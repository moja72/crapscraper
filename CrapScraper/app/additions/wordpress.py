from __future__ import annotations

import mimetypes
import os
import re
import shutil
import unicodedata
from pathlib import Path

import requests


class AdditionStoreGateway:
    def __init__(self, session=None):
        site = (os.getenv("SCRAPER_WP_BASE_URL") or os.getenv("SCRAPER_WOOCOMMERCE_URL") or "").rstrip("/")
        self.wc = site + "/wp-json/wc/v3" if site and "/wp-json/" not in site else site
        self.wp = (site.split("/wp-json/", 1)[0] if "/wp-json/" in site else site) + "/wp-json/wp/v2" if site else ""
        self.auth = (
            os.getenv("SCRAPER_WC_CONSUMER_KEY") or os.getenv("SCRAPER_WOOCOMMERCE_KEY", ""),
            os.getenv("SCRAPER_WC_CONSUMER_SECRET") or os.getenv("SCRAPER_WOOCOMMERCE_SECRET", ""),
        )
        self.wp_auth = (
            os.getenv("SCRAPER_WP_USERNAME") or os.getenv("SCRAPER_WORDPRESS_USER", ""),
            os.getenv("SCRAPER_WP_APPLICATION_PASSWORD") or os.getenv("SCRAPER_WORDPRESS_APPLICATION_PASSWORD", ""),
        )
        self.session = session or requests.Session()
        self.timeout = 60

    def _wc(self, method, path, **kwargs):
        if not self.wc or not all(self.auth):
            raise RuntimeError("Credenciais WooCommerce não configuradas")
        response = self.session.request(method, self.wc + path, auth=self.auth, timeout=self.timeout, **kwargs)
        response.raise_for_status()
        return response.json()

    def reconcile(self, job):
        if int(job.get("woo_product_id") or 0):
            return int(job["woo_product_id"])
        for product in self._wc("GET", "/products", params={"search": job["product_name"], "per_page": 100}):
            if any(
                str(meta.get("key")) == "crapscraper_addition_job" and str(meta.get("value")) == job["job_id"]
                for meta in product.get("meta_data", []) or []
            ):
                return int(product["id"])
        return 0

    @staticmethod
    def _term_slug(name):
        normalized = unicodedata.normalize("NFKD", str(name or ""))
        ascii_name = "".join(char for char in normalized if not unicodedata.combining(char))
        slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.casefold()).strip("-")
        return slug[:190]

    @staticmethod
    def _term_exists_id(error):
        if not isinstance(error, requests.HTTPError):
            return 0
        response = getattr(error, "response", None)
        try:
            payload = response.json() if response is not None else {}
        except Exception:
            payload = {}
        if str(payload.get("code") or "") not in {"term_exists", "woocommerce_rest_term_exists"}:
            return 0
        data = payload.get("data") or {}
        for key in ("resource_id", "term_id", "id"):
            value = data.get(key)
            if str(value or "").isdigit():
                return int(value)
        return 0

    def _term(self, kind, name):
        endpoint = "categories" if kind == "category" else "tags"
        expected = str(name or "").strip()
        if not expected:
            raise RuntimeError("Termo WooCommerce vazio")
        slug = self._term_slug(expected)
        rows = []
        if slug:
            try:
                rows = self._wc("GET", f"/products/{endpoint}", params={"slug": slug, "per_page": 100})
            except requests.HTTPError as exc:
                status = int(getattr(getattr(exc, "response", None), "status_code", 0) or 0)
                if status not in {401, 403}:
                    raise
        for row in rows:
            if str(row.get("name") or "").casefold() == expected.casefold() or str(row.get("slug") or "").casefold() == slug.casefold():
                return int(row["id"])
        if not rows:
            try:
                rows = self._wc("GET", f"/products/{endpoint}", params={"per_page": 100})
            except requests.HTTPError as exc:
                status = int(getattr(getattr(exc, "response", None), "status_code", 0) or 0)
                if status not in {401, 403}:
                    raise
                rows = []
            for row in rows:
                if str(row.get("name") or "").casefold() == expected.casefold() or str(row.get("slug") or "").casefold() == slug.casefold():
                    return int(row["id"])
        try:
            created = self._wc("POST", f"/products/{endpoint}", json={"name": expected})
            return int(created["id"])
        except requests.HTTPError as exc:
            existing = self._term_exists_id(exc)
            if existing:
                return existing
            raise

    @staticmethod
    def media_upload_fallback_allowed(error):
        if isinstance(error, requests.HTTPError):
            response = getattr(error, "response", None)
            return int(getattr(response, "status_code", 0) or 0) in {401, 403}
        return isinstance(error, RuntimeError) and "Credenciais WordPress não configuradas" in str(error)

    def upload_media(self, path: Path, title: str):
        if not self.wp or not all(self.wp_auth):
            raise RuntimeError("Credenciais WordPress não configuradas")
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        headers = {"Content-Disposition": f'attachment; filename="{path.name}"', "Content-Type": mime}
        response = self.session.post(self.wp + "/media", auth=self.wp_auth, headers=headers, data=path.read_bytes(), timeout=120)
        response.raise_for_status()
        media = response.json()
        self.session.post(
            self.wp + f"/media/{media['id']}",
            auth=self.wp_auth,
            json={"title": title, "alt_text": title},
            timeout=60,
        ).raise_for_status()
        return int(media["id"])

    def create_parent(self, job, media_id, download_ref, image_url=""):
        category_names = list(job.get("categories") or []) or (["Temas"] if job["kind"] == "theme" else ["Plugins"])
        categories = [{"id": self._term("category", name)} for name in category_names]
        tags = [{"id": self._term("tag", name)} for name in job.get("tags", [])]
        attribute = int(os.getenv("SCRAPER_WOOCOMMERCE_PLAN_ATTRIBUTE_ID", "4"))
        status = "draft"
        images = [{"id": int(media_id)}] if int(media_id or 0) else ([{"src": str(image_url)}] if str(image_url or "").strip() else [])
        if not images:
            raise RuntimeError("Imagem principal não disponível para criação do produto")
        payload = {
            "name": job["product_name"],
            "type": "variable",
            "status": status,
            "description": job["content"],
            "short_description": job["short_description"],
            "categories": categories,
            "tags": tags,
            "images": images,
            "attributes": [{"id": attribute, "visible": True, "variation": True, "options": ["Anual", "Vitalício"]}],
            "meta_data": [
                {"key": "pt_versao", "value": job["source_version"]},
                {"key": "site_oficial", "value": job["official_url"]},
                {"key": "desenvolvedor", "value": job["developer"]},
                {"key": "crapscraper_addition_job", "value": job["job_id"]},
                {"key": "fonte_crapscraper", "value": job["source_name"]},
            ],
        }
        return self._wc("POST", "/products", json=payload)

    def ensure_variations(self, product_id, job, download_ref):
        existing = self._wc("GET", f"/products/{product_id}/variations", params={"per_page": 100})
        attribute = int(os.getenv("SCRAPER_WOOCOMMERCE_PLAN_ATTRIBUTE_ID", "4"))
        prices = {
            "Anual": os.getenv("SCRAPER_ADDITION_ANNUAL_PRICE", "0.00"),
            "Vitalício": os.getenv("SCRAPER_ADDITION_LIFETIME_PRICE", "0.00"),
        }
        ids = []
        by_option = {}
        for variation in existing:
            option = next(
                (str(item.get("option") or "") for item in variation.get("attributes", []) if int(item.get("id") or 0) == attribute),
                "",
            )
            if option:
                by_option[option.casefold()] = int(variation["id"])
        for option in ("Anual", "Vitalício"):
            if option.casefold() in by_option:
                ids.append(by_option[option.casefold()])
                continue
            payload = {
                "status": "publish",
                "regular_price": prices[option],
                "virtual": True,
                "downloadable": True,
                "download_limit": -1,
                "download_expiry": -1,
                "attributes": [{"id": attribute, "option": option}],
                "downloads": [{"name": Path(download_ref).name, "file": download_ref}],
            }
            ids.append(int(self._wc("POST", f"/products/{product_id}/variations", json=payload)["id"]))
        return ids

    def set_status(self, product_id, status):
        self._wc("PUT", f"/products/{product_id}", json={"status": status})

    def validate(self, product_id, job, variation_ids):
        product = self._wc("GET", f"/products/{product_id}")
        variations = self._wc("GET", f"/products/{product_id}/variations", params={"per_page": 100})
        meta = {str(item.get("key")): str(item.get("value")) for item in product.get("meta_data", [])}
        return (
            product.get("type") == "variable"
            and bool(product.get("images"))
            and meta.get("pt_versao") == job["source_version"]
            and meta.get("crapscraper_addition_job") == job["job_id"]
            and len(variations) == 2
            and all(variation.get("virtual") and variation.get("downloadable") and len(variation.get("downloads") or []) == 1 for variation in variations)
        )


class ArtifactPublisher:
    def __init__(self):
        self.local = Path(os.getenv("SCRAPER_ADDITION_DOWNLOAD_DIR", "")).resolve() if os.getenv("SCRAPER_ADDITION_DOWNLOAD_DIR") else None

    def _public_base(self):
        base = os.getenv("SCRAPER_DOWNLOAD_PUBLIC_BASE_URL", "").rstrip("/")
        if not base and os.getenv("SCRAPER_WP_BASE_URL"):
            base = os.getenv("SCRAPER_WP_BASE_URL", "").rstrip("/") + "/downloads"
        return base

    def _publish_as(self, path: Path, name: str):
        base = self._public_base()
        if self.local:
            self.local.mkdir(parents=True, exist_ok=True)
            target = self.local / name
            temp = target.with_suffix(target.suffix + ".upload")
            shutil.copy2(path, temp)
            os.replace(temp, target)
            return f"{base}/{name}" if base else str(target)
        import paramiko

        host = os.getenv("SCRAPER_SSH_HOST", "")
        user = os.getenv("SCRAPER_SSH_USER", "")
        root = os.getenv("SCRAPER_SSH_DOWNLOAD_ROOT", "").rstrip("/")
        if not host or not user or not root:
            raise RuntimeError("Destino de download não configurado")
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        kwargs = {
            "hostname": host,
            "port": int(os.getenv("SCRAPER_SSH_PORT", "22")),
            "username": user,
            "timeout": 30,
        }
        key = os.getenv("SCRAPER_SSH_KEY_PATH", "")
        password = os.getenv("SCRAPER_SSH_PASSWORD", "")
        kwargs.update({"key_filename": key} if key else {"password": password})
        client.connect(**kwargs)
        sftp = client.open_sftp()
        remote = f"{root}/{name}"
        temp = remote + ".upload"
        try:
            sftp.put(str(path), temp)
            getattr(sftp, "posix_rename", sftp.rename)(temp, remote)
        finally:
            try:
                sftp.remove(temp)
            except OSError:
                pass
            sftp.close()
            client.close()
        return f"{base}/{name}" if base else remote

    def publish(self, job, path: Path):
        return self._publish_as(path, f"{job['job_id']}-{path.name}")

    def publish_image(self, job, path: Path):
        suffix = path.suffix.lower() or ".png"
        return self._publish_as(path, f"{job['job_id']}-product-image{suffix}")
