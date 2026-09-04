from __future__ import annotations

import html as html_module
import imghdr
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

_INSTALLED = False
_ACTIVE_ADDITION_SERVICE: Any | None = None


def _fallback_content(job: dict[str, Any]) -> dict[str, Any]:
    name = " ".join(str(job.get("product_name") or "Produto WordPress").split())
    kind = str(job.get("kind") or "plugin").strip().lower()
    kind_label = "tema" if kind == "theme" else "plugin"
    source = str(job.get("source_name") or job.get("source_kind") or "fonte aprovada").strip()
    version = str(job.get("source_version") or "").strip()
    developer = str(job.get("developer") or "").strip()
    official = str(job.get("official_url") or "").strip()
    developer_text = f" O desenvolvedor confirmado é {developer}." if developer else ""
    official_text = f" A página oficial confirmada é {official}." if official else ""
    short = (
        f"{name} é um {kind_label} para WordPress preparado para cadastro na PluginTema a partir da fonte aprovada {source}. "
        f"O CrapScraper validou a versão {version or 'informada na aprovação'}, preservou a origem do arquivo e reuniu os dados confirmados para que o produto possa ser publicado com segurança no WooCommerce."
        f"{developer_text}"
    )
    content = (
        f"<p><strong>{name}</strong> é um {kind_label} para WordPress cadastrado a partir de uma aprovação registrada no CrapScraper. "
        f"A versão considerada neste cadastro é <strong>{version or 'a versão aprovada'}</strong> e o arquivo é obtido exclusivamente da fonte aprovada <strong>{source}</strong>.</p>"
        f"<p>Antes da criação no WooCommerce, o fluxo valida a origem, a integridade do ZIP e os dados essenciais do produto. "
        f"Este texto de contingência não adiciona recursos, compatibilidades ou características que não tenham sido confirmadas pelas fontes disponíveis.</p>"
        f"<p>{developer_text.strip() or 'O desenvolvedor será mantido conforme o dado confirmado pelo processo de pesquisa.'}"
        f"{official_text}</p>"
    )
    return {
        "product_name": name,
        "short_description": short,
        "content": content,
        "categories": ["Temas" if kind == "theme" else "Plugins"],
        "tags": [],
        "developer": developer,
        "official_url": official,
        "content_origin": "deterministic_fallback",
    }


def _extract_image_url(page_url: str, page_html: str) -> str:
    patterns = (
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image(?::src)?["\']',
        r'<img[^>]+src=["\']([^"\']+)["\']',
    )
    for pattern in patterns:
        match = re.search(pattern, page_html, re.I)
        if not match:
            continue
        candidate = html_module.unescape(match.group(1)).strip()
        if not candidate or candidate.startswith("data:"):
            continue
        return urljoin(page_url, candidate)
    return ""


def _download_source_image(service: Any, job: dict[str, Any]) -> Path:
    page_url = str(job.get("source_url") or job.get("official_url") or "").strip()
    if not page_url:
        raise RuntimeError("Produto sem URL para localizar a imagem de origem")
    session = getattr(service, "session", None) or requests.Session()
    page = session.get(page_url, timeout=45, headers={"User-Agent": "Mozilla/5.0"})
    page.raise_for_status()
    image_url = _extract_image_url(page_url, page.text)
    if not image_url:
        raise RuntimeError("Imagem do produto não encontrada na página da fonte")
    response = session.get(image_url, timeout=90, headers={"User-Agent": "Mozilla/5.0", "Referer": page_url})
    response.raise_for_status()
    raw = bytes(response.content or b"")
    if len(raw) <= 1024:
        raise RuntimeError("Imagem localizada na fonte está vazia ou pequena demais")
    kind = imghdr.what(None, raw)
    extension = {"jpeg": ".jpg", "png": ".png", "webp": ".webp"}.get(str(kind or ""))
    if not extension:
        raise RuntimeError("Imagem localizada na fonte não possui formato PNG, JPEG ou WebP suportado")
    root = Path(service.root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{job['job_id']}{extension}"
    path.write_bytes(raw)
    if not service.valid(str(path)):
        path.unlink(missing_ok=True)
        raise RuntimeError("Imagem obtida da fonte não passou na validação local")
    return path


def _patch_content_and_images() -> None:
    from app.additions.chatgpt import ChatGPTContentService
    from app.additions.images import ImageService

    if not getattr(ChatGPTContentService, "_crapscraper_optional_openai", False):
        original_generate = ChatGPTContentService.generate

        def generate(self: Any, job: dict[str, Any]) -> dict[str, Any]:
            if not str(getattr(self, "api_key", "") or "").strip():
                return _fallback_content(job)
            return original_generate(self, job)

        ChatGPTContentService.generate = generate
        ChatGPTContentService._crapscraper_optional_openai = True

    if not getattr(ImageService, "_crapscraper_optional_openai", False):
        original_image_generate = ImageService.generate

        def image_generate(self: Any, job: dict[str, Any]) -> Path:
            if not str(getattr(self, "api_key", "") or "").strip():
                return _download_source_image(self, job)
            return original_image_generate(self, job)

        ImageService.generate = image_generate
        ImageService._crapscraper_optional_openai = True


def _patch_repository_listing() -> None:
    from app.additions.repository import AdditionRepository
    from app.additions.state import GROUP_STATES

    if getattr(AdditionRepository, "_crapscraper_queue_listing", False):
        return

    def list_jobs(
        self: Any,
        query: str = "",
        group: str = "",
        stage: str = "",
        page: int = 1,
        page_size: int = 5,
        sort_by: str = "date",
        sort_order: str = "desc",
    ) -> dict[str, Any]:
        filters: list[str] = []
        values: list[Any] = []
        if query:
            filters.append("(product_name LIKE ? OR source_name LIKE ? OR CAST(woo_product_id AS TEXT) LIKE ?)")
            values += [f"%{query}%"] * 3
        if group:
            if group not in GROUP_STATES:
                raise ValueError("Grupo operacional inválido")
            filters.append("public_state=?")
            values.append(GROUP_STATES[group])
        if stage:
            filters.append("stage=?")
            values.append(stage)
        where = " WHERE " + " AND ".join(filters) if filters else ""
        page = max(1, int(page))
        page_size = max(1, min(100, int(page_size)))
        order_column = "product_name COLLATE NOCASE" if str(sort_by).lower() == "name" else "created_at"
        direction = "ASC" if str(sort_order).lower() == "asc" else "DESC"
        with self.connection() as db:
            total = int(db.execute("SELECT COUNT(*) FROM addition_jobs" + where, values).fetchone()[0])
            rows = db.execute(
                "SELECT * FROM addition_jobs" + where + f" ORDER BY {order_column} {direction}, job_id ASC LIMIT ? OFFSET ?",
                values + [page_size, (page - 1) * page_size],
            ).fetchall()
            counts = {"total": int(db.execute("SELECT COUNT(*) FROM addition_jobs").fetchone()[0])}
            for group_name, public_state in GROUP_STATES.items():
                counts[group_name] = int(db.execute("SELECT COUNT(*) FROM addition_jobs WHERE public_state=?", (public_state,)).fetchone()[0])
        return {
            "items": [self.decode(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size),
            "counts": counts,
        }

    AdditionRepository.list = list_jobs
    AdditionRepository._crapscraper_queue_listing = True


def _patch_addition_service() -> None:
    from app.additions.service import AdditionService
    from app.comparison import decisions

    if getattr(AdditionService, "_crapscraper_auto_materialize", False):
        return
    original_init = AdditionService.__init__

    def init(self: Any, *args: Any, **kwargs: Any) -> None:
        global _ACTIVE_ADDITION_SERVICE
        original_init(self, *args, **kwargs)
        _ACTIVE_ADDITION_SERVICE = self

    def list_items(self: Any, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        p = payload or {}
        with self.lock:
            sync = self.repository.materialize(decisions.list_approved_additions())
        result = self.repository.list(
            str(p.get("query") or ""),
            str(p.get("group") or ""),
            str(p.get("stage") or ""),
            int(p.get("page") or 1),
            int(p.get("page_size") or 5),
            str(p.get("sort_by") or "date"),
            str(p.get("sort_order") or "desc"),
        )
        return {
            "ok": True,
            **result,
            "batch": self.batch.state(),
            "database": str(self.repository.path),
            "auto_sync": sync,
        }

    AdditionService.__init__ = init
    AdditionService.list = list_items
    AdditionService._crapscraper_auto_materialize = True


def _sync_after_new_product_approval() -> None:
    service = _ACTIVE_ADDITION_SERVICE
    if service is None:
        return
    try:
        service.materialize()
    except Exception:
        # A decisão já foi persistida. Se a materialização imediata falhar por
        # bloqueio transitório, a própria leitura da fila repete o sync.
        pass


def _patch_comparison_approval_sync() -> None:
    from app.comparison.service import ComparisonService

    if getattr(ComparisonService, "_crapscraper_addition_auto_sync", False):
        return
    original_save = ComparisonService.save_decision
    original_bulk = ComparisonService.save_decisions_bulk

    def save_decision(self: Any, payload: dict[str, Any]) -> dict[str, Any]:
        result = original_save(self, payload)
        if str(payload.get("decision") or "") == "approve_new_product":
            _sync_after_new_product_approval()
        return result

    def save_bulk(self: Any, payload: dict[str, Any]) -> dict[str, Any]:
        result = original_bulk(self, payload)
        if str(payload.get("decision") or "") == "approve_new_product":
            _sync_after_new_product_approval()
        return result

    ComparisonService.save_decision = save_decision
    ComparisonService.save_decisions_bulk = save_bulk
    ComparisonService._crapscraper_addition_auto_sync = True


def install_addition_runtime_recovery() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _patch_content_and_images()
    _patch_repository_listing()
    _patch_addition_service()
    _patch_comparison_approval_sync()
    _INSTALLED = True


__all__ = [
    "install_addition_runtime_recovery",
    "_fallback_content",
    "_extract_image_url",
]
