from __future__ import annotations

import json
import re
from typing import Any, Iterator

_INSTALLED = False
_ORIGINAL_EXTRACT_JSON = None


def _rendered(value: Any) -> str:
    text = str(value or "").replace("\ufeff", "")
    # O Markdown renderizado do ChatGPT pode escapar caracteres que não são
    # escapes JSON válidos. Preserve escapes JSON reais e normalize só estes.
    return re.sub(r"(\\+)([_<>])", lambda match:
                  match[1][:-1] + match[2] if len(match[1]) % 2 else match[0], text)


def _balanced_objects(text: str) -> Iterator[str]:
    """Yield complete JSON-object shaped regions, including nested braces.

    Braces inside JSON strings do not affect depth. Incomplete trailing objects
    are deliberately ignored: formatting can be repaired, truncation cannot.
    """
    source = _rendered(text)
    start = -1
    depth = 0
    in_string = False
    escaped = False

    for index, char in enumerate(source):
        if in_string:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == '"':
                in_string = False
            continue

        # Markdown outside an object is not a JSON string (e.g. an unmatched
        # quotation in the introduction must not hide the response).
        if char == '"' and depth:
            in_string = True
            continue
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
            continue
        if char == "}" and depth:
            depth -= 1
            if depth == 0 and start >= 0:
                yield source[start : index + 1]
                start = -1


def _repair_controls_inside_strings(candidate: str) -> str:
    """Repair DOM line breaks/control chars without changing JSON structure."""
    out: list[str] = []
    in_string = False
    escaped = False
    for char in _rendered(candidate):
        if in_string:
            if escaped:
                out.append(char)
                escaped = False
                continue
            if char == "\\":
                out.append(char)
                escaped = True
                continue
            if char == '"':
                out.append(char)
                in_string = False
                continue
            if char in "\r\n\t":
                # innerText pode inserir quebra visual dentro de uma string JSON,
                # como ocorreu no official_url do diagnóstico de 06/09/2026.
                # Um espaço é seguro para prosa e é removido pelos cleaners de URL.
                out.append(" ")
                continue
            if ord(char) < 0x20:
                out.append(" ")
                continue
            out.append(char)
            continue

        out.append(char)
        if char == '"':
            in_string = True
    return "".join(out)


def _remove_trailing_commas(candidate: str) -> str:
    """Remove only commas immediately before ]/} outside JSON strings."""
    source = candidate
    out: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(source):
        char = source[index]
        if in_string:
            out.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue

        if char == '"':
            in_string = True
            out.append(char)
            index += 1
            continue

        if char == ",":
            probe = index + 1
            while probe < len(source) and source[probe].isspace():
                probe += 1
            if probe < len(source) and source[probe] in "}]":
                index += 1
                continue
        out.append(char)
        index += 1
    return "".join(out)


def _decode_candidate(candidate: str) -> dict[str, Any] | None:
    variants = [
        _rendered(candidate).strip().strip("`").strip(),
    ]
    repaired = _repair_controls_inside_strings(variants[0])
    if repaired not in variants:
        variants.append(repaired)
    without_trailing = _remove_trailing_commas(repaired)
    if without_trailing not in variants:
        variants.append(without_trailing)

    for value in variants:
        try:
            payload = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    return None


def content_object(payload: dict[str, Any]) -> bool:
    return bool(
        isinstance(payload.get("product_name"), str)
        and payload["product_name"].strip()
        and isinstance(payload.get("short_description"), str)
        and payload["short_description"].strip()
        and isinstance(payload.get("content", payload.get("description")), str)
        and str(payload.get("content", payload.get("description"))).strip()
    )


def extract_json(text: str, expected_product: str = "") -> dict[str, Any] | None:
    """Choose a complete response object; never complete a truncated document.

    Schema outranks incidental JSON. With an expected identity, only a content
    object for that product is eligible. Callers must additionally scope text to
    the current assistant turn; the parser cannot prove conversation provenance.
    """
    raw = _rendered(text).strip()
    if not raw:
        return None

    payloads = [payload for candidate in _balanced_objects(raw)
                if (payload := _decode_candidate(candidate)) is not None]
    expected = " ".join(expected_product.split()).casefold()
    if expected:
        payloads = [p for p in payloads if content_object(p)
                    and " ".join(p["product_name"].split()).casefold() == expected]
    if not payloads:
        return None
    # Ties go to the newest complete object in this response only.
    return max(enumerate(payloads), key=lambda pair: (content_object(pair[1]), pair[0]))[1]


def response_kind(text: str, expected_product: str = "") -> str:
    payload = extract_json(text, expected_product)
    if payload is not None and content_object(payload):
        for candidate in _balanced_objects(text):
            try:
                if json.loads(candidate) == payload:
                    return "content_json_complete"
            except ValueError:
                pass
        return "content_json_dom_repaired"
    if any(content_object(p) for c in _balanced_objects(text)
           if (p := _decode_candidate(c)) is not None):
        return "content_product_mismatch"
    if list(_balanced_objects(text)):
        return "content_json_invalid"
    return "content_response_partial" if str(text).strip() else "content_no_response"


def install_chatgpt_json_recovery_runtime() -> None:
    from app.additions import chatgpt_content_response_runtime as content_runtime
    global _INSTALLED, _ORIGINAL_EXTRACT_JSON
    if _INSTALLED:
        return
    _ORIGINAL_EXTRACT_JSON = content_runtime._extract_json
    content_runtime._extract_json = extract_json
    _INSTALLED = True


__all__ = [
    "install_chatgpt_json_recovery_runtime",
    "extract_json",
    "_balanced_objects",
    "_repair_controls_inside_strings",
]
