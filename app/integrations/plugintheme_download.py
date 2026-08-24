"""Download legítimo do PluginTheme pela mesma API usada pelo frontend."""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.integrations.ultrapack_download import (
    LocalZipArtifact, UltrapackDownloadError, UltrapackDownloader,
)


class PluginThemeDownloadError(UltrapackDownloadError):
    pass


class PluginThemeDownloader(UltrapackDownloader):
    API_BASE = "https://api.plugintheme.net/api"

    @staticmethod
    def access_allowed(payload: object) -> bool:
        """Aceita somente indicadores explícitos de autorização conhecidos pela API."""
        if not isinstance(payload, dict):
            return False
        for container_key in ("data", "result", "access"):
            nested = payload.get(container_key)
            if isinstance(nested, dict) and PluginThemeDownloader.access_allowed(nested):
                return True
        for key in ("canDownload", "can_download", "hasAccess", "has_access", "allowed", "isAllowed", "is_allowed", "authorized"):
            value = payload.get(key)
            if value is True or (isinstance(value, (int, str)) and str(value).strip().lower() in {"1", "true", "yes"}):
                return True
        return False

    @staticmethod
    def _credit_failure(payload: object) -> bool:
        """Reconhece respostas da API que indicam ausência de crédito/saldo de download."""
        credit_terms = ("credit", "credito", "crédito", "credits", "creditos", "créditos", "balance", "saldo")
        negative_terms = (
            "insufficient", "not enough", "no credit", "no credits", "sem credito", "sem crédito",
            "sem creditos", "sem créditos", "saldo insuficiente", "esgotado", "esgotados", "exhausted",
        )

        def walk(value: object) -> bool:
            if isinstance(value, dict):
                for raw_key, nested in value.items():
                    key = str(raw_key or "").strip().lower()
                    key_is_credit = any(term in key for term in credit_terms)
                    if key_is_credit:
                        if nested is False:
                            return True
                        if isinstance(nested, (int, float)) and not isinstance(nested, bool) and nested <= 0:
                            return True
                        nested_text = str(nested or "").strip().lower()
                        if nested_text in {"0", "0.0", "false", "none", "null"}:
                            return True
                        if any(term in nested_text for term in negative_terms):
                            return True
                    if walk(nested):
                        return True
                joined = " ".join(str(item) for item in value.values() if item is not None).lower()
                return any(term in joined for term in credit_terms) and any(term in joined for term in negative_terms)
            if isinstance(value, (list, tuple, set)):
                return any(walk(item) for item in value)
            text = str(value or "").strip().lower()
            return any(term in text for term in credit_terms) and any(term in text for term in negative_terms)

        return walk(payload)

    @staticmethod
    def _matching_product(value: Any, slug: str) -> dict[str, str] | None:
        """Procura o objeto que contém o slug exato, sem confundir IDs de itens filhos."""
        if isinstance(value, Mapping):
            own_slug = str(value.get("slug") or "").strip()
            own_id = str(value.get("id") or "").strip()
            if own_slug.lower() == slug.lower() and re.fullmatch(r"[0-9a-f-]{20,}", own_id, re.I):
                return {
                    "id": own_id,
                    "slug": slug,
                    "version": str(value.get("version") or "").strip(),
                }
            for nested in value.values():
                found = PluginThemeDownloader._matching_product(nested, slug)
                if found:
                    return found
        elif isinstance(value, (list, tuple)):
            for nested in value:
                found = PluginThemeDownloader._matching_product(nested, slug)
                if found:
                    return found
        return None

    @staticmethod
    def _json_object_candidates(text: str, anchor: int) -> list[str]:
        """Retorna objetos JSON balanceados que contêm o slug, do menor para o maior."""
        stack: list[int] = []
        candidates: list[str] = []
        in_string = False
        escaped = False
        for index, char in enumerate(text):
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
                continue
            if char == "{":
                stack.append(index)
                continue
            if char != "}" or not stack:
                continue
            start = stack.pop()
            if start <= anchor <= index:
                candidates.append(text[start:index + 1])
        return sorted(candidates, key=len)

    @staticmethod
    def product_data(product_url: str, html: str) -> dict[str, str]:
        slug = Path(urlparse(product_url).path.rstrip("/")).name
        if not slug:
            raise PluginThemeDownloadError("Slug do produto PluginTheme não encontrado")

        # O payload RSC do Next.js contém JSON escapado dentro do HTML. Em páginas
        # de packs/bundles há muitos produtos no mesmo documento; por isso o ID
        # deve vir do objeto que possui o slug exato, e não do ID mais próximo.
        decoded = (
            str(html or "")
            .replace('\\"', '"')
            .replace("\\u0026", "&")
            .replace("\\/", "/")
        )
        positions = [
            match.start()
            for match in re.finditer(
                rf'"slug"\s*:\s*"{re.escape(slug)}"',
                decoded,
                re.I,
            )
        ]
        for position in positions:
            for candidate in PluginThemeDownloader._json_object_candidates(decoded, position):
                try:
                    parsed = json.loads(candidate)
                except (TypeError, ValueError):
                    continue
                found = PluginThemeDownloader._matching_product(parsed, slug)
                if found:
                    return found

            # Fallback para payloads RSC que não formam um objeto JSON isolado
            # parseável. O id do próprio produto normalmente precede slug;
            # priorizar o último ID anterior evita capturar um item filho do pack
            # logo depois do slug, origem do falso "sem acesso" em bundles.
            prefix_start = max(0, position - 6000)
            prefix = decoded[prefix_start:position]
            ids_before = list(re.finditer(
                r'"id"\s*:\s*"([0-9a-f-]{20,})"',
                prefix,
                re.I,
            ))
            if not ids_before:
                continue
            product_id = ids_before[-1].group(1)

            object_start = max(0, position - 3500)
            object_window = decoded[object_start:position + 3500]
            object_anchor = position - object_start
            versions_before = list(re.finditer(
                r'"version"\s*:\s*"([^"\\]+)"',
                object_window[:object_anchor],
                re.I,
            ))
            versions_after = list(re.finditer(
                r'"version"\s*:\s*"([^"\\]+)"',
                object_window[object_anchor:],
                re.I,
            ))
            if versions_before:
                version = versions_before[-1].group(1)
            elif versions_after:
                version = versions_after[0].group(1)
            else:
                version = ""
            return {"id": product_id, "slug": slug, "version": version}

        raise PluginThemeDownloadError("Identificador do produto não encontrado no payload público")

    def inspect_product(self, product_url: str) -> tuple[str, str]:
        response = self._get(product_url)
        data = self.product_data(product_url, response.text)
        return product_url, data.get("version", "")

    def _download_metadata(self, product_url: str) -> tuple[dict[str, str], str]:
        response = self._get(product_url)
        product = self.product_data(product_url, response.text)
        product_id = product["id"]
        check = self._get(f"{self.API_BASE}/downloads/{product_id}/check-access")
        try:
            access = check.json()
            raw_access = access
            if isinstance(access.get("data"), dict):
                access = access["data"]
        except Exception:
            raise PluginThemeDownloadError("Resposta inválida ao verificar acesso no PluginTheme") from None
        allowed = self.access_allowed(access)
        if not allowed:
            if self._credit_failure(raw_access):
                raise PluginThemeDownloadError(
                    "Créditos de download insuficientes no PluginTheme. Adicione créditos à conta e tente novamente."
                )
            raise PluginThemeDownloadError("Sessão do PluginTheme expirada ou sem acesso ao produto")
        metadata_response = self._get(f"{self.API_BASE}/downloads/{product_id}/file")
        try:
            metadata = metadata_response.json()
            raw_metadata = metadata
            if isinstance(metadata.get("data"), dict):
                metadata = metadata["data"]
        except Exception:
            raise PluginThemeDownloadError("Resposta inválida ao solicitar o arquivo no PluginTheme") from None
        if self._credit_failure(raw_metadata):
            raise PluginThemeDownloadError(
                "Créditos de download insuficientes no PluginTheme. Adicione créditos à conta e tente novamente."
            )
        download_url = str(metadata.get("downloadUrl") or metadata.get("url") or "").strip()
        if not download_url:
            raise PluginThemeDownloadError("PluginTheme não retornou uma URL de download")
        return {"download_url": download_url, "file_name": str(metadata.get("fileName") or "")}, product.get("version", "")

    def download(self, product_url: str, staging_dir: str | Path) -> tuple[LocalZipArtifact, str]:
        metadata, version = self._download_metadata(product_url)
        download_url = metadata["download_url"]
        response = self._get(download_url, stream=True)
        target_dir = Path(staging_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        name = Path(metadata["file_name"]).name if metadata["file_name"] else self._response_file_name(response, download_url)
        if not name.lower().endswith(".zip"):
            name += ".zip"
        target = target_dir / name
        total = 0
        with target.open("wb") as output:
            for chunk in response.iter_content(1024 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > self.max_bytes:
                    target.unlink(missing_ok=True)
                    raise PluginThemeDownloadError("ZIP excede o limite de tamanho")
                output.write(chunk)
        return self.validate_zip(target, source_url=self._safe_source_url(download_url)), version


class SourceDownloader:
    """Seleciona o adaptador pela origem sem alterar o modelo de jobs legado."""
    def __init__(self, ultrapack: UltrapackDownloader, plugintheme: PluginThemeDownloader) -> None:
        self.ultrapack = ultrapack
        self.plugintheme = plugintheme
        self._session = None

    @staticmethod
    def is_plugintheme(url: str) -> bool:
        return urlparse(str(url or "")).hostname in {"plugintheme.net", "www.plugintheme.net"}

    @property
    def session(self):
        return self._session

    @session.setter
    def session(self, value):
        self._session = value
        self.ultrapack.session = value
        self.plugintheme.session = value

    def _for(self, url: str):
        return self.plugintheme if self.is_plugintheme(url) else self.ultrapack

    def inspect_product(self, url: str):
        return self._for(url).inspect_product(url)

    def download(self, url: str, staging_dir: str | Path):
        return self._for(url).download(url, staging_dir)
