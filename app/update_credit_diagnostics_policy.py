from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlparse

from app.integrations.ultrapack_download import UltrapackDownloadError, UltrapackDownloader
from app.integrations.wordpress import sanitize_text
from app.operations.preparation import UpdatePreparationService

_INSTALLED = False
_BASE_PREPARE = UpdatePreparationService.prepare


_CREDIT_KEYS = (
    "credit", "credits", "credito", "crédito", "creditos", "créditos",
    "balance", "saldo", "quota",
)
_CREDIT_NEGATIVE = (
    "insufficient", "not enough", "no credit", "no credits",
    "sem credito", "sem crédito", "sem creditos", "sem créditos",
    "saldo insuficiente", "credit exhausted", "credits exhausted",
    "esgotado", "esgotados", "exhausted", "quota exceeded",
    "download limit", "limite de download",
)


def _source_label(downloader: Any, url: str = "") -> str:
    class_name = type(downloader).__name__.lower()
    host = (urlparse(str(url or "")).hostname or "").lower()
    if "plugintheme" in class_name or "plugintheme.net" in host:
        return "PluginTheme"
    return "UltraPackV2"


def _credit_failure(value: object) -> bool:
    """Só classifica falta de crédito quando a resposta traz evidência explícita."""

    def walk(item: object) -> bool:
        if isinstance(item, dict):
            for raw_key, nested in item.items():
                key = str(raw_key or "").strip().lower()
                key_is_credit = any(token in key for token in _CREDIT_KEYS)
                if key_is_credit:
                    if nested is False:
                        return True
                    if isinstance(nested, (int, float)) and not isinstance(nested, bool) and nested <= 0:
                        return True
                    nested_text = str(nested or "").strip().lower()
                    if nested_text in {"0", "0.0", "false", "none", "null"}:
                        return True
                    if any(token in nested_text for token in _CREDIT_NEGATIVE):
                        return True
                if walk(nested):
                    return True
            joined = " ".join(str(nested) for nested in item.values() if nested is not None).lower()
            return (
                any(token in joined for token in _CREDIT_KEYS)
                and any(token in joined for token in _CREDIT_NEGATIVE)
            )
        if isinstance(item, (list, tuple, set)):
            return any(walk(nested) for nested in item)
        text = str(item or "").strip().lower()
        return (
            any(token in text for token in _CREDIT_KEYS)
            and any(token in text for token in _CREDIT_NEGATIVE)
        )

    if walk(value):
        return True

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return False
        return walk(parsed)
    return False


def _response_payload(response: Any) -> object:
    try:
        payload = response.json()
        if payload is not None:
            return payload
    except Exception:
        pass
    try:
        return str(getattr(response, "text", "") or "")
    except Exception:
        return ""


def _credit_message(label: str) -> str:
    return (
        f"{label} não liberou o download: créditos de download insuficientes "
        "ou esgotados no site de origem. Adicione créditos à conta ou aguarde "
        "a renovação do limite e tente novamente."
    )


def _patched_get(
    self: UltrapackDownloader,
    url: str,
    *,
    stream: bool = False,
    stage: str = "request",
) -> Any:
    """Mantém o transporte atual, mas preserva a origem e diagnostica crédito."""

    last: Exception | None = None
    label = _source_label(self, url)

    for attempt in range(self.retries + 1):
        try:
            response = self.session.get(
                url,
                timeout=self.timeout,
                stream=stream,
                allow_redirects=True,
            )
            self._record_response(stage, url, response)
            status = int(getattr(response, "status_code", 0) or 0)

            if status >= 400:
                if _credit_failure(_response_payload(response)):
                    raise UltrapackDownloadError(_credit_message(label)) from None

                error = UltrapackDownloadError(
                    f"{label} recusou a requisição: HTTP {status} em {stage}: "
                    f"{self._safe_source_url(url)}"
                )
                if status in {401, 403}:
                    raise error from None
                raise error

            return response
        except Exception as error:
            last = error
            lowered = str(error).lower()
            if (
                _credit_failure(str(error))
                or "http 401" in lowered
                or "http 403" in lowered
            ):
                break
            if attempt >= self.retries:
                break
            time.sleep(self.retry_delay)

    if isinstance(last, UltrapackDownloadError):
        message = str(last)
        if message.startswith(("PluginTheme ", "UltraPackV2 ")):
            raise last from None

    raise UltrapackDownloadError(
        f"Falha no download {label}: {sanitize_text(last)}"
    ) from None


def _patched_prepare(self: UpdatePreparationService, job: Any):
    preview = _BASE_PREPARE(self, job)

    # O fluxo legado captura falhas de download dentro do preview. Promovemos
    # especificamente falta de crédito para o log técnico, sem transformar
    # qualquer 401/403 em diagnóstico de saldo.
    for item in getattr(preview, "validations", ()) or ():
        if bool(getattr(item, "ok", False)):
            continue
        detail = str(getattr(item, "detail", "") or "")
        if not _credit_failure(detail):
            continue
        self.logger(
            "💳 Download não concluído por falta de créditos no site de origem: "
            f"{detail}"
        )
        break

    return preview


def install_update_credit_diagnostics_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    UltrapackDownloader._get = _patched_get
    UpdatePreparationService.prepare = _patched_prepare
    _INSTALLED = True
