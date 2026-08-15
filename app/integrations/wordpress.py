from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class IntegrationError(RuntimeError):
    """Falha segura de comunicacao com uma integracao remota."""


class WriteOperationDisabledError(IntegrationError):
    """Uma operacao remota de escrita foi bloqueada localmente."""


Transport = Callable[[Request, float], tuple[int, Mapping[str, str], bytes]]


def sanitize_text(value: Any, *secrets: str) -> str:
    text = str(value or "")
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


def _default_transport(request: Request, timeout: float) -> tuple[int, Mapping[str, str], bytes]:
    with urlopen(request, timeout=timeout) as response:
        return response.status, dict(response.headers), response.read()


@dataclass(frozen=True)
class ReadOnlyHttpClient:
    base_url: str
    username: str
    password: str
    timeout: float = 30.0
    retries: int = 2
    retry_delay: float = 0.25
    transport: Transport = _default_transport

    def _authorization(self) -> str:
        token = base64.b64encode(
            f"{self.username}:{self.password}".encode("utf-8")
        ).decode("ascii")
        return f"Basic {token}"

    def _request(
        self,
        method: str,
        path: str,
        params: Mapping[str, Any] | None = None,
    ) -> tuple[Any, Mapping[str, str]]:
        normalized_method = str(method).upper()
        if normalized_method not in {"GET", "OPTIONS"}:
            raise WriteOperationDisabledError(
                f"Metodo remoto bloqueado: {normalized_method}"
            )

        url = self.base_url.rstrip("/") + "/" + path.lstrip("/")
        if params:
            query = urlencode(
                [(key, item) for key, value in params.items() for item in (
                    value if isinstance(value, (list, tuple)) else [value]
                )]
            )
            url += ("&" if "?" in url else "?") + query

        request = Request(
            url,
            method=normalized_method,
            headers={
                "Accept": "application/json",
                "Authorization": self._authorization(),
                "User-Agent": "CrapScraper-read-only/1.0",
            },
        )
        last_error: Exception | None = None
        for attempt in range(max(0, self.retries) + 1):
            try:
                status, headers, body = self.transport(request, self.timeout)
                if status >= 400:
                    raise IntegrationError(f"HTTP {status}")
                return (json.loads(body) if body else None), headers
            except (HTTPError, URLError, TimeoutError, IntegrationError) as error:
                last_error = error
                transient = not isinstance(error, HTTPError) or error.code >= 500
                if attempt >= self.retries or not transient:
                    break
                time.sleep(max(0.0, self.retry_delay))

        safe = sanitize_text(last_error, self.username, self.password)
        raise IntegrationError(f"Falha na requisição read-only: {safe}") from None

    def get(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        return self._request("GET", path, params)[0]

    def get_with_headers(
        self, path: str, params: Mapping[str, Any] | None = None
    ) -> tuple[Any, Mapping[str, str]]:
        return self._request("GET", path, params)

    def options(self, path: str) -> Any:
        return self._request("OPTIONS", path)[0]

    def write(self, *_args: Any, **_kwargs: Any) -> None:
        raise WriteOperationDisabledError("Escrita remota desabilitada nesta versao")


class WordPressClient(ReadOnlyHttpClient):
    def identity(self) -> Mapping[str, Any]:
        return self.get("/wp-json/wp/v2/users/me", {"context": "edit"})

    def list_media(
        self, *, page: int = 1, per_page: int = 100, search: str = ""
    ) -> list[Mapping[str, Any]]:
        params: dict[str, Any] = {
            "context": "edit", "page": page, "per_page": per_page
        }
        if search:
            params["search"] = search
        result = self.get("/wp-json/wp/v2/media", params)
        return list(result or [])

    create_media = ReadOnlyHttpClient.write
    update_media = ReadOnlyHttpClient.write
    delete_media = ReadOnlyHttpClient.write
