from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_SENSITIVE_NAME = re.compile(
    r"(?i)^(?:consumer_(?:key|secret)|password|passwd|secret|token|authorization|cookie|session(?:_?id)?)$"
)


def safe_url(value: object) -> str:
    text = str(value or "")
    try:
        parsed = urlsplit(text)
    except ValueError:
        return "[url inválida]"
    if not parsed.scheme or not parsed.netloc:
        return safe_text(text)
    hostname = parsed.hostname or ""
    try:
        port = f":{parsed.port}" if parsed.port else ""
    except ValueError:
        port = ""
    netloc = f"{hostname}{port}"
    query = urlencode([
        (key, "[redacted]" if _SENSITIVE_NAME.match(key) else item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
    ])
    return urlunsplit((parsed.scheme, netloc, parsed.path, query, ""))


def safe_text(value: object, *, limit: int = 1000) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ")
    text = re.sub(r"(?i)(https?://)[^/@\s]+:[^/@\s]+@", r"\1[redacted]@", text)
    text = re.sub(
        r"(?i)\b(consumer_(?:key|secret)|password|passwd|secret|token|authorization|cookie|session(?:_?id)?)\b"
        r"(\s*[:=]\s*)[^&\s,;)}\]]+",
        r"\1\2[redacted]",
        text,
    )
    text = re.sub(r"(?i)\b(?:ck|cs)_[a-z0-9_-]{6,}\b", "[redacted]", text)
    return text[:limit]


def safe_message(error: BaseException) -> str:
    return safe_text(error)
