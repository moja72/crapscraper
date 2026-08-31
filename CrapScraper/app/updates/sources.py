from __future__ import annotations

import hashlib
import json
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from html import unescape
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

import requests

from app.updates.models import UpdateError
from app.updates.source_auth import ensure_source_session, get_source_session, set_source_state


@dataclass(frozen=True)
class DownloadArtifact:
    path: Path
    sha256: str
    size: int
    requested_url: str
    final_url: str
    content_type: str


class SourceFailure(RuntimeError):
    def __init__(self, error: UpdateError):
        super().__init__(error.message); self.error = error


class UpdateSource(Protocol):
    kind: str
    display_name: str
    def validate_authentication(self) -> None: ...
    def confirm_version(self, job: dict[str, Any]) -> str: ...
    def download(self, job: dict[str, Any], target: Path) -> DownloadArtifact: ...


_CREDIT_RE = re.compile(r"(?:credits?[\"']?\s*[:=]\s*0|insufficient\s+credits?|balance\s+exhausted|quota\s+exceeded|download\s+limit\s+reached|cr[eé]ditos?\s+insuficientes?)", re.I)


def classify_source_error(source: str, *, status: int | None=None, body: str="", requested_url: str="", final_url: str="", content_type: str="", technical: str="") -> UpdateError:
    credit = bool(_CREDIT_RE.search(body or technical))
    if credit:
        return UpdateError(message=f"Download não concluído: créditos de download insuficientes no {source}.",technical_message=technical or body[:500],code="insufficient_credits",stage="downloading",source=source,requested_url=requested_url,final_url=final_url,http_status=status,content_type=content_type,diagnosis="A origem informou saldo, cota ou limite de download esgotado.",recoverable=True)
    if status in {401,403}:
        return UpdateError(message=f"{source} recusou o acesso ao download; verifique a autenticação.",technical_message=technical or body[:500],code="authentication_access",stage="authenticating",source=source,requested_url=requested_url,final_url=final_url,http_status=status,content_type=content_type,diagnosis="Falha de autenticação ou acesso, sem evidência de créditos insuficientes.",recoverable=True)
    return UpdateError(message=f"{source} recusou o download ou retornou um artefato inválido.",technical_message=technical or body[:500],code="source_download_failed",stage="downloading",source=source,requested_url=requested_url,final_url=final_url,http_status=status,content_type=content_type,diagnosis="Resposta da origem incompatível com um arquivo ZIP.",recoverable=True)


class HttpDownloadTransport:
    def __init__(self, session: requests.Session | None=None, timeout: int=90): self.session=session or requests.Session();self.timeout=timeout
    def download(self, *, url: str, target: Path, source: str, headers: dict[str,str]|None=None, cookies: dict[str,str]|None=None) -> DownloadArtifact:
        if urlparse(url).scheme not in {"http","https"}: raise SourceFailure(UpdateError(message=f"URL inválida para {source}.",code="invalid_source_url",stage="validating",source=source,requested_url=url,recoverable=False))
        try: response=self.session.get(url,headers=headers or {},cookies=cookies or {},timeout=self.timeout,allow_redirects=True,stream=True)
        except requests.RequestException as exc: raise SourceFailure(classify_source_error(source,requested_url=url,technical=str(exc))) from exc
        content_type=str(response.headers.get("Content-Type") or "").lower(); disposition=str(response.headers.get("Content-Disposition") or "")
        preview=response.content[:4096] if response.status_code>=400 or "html" in content_type else b""
        body=preview.decode("utf-8","ignore")
        if response.status_code>=400 or "html" in content_type or ("zip" not in content_type and ".zip" not in disposition.lower()):
            raise SourceFailure(classify_source_error(source,status=response.status_code,body=body,requested_url=url,final_url=response.url,content_type=content_type))
        target.parent.mkdir(parents=True,exist_ok=True); digest=hashlib.sha256();size=0
        with target.open("wb") as stream:
            for chunk in response.iter_content(1024*1024):
                if chunk: stream.write(chunk);digest.update(chunk);size+=len(chunk)
        if not zipfile.is_zipfile(target):
            target.unlink(missing_ok=True)
            raise SourceFailure(classify_source_error(source,status=response.status_code,requested_url=url,final_url=response.url,content_type=content_type,technical="O arquivo baixado não é um ZIP válido."))
        with zipfile.ZipFile(target) as archive:
            bad=archive.testzip()
            if bad: raise SourceFailure(classify_source_error(source,requested_url=url,final_url=response.url,content_type=content_type,technical=f"Entrada ZIP corrompida: {bad}"))
        return DownloadArtifact(target,digest.hexdigest(),size,url,response.url,content_type)


def _json_env(name: str) -> dict[str,str]:
    try: value=json.loads(os.getenv(name,"{}") or "{}")
    except json.JSONDecodeError: value={}
    return {str(k):str(v) for k,v in value.items()} if isinstance(value,dict) else {}


class _HttpSource:
    kind=""; display_name=""; header_env=""; cookie_env=""
    def __init__(self, transport: HttpDownloadTransport | None=None): self.transport=transport or HttpDownloadTransport()
    def _session(self):
        shared=get_source_session(self.kind)
        return shared if isinstance(shared, requests.Session) else self.transport.session
    def validate_authentication(self) -> None:
        if get_source_session(self.kind) is not None:
            return
        if not (_json_env(self.header_env) or _json_env(self.cookie_env)):
            raise SourceFailure(UpdateError(message=f"Autenticação do {self.display_name} não configurada.",code="authentication_missing",stage="authenticating",source=self.display_name,recoverable=True))
    def _get(self,url: str, **kwargs: Any) -> requests.Response:
        shared=get_source_session(self.kind)
        headers={} if shared is not None else _json_env(self.header_env)
        cookies={} if shared is not None else _json_env(self.cookie_env)
        try:r=self._session().get(url,headers=headers,cookies=cookies,timeout=self.transport.timeout,allow_redirects=True,**kwargs)
        except requests.RequestException as exc:raise SourceFailure(classify_source_error(self.display_name,requested_url=url,technical=str(exc))) from exc
        if r.status_code>=400:raise SourceFailure(classify_source_error(self.display_name,status=r.status_code,body=r.text[:4000],requested_url=url,final_url=r.url,content_type=str(r.headers.get("Content-Type") or "")))
        return r
    def confirm_version(self, job: dict[str,Any]) -> str:
        version=str(job.get("source_version") or "").strip()
        if not re.fullmatch(r"\d+(?:\.\d+)*(?:[-+._a-zA-Z0-9]*)?",version): raise SourceFailure(UpdateError(message=f"Versão aprovada inválida para {self.display_name}.",code="invalid_version",stage="validating",source=self.display_name,recoverable=False))
        return version
    def download(self, job: dict[str,Any], target: Path) -> DownloadArtifact:
        return self.transport.download(url=str(job["source_url"]),target=target,source=self.display_name,headers=_json_env(self.header_env),cookies=_json_env(self.cookie_env))


class PluginThemeSource(_HttpSource):
    kind="plugintheme";display_name="PluginTheme";header_env="SCRAPER_PLUGINTHEME_HEADERS_JSON";cookie_env="SCRAPER_PLUGINTHEME_COOKIES_JSON"
    api_base="https://api.plugintheme.net/api"
    def _product(self,job: dict[str,Any])->dict[str,str]:
        url=str(job["source_url"]);html=self._get(url).text.replace('\\"','"').replace("\\/","/");slug=Path(urlparse(url).path.rstrip("/")).name
        anchor=re.search(rf'"slug"\s*:\s*"{re.escape(slug)}"',html,re.I)
        if not anchor:raise SourceFailure(classify_source_error(self.display_name,requested_url=url,technical="Produto não encontrado no payload público do PluginTheme."))
        prefix=html[max(0,anchor.start()-6000):anchor.start()];ids=list(re.finditer(r'"id"\s*:\s*"([0-9a-f-]{20,})"',prefix,re.I));versions=list(re.finditer(r'"version"\s*:\s*"([^"\\]+)"',prefix,re.I))
        if not ids:raise SourceFailure(classify_source_error(self.display_name,requested_url=url,technical="ID do produto PluginTheme não encontrado."))
        return {"id":ids[-1].group(1),"version":versions[-1].group(1) if versions else str(job["source_version"])}
    def confirm_version(self,job):return self._product(job)["version"]
    def validate_access(self, job: dict[str, Any]) -> dict[str, str]:
        ensure_source_session(self.kind, str(job.get("source_url") or ""))
        self.validate_authentication()
        product = self._product(job)
        set_source_state(self.kind, "validated")
        return {"source_url": str(job["source_url"]), "product_id": product["id"], "version": product["version"]}
    def download(self,job,target):
        product=self._product(job);check=self._get(f"{self.api_base}/downloads/{product['id']}/check-access")
        try:access=check.json()
        except ValueError:raise SourceFailure(classify_source_error(self.display_name,requested_url=check.url,body=check.text,technical="Resposta de acesso inválida."))
        serialized=json.dumps(access,ensure_ascii=False)
        allowed=any(value is True or str(value).lower() in {"1","true","yes"} for key,value in (access.get("data",access) if isinstance(access,dict) else {}).items() if key in {"canDownload","can_download","hasAccess","has_access","allowed","authorized"})
        if not allowed:raise SourceFailure(classify_source_error(self.display_name,status=403,body=serialized,requested_url=check.url,technical="Acesso ao produto não autorizado."))
        response=self._get(f"{self.api_base}/downloads/{product['id']}/file")
        try:metadata=response.json();metadata=metadata.get("data",metadata)
        except ValueError:raise SourceFailure(classify_source_error(self.display_name,body=response.text,requested_url=response.url,technical="Metadados de download inválidos."))
        url=str(metadata.get("downloadUrl") or metadata.get("url") or "")
        if not url:raise SourceFailure(classify_source_error(self.display_name,body=json.dumps(metadata),requested_url=response.url,technical="PluginTheme não retornou URL de download."))
        shared=get_source_session(self.kind)
        if shared is not None:
            return HttpDownloadTransport(session=shared,timeout=self.transport.timeout).download(url=url,target=target,source=self.display_name)
        return self.transport.download(url=url,target=target,source=self.display_name,headers=_json_env(self.header_env),cookies=_json_env(self.cookie_env))


class UltraPackSource(_HttpSource):
    kind="ultrapackv2";display_name="UltraPackV2";header_env="SCRAPER_ULTRAPACK_HEADERS_JSON";cookie_env="SCRAPER_ULTRAPACK_COOKIES_JSON"
    def _inspect(self,job):
        url=str(job["source_url"]);html=self._get(url).text;tag=next((tag for tag in re.findall(r"<a\b[^>]*>",html,re.I) if re.search(r'class\s*=\s*["\'][^"\']*single-bt-download-a',tag,re.I)),"");token=re.search(r'data-f\s*=\s*["\']([^"\']+)',tag,re.I)
        if not token:raise SourceFailure(classify_source_error(self.display_name,requested_url=url,technical="Botão autenticado de download não encontrado."))
        parts=urlsplit(url);query=[(k,v) for k,v in parse_qsl(parts.query,keep_blank_values=True) if k!="f"]+[("f",unescape(token.group(1)).strip())]
        plain=re.sub(r"<[^>]+>"," ",html);match=re.search(r"(?:versão|versao|version)\s*[:\-]?\s*v?([0-9]+(?:\.[0-9A-Za-z_-]+)+)",plain,re.I)
        return urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(query),"")),match.group(1) if match else str(job["source_version"])
    def validate_access(self, job: dict[str, Any]) -> dict[str, str]:
        """Preflight somente leitura: autenticação, produto e link de download."""
        ensure_source_session(self.kind, str(job.get("source_url") or ""))
        self.validate_authentication()
        url, version = self._inspect(job)
        set_source_state(self.kind, "validated")
        return {"source_url": str(job["source_url"]), "download_url": url, "version": version}
    def confirm_version(self,job):return self._inspect(job)[1]
    def download(self,job,target):
        url,_version=self._inspect(job)
        shared=get_source_session(self.kind)
        if shared is not None:
            return HttpDownloadTransport(session=shared,timeout=self.transport.timeout).download(url=url,target=target,source=self.display_name)
        return self.transport.download(url=url,target=target,source=self.display_name,headers=_json_env(self.header_env),cookies=_json_env(self.cookie_env))


class SourceRegistry:
    def __init__(self, sources: list[UpdateSource] | None=None):
        sources=sources or [PluginThemeSource(),UltraPackSource()];self.sources={s.kind:s for s in sources}
    def get(self, kind: str) -> UpdateSource:
        try: return self.sources[kind]
        except KeyError as exc: raise ValueError(f"Fonte não suportada: {kind}") from exc
