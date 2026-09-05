from __future__ import annotations

import os

import requests


def _http_status(error):
    if not isinstance(error, requests.HTTPError):
        return 0
    response = getattr(error, "response", None)
    return int(getattr(response, "status_code", 0) or 0)


def install_addition_taxonomy_waf_recovery():
    from app.additions.wordpress import AdditionStoreGateway

    if getattr(AdditionStoreGateway, "_crapscraper_taxonomy_waf_installed", False):
        return

    def term(self, kind, name):
        endpoint = "categories" if kind == "category" else "tags"
        expected = str(name or "").strip()
        if not expected:
            raise RuntimeError("Termo WooCommerce vazio")

        slug = self._term_slug(expected)
        rows = []
        if slug:
            try:
                rows = self._wc("GET", f"/products/{endpoint}", params={"slug": slug, "per_page": 100})
            except requests.HTTPError as error:
                if _http_status(error) not in {401, 403}:
                    raise
                rows = []

        for row in rows:
            if str(row.get("name") or "").casefold() == expected.casefold() or str(row.get("slug") or "").casefold() == slug.casefold():
                return int(row["id"])

        list_blocked = False
        try:
            rows = self._wc("GET", f"/products/{endpoint}", params={"per_page": 100})
        except requests.HTTPError as error:
            if _http_status(error) not in {401, 403}:
                raise
            rows = []
            list_blocked = True

        for row in rows:
            if str(row.get("name") or "").casefold() == expected.casefold() or str(row.get("slug") or "").casefold() == slug.casefold():
                return int(row["id"])

        # Se o próprio endpoint de taxonomia está sendo barrado pelo WAF,
        # não insistimos com POST no mesmo endpoint. A criação do produto
        # continua sem a taxonomia e os nomes ficam preservados em metadata.
        if list_blocked:
            return 0

        try:
            created = self._wc("POST", f"/products/{endpoint}", json={"name": expected})
            return int(created["id"])
        except requests.HTTPError as error:
            existing = self._term_exists_id(error)
            if existing:
                return existing
            if _http_status(error) in {401, 403}:
                return 0
            raise

    def create_parent(self, job, media_id, download_ref, image_url=""):
        category_names = list(job.get("categories") or []) or (["Temas"] if job["kind"] == "theme" else ["Plugins"])
        tag_names = list(job.get("tags") or [])

        category_ids = []
        pending_categories = []
        for name in category_names:
            term_id = int(self._term("category", name) or 0)
            if term_id:
                category_ids.append(term_id)
            else:
                pending_categories.append(str(name))

        tag_ids = []
        pending_tags = []
        for name in tag_names:
            term_id = int(self._term("tag", name) or 0)
            if term_id:
                tag_ids.append(term_id)
            else:
                pending_tags.append(str(name))

        attribute = int(os.getenv("SCRAPER_WOOCOMMERCE_PLAN_ATTRIBUTE_ID", "4"))
        images = [{"id": int(media_id)}] if int(media_id or 0) else ([{"src": str(image_url)}] if str(image_url or "").strip() else [])
        if not images:
            raise RuntimeError("Imagem principal não disponível para criação do produto")

        metadata = [
            {"key": "pt_versao", "value": job["source_version"]},
            {"key": "site_oficial", "value": job["official_url"]},
            {"key": "desenvolvedor", "value": job["developer"]},
            {"key": "crapscraper_addition_job", "value": job["job_id"]},
            {"key": "fonte_crapscraper", "value": job["source_name"]},
        ]
        if pending_categories:
            metadata.append({"key": "crapscraper_pending_categories", "value": " | ".join(pending_categories)})
        if pending_tags:
            metadata.append({"key": "crapscraper_pending_tags", "value": " | ".join(pending_tags)})
        if pending_categories or pending_tags:
            metadata.append({"key": "crapscraper_taxonomy_state", "value": "deferred_waf"})

        payload = {
            "name": job["product_name"],
            "type": "variable",
            "status": "draft",
            "description": job["content"],
            "short_description": job["short_description"],
            "categories": [{"id": value} for value in category_ids],
            "tags": [{"id": value} for value in tag_ids],
            "images": images,
            "attributes": [{"id": attribute, "visible": True, "variation": True, "options": ["Anual", "Vitalício"]}],
            "meta_data": metadata,
        }
        return self._wc("POST", "/products", json=payload)

    AdditionStoreGateway._term = term
    AdditionStoreGateway.create_parent = create_parent
    AdditionStoreGateway._crapscraper_taxonomy_waf_installed = True
