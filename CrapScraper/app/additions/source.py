from __future__ import annotations
import re
from urllib.parse import urljoin,urlparse
import requests
from app.updates.sources import SourceRegistry

class ProductResearchService:
    def __init__(self,session=None):self.session=session or requests.Session()
    def resolve(self,job):
        if job.get("official_url") and job.get("developer"):return {"official_url":job["official_url"],"developer":job["developer"]}
        try:response=self.session.get(job["source_url"],timeout=30,headers={"User-Agent":"Mozilla/5.0"});response.raise_for_status();html=response.text
        except requests.RequestException as exc:raise RuntimeError(f"Não foi possível pesquisar a página da fonte: {exc}") from exc
        official=str(job.get("official_url") or "")
        if not official:
            source_host=urlparse(job["source_url"]).netloc.lower()
            links=re.findall(r'href=["\']([^"\']+)["\']',html,re.I)
            for link in links:
                candidate=urljoin(job["source_url"],link);host=urlparse(candidate).netloc.lower()
                if host and host!=source_host and not any(x in host for x in ("facebook","twitter","youtube","instagram","google")):official=candidate;break
        developer=""
        plain=re.sub(r"<[^>]+>"," ",html)
        match=re.search(r"(?:developer|desenvolvedor|author|autor)\s*[:\-]\s*([^|<\n]{2,80})",plain,re.I)
        if match:developer=" ".join(match.group(1).split())
        if not official:raise RuntimeError("Página oficial não pôde ser confirmada sem inventar dados")
        return {"official_url":official,"developer":developer}

class AdditionSourceService:
    def __init__(self,registry=None):self.registry=registry or SourceRegistry()
    def source(self,job):return self.registry.get(job["source_kind"])
