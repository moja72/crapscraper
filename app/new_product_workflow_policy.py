from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping
from urllib.parse import quote
from urllib.request import Request
from uuid import uuid4

import app.web as web
from app import settings
from app.comparison_decisions import list_approved_additions
from app.integrations.wordpress import IntegrationError, sanitize_text

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_BASE_HTTP_SERVER: Any = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "new_product_workflow.js"
_DB_LOCK = threading.RLock()
_DB_PATH = Path(settings.DATA_DIR) / "addition_jobs.sqlite3"
_STAGING_ROOT = Path(settings.DATA_DIR) / "staging" / "additions"
_IMAGE_ROOT = Path(settings.DATA_DIR) / "addition_images"

_STATES = {
    "awaiting_content": "Aguardando conteúdo",
    "content_ready": "Conteúdo pronto",
    "file_ready": "Arquivo pronto",
    "ready_to_create": "Pronto para criar",
    "draft_created": "Rascunho criado",
    "published": "Publicado",
    "completed": "Concluído",
    "blocked": "Bloqueado",
    "error": "Erro",
}

_STYLE = r"""
<style data-new-product-workflow>
#tab_panel_adicoes .addition-shell{display:grid;gap:16px}
#tab_panel_adicoes .addition-summary{display:grid;grid-template-columns:repeat(7,minmax(100px,1fr));gap:8px}
#tab_panel_adicoes .addition-kpi{border:1px solid var(--line);border-radius:12px;padding:12px;background:rgba(255,255,255,.015)}
#tab_panel_adicoes .addition-kpi strong{display:block;font-size:22px}.addition-kpi span{color:var(--text-muted);font-size:11px}
#tab_panel_adicoes .addition-toolbar{display:grid;grid-template-columns:minmax(0,1fr) 230px auto;gap:10px;align-items:end}
#tab_panel_adicoes .addition-list{display:grid;gap:12px}
#tab_panel_adicoes .addition-item{border:1px solid var(--line);border-radius:14px;padding:14px;background:rgba(255,255,255,.012)}
#tab_panel_adicoes .addition-item-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}
#tab_panel_adicoes .addition-title{font-weight:800;font-size:15px}.addition-meta{color:var(--text-muted);font-size:12px;line-height:1.5}
#tab_panel_adicoes .addition-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
#tab_panel_adicoes .addition-actions button{min-height:36px;padding:8px 11px;font-size:12px}
#tab_panel_adicoes .addition-state{display:inline-flex;align-items:center;padding:5px 9px;border-radius:999px;border:1px solid var(--line);font-size:11px;font-weight:800;white-space:nowrap}
#tab_panel_adicoes .addition-state.is-ready,#tab_panel_adicoes .addition-state.is-done{border-color:rgba(16,185,129,.4);color:#9ff4d1;background:rgba(16,185,129,.1)}
#tab_panel_adicoes .addition-state.is-warn{border-color:rgba(245,158,11,.4);color:#ffd791;background:rgba(245,158,11,.08)}
#tab_panel_adicoes .addition-state.is-error{border-color:rgba(239,68,68,.45);color:#ffc1c1;background:rgba(239,68,68,.08)}
#addition_editor_modal{position:fixed;inset:0;z-index:1500;display:none;align-items:center;justify-content:center;padding:20px;background:rgba(0,0,0,.76)}
#addition_editor_modal.is-open{display:flex}#addition_editor_modal .addition-modal-card{width:min(1040px,96vw);max-height:92vh;overflow:auto;border:1px solid var(--line-strong);border-radius:18px;background:#0c0c0e;padding:18px;box-shadow:0 24px 80px rgba(0,0,0,.55)}
#addition_editor_modal .addition-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
#addition_editor_modal .addition-grid .wide{grid-column:1/-1}#addition_editor_modal textarea{min-height:130px}
#addition_editor_modal .addition-modal-actions{display:flex;justify-content:flex-end;flex-wrap:wrap;gap:8px;margin-top:14px}
#addition_prompt_modal{position:fixed;inset:0;z-index:1510;display:none;align-items:center;justify-content:center;padding:20px;background:rgba(0,0,0,.76)}
#addition_prompt_modal.is-open{display:flex}#addition_prompt_modal .addition-modal-card{width:min(980px,96vw);max-height:92vh;overflow:auto;border:1px solid var(--line-strong);border-radius:18px;background:#0c0c0e;padding:18px}
#addition_prompt_text{min-height:420px;font-family:Consolas,monospace;font-size:12px}
#tab_panel_adicoes .addition-progress{margin-top:9px;padding:9px 10px;border:1px solid var(--line);border-radius:10px;color:var(--text-muted);font-size:12px;white-space:pre-wrap}
@media(max-width:980px){#tab_panel_adicoes .addition-summary{grid-template-columns:repeat(3,1fr)}#tab_panel_adicoes .addition-toolbar{grid-template-columns:1fr}#addition_editor_modal .addition-grid{grid-template-columns:1fr}#addition_editor_modal .addition-grid .wide{grid-column:auto}}
</style>
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _slug(value: Any) -> str:
    text = _normalize(value).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return re.sub(r"-{2,}", "-", text).strip("-") or "produto"


def _safe_job_id(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9_-]+", "-", _normalize(value))
    return text[:80] or uuid4().hex


def _guess_kind(row: Mapping[str, Any]) -> str:
    haystack = " ".join(
        str(row.get(key, "") or "")
        for key in ("source_product_url", "source_name", "recommended_action", "status")
    ).lower()
    if any(token in haystack for token in ("/temas/", "themeforest", " wordpress theme", " theme")):
        return "theme"
    return "plugin"


@contextmanager
def _db():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _DB_LOCK:
        connection = sqlite3.connect(str(_DB_PATH), timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        try:
            _initialize(connection)
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def _initialize(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS addition_jobs (
            job_id TEXT PRIMARY KEY,
            comparison_item_id TEXT NOT NULL UNIQUE,
            state TEXT NOT NULL DEFAULT 'awaiting_content',
            kind TEXT NOT NULL DEFAULT 'plugin',
            source_name TEXT NOT NULL DEFAULT '',
            source_version TEXT NOT NULL DEFAULT '',
            source_product_url TEXT NOT NULL DEFAULT '',
            source_official_url TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            short_description TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            seo_title TEXT NOT NULL DEFAULT '',
            meta_description TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '',
            image_path TEXT NOT NULL DEFAULT '',
            zip_path TEXT NOT NULL DEFAULT '',
            zip_name TEXT NOT NULL DEFAULT '',
            zip_sha256 TEXT NOT NULL DEFAULT '',
            zip_size INTEGER NOT NULL DEFAULT 0,
            annual_regular TEXT NOT NULL DEFAULT '',
            annual_sale TEXT NOT NULL DEFAULT '',
            lifetime_regular TEXT NOT NULL DEFAULT '',
            lifetime_sale TEXT NOT NULL DEFAULT '',
            remote_file_name TEXT NOT NULL DEFAULT '',
            remote_file_path TEXT NOT NULL DEFAULT '',
            woo_product_id INTEGER NOT NULL DEFAULT 0,
            media_id INTEGER NOT NULL DEFAULT 0,
            error TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_addition_jobs_state ON addition_jobs(state);
        """
    )


def _sync_approved() -> None:
    approved = list_approved_additions()
    now = _utc_now()
    with _db() as connection:
        for row in approved:
            comparison_item_id = _normalize(row.get("comparison_item_id"))
            if not comparison_item_id:
                continue
            job_id = "add-" + hashlib.sha1(comparison_item_id.encode("utf-8")).hexdigest()[:16]
            connection.execute(
                """
                INSERT INTO addition_jobs (
                    job_id, comparison_item_id, state, kind, source_name,
                    source_version, source_product_url, source_official_url,
                    title, created_at, updated_at
                ) VALUES (?, ?, 'awaiting_content', ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(comparison_item_id) DO UPDATE SET
                    source_name=excluded.source_name,
                    source_version=excluded.source_version,
                    source_product_url=excluded.source_product_url,
                    source_official_url=excluded.source_official_url,
                    updated_at=excluded.updated_at
                """,
                (
                    job_id, comparison_item_id, _guess_kind(row),
                    _normalize(row.get("source_name")), _normalize(row.get("source_version")),
                    _normalize(row.get("source_product_url")), _normalize(row.get("source_official_url")),
                    _normalize(row.get("source_name")), now, now,
                ),
            )


def _row(job_id: str) -> dict[str, Any]:
    with _db() as connection:
        row = connection.execute("SELECT * FROM addition_jobs WHERE job_id=?", (job_id,)).fetchone()
    if not row:
        raise ValueError("Cadastro novo não encontrado.")
    return dict(row)


def _update(job_id: str, **values: Any) -> dict[str, Any]:
    if not values:
        return _row(job_id)
    values["updated_at"] = _utc_now()
    columns = ", ".join(f"{key}=?" for key in values)
    with _db() as connection:
        connection.execute(
            f"UPDATE addition_jobs SET {columns} WHERE job_id=?",
            tuple(values.values()) + (job_id,),
        )
    return _row(job_id)


def _content_complete(job: Mapping[str, Any]) -> bool:
    return bool(
        _normalize(job.get("title"))
        and _normalize(job.get("short_description"))
        and _normalize(job.get("description"))
    )


def _recalculate_state(job_id: str) -> dict[str, Any]:
    job = _row(job_id)
    if job.get("state") in {"draft_created", "published", "completed"}:
        return job
    content = _content_complete(job)
    file_ready = bool(_normalize(job.get("zip_path")) and Path(str(job.get("zip_path"))).exists())
    state = "ready_to_create" if content and file_ready else "content_ready" if content else "file_ready" if file_ready else "awaiting_content"
    return _update(job_id, state=state, error="")


def _prompt(job: Mapping[str, Any]) -> str:
    kind_label = "tema WordPress" if job.get("kind") == "theme" else "plugin WordPress"
    return f"""Você está preparando o conteúdo editorial de um novo produto para o e-commerce PluginTema.

PRODUTO
Nome de origem: {job.get('source_name') or '-'}
Tipo: {kind_label}
Versão: {job.get('source_version') or '-'}
Página da fonte: {job.get('source_product_url') or '-'}
Página oficial: {job.get('source_official_url') or '-'}

OBJETIVO
Produza conteúdo original em português do Brasil para cadastrar este produto. Não invente recursos, integrações, compatibilidades ou números que não possam ser inferidos com segurança das informações disponíveis. Se algum ponto técnico não estiver confirmado, use linguagem neutra e não o apresente como fato.

ENTREGUE NESTA ORDEM
1. Título comercial limpo, sem versão no título.
2. Breve descrição com 2 a 3 frases, objetiva e útil.
3. Descrição completa em HTML simples, com introdução, principais possibilidades, público indicado e observações de uso. Evite promessas exageradas.
4. Título SEO com até aproximadamente 60 caracteres.
5. Meta description com até aproximadamente 155 caracteres.
6. De 4 a 8 tags relevantes, separadas por vírgula.
7. Gere também uma imagem quadrada 1:1, limpa, profissional, sem selos de preço, sem texto pequeno ilegível e sem copiar identidade visual protegida de terceiros. A imagem deve funcionar como capa de produto em uma loja de plugins e temas WordPress.

Ao final, repita os campos textuais em um bloco fácil de copiar para o CrapScraper, usando os rótulos: TÍTULO, BREVE DESCRIÇÃO, DESCRIÇÃO, TÍTULO SEO, META DESCRIPTION e TAGS."""


def _public_job(job: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(job)
    result["state_label"] = _STATES.get(str(job.get("state")), str(job.get("state")))
    result["content_complete"] = _content_complete(job)
    result["zip_exists"] = bool(job.get("zip_path") and Path(str(job.get("zip_path"))).exists())
    result["prompt"] = _prompt(job)
    return result


def _price_defaults() -> dict[str, str]:
    defaults = {"annual_regular": "", "annual_sale": "", "lifetime_regular": "", "lifetime_sale": ""}
    try:
        from app.store_pricing import read_store_price_reference_products, variation_period
        woo = web._build_store_woocommerce_client()
        refs = read_store_price_reference_products(Path(settings.COMPARISON_IMPORTS_DIR), ("plugin",), limit_per_kind=1)
        if not refs:
            return defaults
        variations = woo.list_variations(int(refs[0]["id"]), per_page=100)
        for variation in variations:
            period = variation_period(variation)
            if period not in {"annual", "lifetime"}:
                continue
            defaults[f"{period}_regular"] = str(variation.get("regular_price", "") or "")
            defaults[f"{period}_sale"] = str(variation.get("sale_price", "") or "")
    except Exception:
        pass
    return defaults


def _snapshot() -> dict[str, Any]:
    _sync_approved()
    with _db() as connection:
        rows = [dict(row) for row in connection.execute("SELECT * FROM addition_jobs ORDER BY updated_at DESC").fetchall()]
    counts = {key: 0 for key in _STATES}
    for row in rows:
        counts[str(row.get("state", ""))] = counts.get(str(row.get("state", "")), 0) + 1
    return {
        "ok": True,
        "jobs": [_public_job(row) for row in rows],
        "counts": counts,
        "total": len(rows),
        "price_defaults": _price_defaults(),
    }


def _save_content(payload: Mapping[str, Any]) -> dict[str, Any]:
    job_id = _normalize(payload.get("job_id"))
    if not job_id:
        raise ValueError("job_id obrigatório.")
    values = {
        "kind": "theme" if _normalize(payload.get("kind")).lower() == "theme" else "plugin",
        "title": _normalize(payload.get("title")),
        "short_description": str(payload.get("short_description", "") or "").strip(),
        "description": str(payload.get("description", "") or "").strip(),
        "seo_title": _normalize(payload.get("seo_title")),
        "meta_description": _normalize(payload.get("meta_description")),
        "tags": _normalize(payload.get("tags")),
        "annual_regular": _normalize(payload.get("annual_regular")),
        "annual_sale": _normalize(payload.get("annual_sale")),
        "lifetime_regular": _normalize(payload.get("lifetime_regular")),
        "lifetime_sale": _normalize(payload.get("lifetime_sale")),
        "error": "",
    }
    image_data = str(payload.get("image_base64", "") or "").strip()
    image_name = _normalize(payload.get("image_name"))
    if image_data:
        if "," in image_data and image_data.lower().startswith("data:"):
            image_data = image_data.split(",", 1)[1]
        binary = base64.b64decode(image_data, validate=True)
        if len(binary) > 12 * 1024 * 1024:
            raise ValueError("Imagem excede 12 MB.")
        suffix = Path(image_name).suffix.lower() if image_name else ".png"
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            suffix = ".png"
        _IMAGE_ROOT.mkdir(parents=True, exist_ok=True)
        image_path = _IMAGE_ROOT / f"{_safe_job_id(job_id)}{suffix}"
        image_path.write_bytes(binary)
        values["image_path"] = str(image_path)
    _update(job_id, **values)
    job = _recalculate_state(job_id)
    return {"ok": True, "message": "Conteúdo salvo.", "job": _public_job(job)}


def _manager_from_handler(handler_class: type) -> Any:
    for method_name in ("_route_get", "_route_post", "do_GET"):
        method = getattr(handler_class, method_name, None)
        closure = getattr(method, "__closure__", None)
        freevars = getattr(getattr(method, "__code__", None), "co_freevars", ())
        if not closure:
            continue
        mapping = {name: cell.cell_contents for name, cell in zip(freevars, closure)}
        if "manager" in mapping:
            return mapping["manager"]
    return None


def _download_source(job_id: str, manager: Any) -> dict[str, Any]:
    job = _row(job_id)
    source_url = _normalize(job.get("source_product_url"))
    if not source_url:
        raise ValueError("A decisão aprovada não possui URL de origem persistida. Restaure e aprove novamente o item na Comparação.")
    primary = web._get_primary_app(manager) if manager is not None else None
    if primary is None:
        raise ValueError("Execução principal não disponível para autenticar a fonte.")
    from app.integrations.plugintheme_download import PluginThemeDownloader, SourceDownloader
    from app.integrations.ultrapack_download import UltrapackDownloader
    from app.integrations.ultrapack_session import get_authenticated_plugintheme_session, get_authenticated_ultrapack_session

    source = SourceDownloader(UltrapackDownloader(None), PluginThemeDownloader(None))
    auth = (
        get_authenticated_plugintheme_session(primary, source_url)
        if SourceDownloader.is_plugintheme(source_url)
        else get_authenticated_ultrapack_session(primary, source_url)
    )
    source.session = auth.session
    staging_dir = _STAGING_ROOT / _safe_job_id(job_id)
    staging_dir.mkdir(parents=True, exist_ok=True)
    artifact, detected_version = source.download(source_url, staging_dir)
    expected = _normalize(job.get("source_version"))
    detected = _normalize(detected_version)
    if expected and detected and expected != detected:
        _update(job_id, state="blocked", error=f"Versão da fonte mudou: aprovado {expected}, download atual {detected}.")
        raise ValueError(f"A versão da fonte mudou de {expected} para {detected}. Revise a comparação antes de cadastrar.")
    _update(
        job_id,
        zip_path=artifact.path,
        zip_name=artifact.file_name,
        zip_sha256=artifact.sha256,
        zip_size=int(artifact.size),
        source_version=detected or expected,
        error="",
    )
    job = _recalculate_state(job_id)
    return {"ok": True, "message": "ZIP preparado e validado.", "job": _public_job(job)}


def _wc_request(client: Any, method: str, path: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
    url = client.base_url.rstrip("/") + "/" + path.lstrip("/")
    body = json.dumps(dict(payload), ensure_ascii=False).encode("utf-8")
    request = Request(url, data=body, method=method.upper(), headers={
        "Accept": "application/json",
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": client._authorization(),
        "User-Agent": "CrapScraper-new-product/1.0",
    })
    try:
        status, _headers, response_body = client.transport(request, client.timeout)
        if status >= 400:
            message = response_body.decode("utf-8", "replace")[:800] if response_body else ""
            raise IntegrationError(f"WooCommerce recusou o cadastro: HTTP {status} {message}")
        decoded = json.loads(response_body) if response_body else {}
    except Exception as error:
        if isinstance(error, IntegrationError):
            raise
        raise IntegrationError("Falha no WooCommerce: " + sanitize_text(error, client.username, client.password)) from None
    if not isinstance(decoded, Mapping):
        raise IntegrationError("WooCommerce retornou resposta inválida.")
    return decoded


def _wp_media_upload(image_path: str, title: str) -> int:
    path = Path(image_path)
    if not path.exists():
        return 0
    base_url = os.getenv("SCRAPER_WP_BASE_URL", "").strip().rstrip("/")
    username = os.getenv("SCRAPER_WP_USERNAME", "").strip()
    password = os.getenv("SCRAPER_WP_APPLICATION_PASSWORD", "").strip()
    if not base_url or not username or not password:
        return 0
    import base64 as _b64
    auth = _b64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    request = Request(
        base_url + "/wp-json/wp/v2/media",
        data=path.read_bytes(),
        method="POST",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": mime,
            "Content-Disposition": f'attachment; filename="{path.name}"',
            "User-Agent": "CrapScraper-new-product-media/1.0",
        },
    )
    from urllib.request import urlopen
    try:
        with urlopen(request, timeout=60) as response:
            payload = json.loads(response.read() or b"{}")
        return int(payload.get("id") or 0)
    except Exception:
        return 0


def _category_id(woo: Any, kind: str) -> int:
    targets = {"plugin", "plugins"} if kind == "plugin" else {"tema", "temas", "theme", "themes"}
    page = 1
    while True:
        batch = list(woo.list_product_categories(page=page, per_page=100) or [])
        for item in batch:
            name = re.sub(r"[^a-z]+", " ", str(item.get("name", "") or "").lower()).strip()
            if name in targets:
                return int(item.get("id") or 0)
        if len(batch) < 100:
            break
        page += 1
    return 0


def _duplicate_product(woo: Any, title: str) -> Mapping[str, Any] | None:
    wanted = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    for product in woo.search_products(title, per_page=30):
        current = re.sub(r"[^a-z0-9]+", " ", str(product.get("name", "") or "").lower()).strip()
        if wanted and current == wanted:
            return product
    return None


def _upload_zip(job: Mapping[str, Any]) -> tuple[str, str]:
    local_path = Path(str(job.get("zip_path") or ""))
    if not local_path.exists():
        raise ValueError("ZIP local não encontrado. Prepare o arquivo novamente.")
    version = _normalize(job.get("source_version")) or "latest"
    filename = f"{_slug(job.get('title') or job.get('source_name'))}-{_slug(version)}.zip"
    target = str(PurePosixPath(settings.SSH_DOWNLOAD_ROOT) / filename)
    from app.integrations.ssh_storage import ControlledWriteSSHStorage, ReadOnlySSHStorage
    with ReadOnlySSHStorage.from_env() as reader:
        if reader.exists(target):
            remote_sha = reader.sha256(target)
            if remote_sha != str(job.get("zip_sha256") or ""):
                raise ValueError("Já existe um ZIP remoto com este nome e conteúdo diferente. Altere/revise o cadastro antes de continuar.")
        else:
            writer = ControlledWriteSSHStorage.from_env(
                job_id=_safe_job_id(str(job.get("job_id"))), target_path=target, write_authorized=True,
            )
            with writer:
                with local_path.open("rb") as source:
                    writer.upload(source, writer.temporary_path)
                uploaded_sha = writer.sha256(writer.temporary_path)
                if uploaded_sha != str(job.get("zip_sha256") or ""):
                    writer.delete_temporary(writer.temporary_path)
                    raise ValueError("SHA-256 do ZIP remoto não confere com o arquivo preparado.")
                writer.rename(writer.temporary_path, writer.target_path)
    base_url = os.getenv("SCRAPER_WP_BASE_URL", "https://plugintema.com").strip().rstrip("/")
    return filename, base_url + "/downloads/" + quote(filename)


def _create_or_resume_draft(job_id: str, confirmation: str) -> dict[str, Any]:
    job = _recalculate_state(job_id)
    if confirmation.strip() != "CRIAR RASCUNHO":
        raise ValueError('Digite "CRIAR RASCUNHO" para confirmar a escrita no WooCommerce.')
    if job.get("state") not in {"ready_to_create", "draft_created", "error", "blocked"}:
        raise ValueError("O produto ainda precisa de conteúdo e ZIP válidos antes de criar o rascunho.")
    if not _content_complete(job):
        raise ValueError("Conteúdo incompleto.")
    if not Path(str(job.get("zip_path") or "")).exists():
        raise ValueError("ZIP preparado não está mais disponível.")

    woo = web._build_store_woocommerce_client()
    existing_id = int(job.get("woo_product_id") or 0)
    if not existing_id:
        duplicate = _duplicate_product(woo, str(job.get("title") or job.get("source_name") or ""))
        if duplicate:
            _update(job_id, state="blocked", error=f"Produto com o mesmo nome já existe no WooCommerce: #{duplicate.get('id')}.")
            raise ValueError(f"Já existe um produto com o mesmo nome no WooCommerce: #{duplicate.get('id')}.")

    filename, download_url = _upload_zip(job)
    media_id = int(job.get("media_id") or 0)
    if not media_id and job.get("image_path"):
        media_id = _wp_media_upload(str(job.get("image_path")), str(job.get("title") or ""))

    category_id = _category_id(woo, str(job.get("kind") or "plugin"))
    title = str(job.get("title") or job.get("source_name") or "Novo produto")
    if not existing_id:
        product_payload: dict[str, Any] = {
            "name": title,
            "type": "variable",
            "status": "draft",
            "description": str(job.get("description") or ""),
            "short_description": str(job.get("short_description") or ""),
            "attributes": [{
                "name": "Plano", "position": 0, "visible": True, "variation": True,
                "options": ["Anual", "Vitalício"],
            }],
            "meta_data": [
                {"key": "pt_versao", "value": str(job.get("source_version") or "")},
                {"key": "crapscraper_source_url", "value": str(job.get("source_product_url") or "")},
                {"key": "crapscraper_addition_job", "value": job_id},
                {"key": "_yoast_wpseo_title", "value": str(job.get("seo_title") or "")},
                {"key": "_yoast_wpseo_metadesc", "value": str(job.get("meta_description") or "")},
            ],
        }
        if category_id:
            product_payload["categories"] = [{"id": category_id}]
        if media_id:
            product_payload["images"] = [{"id": media_id}]
        product = _wc_request(woo, "POST", "/wp-json/wc/v3/products", product_payload)
        existing_id = int(product.get("id") or 0)
        if not existing_id:
            raise ValueError("WooCommerce não retornou o ID do rascunho criado.")
        _update(job_id, woo_product_id=existing_id, media_id=media_id)

    existing_variations = list(woo.list_variations(existing_id, per_page=100) or [])
    periods = set()
    try:
        from app.store_pricing import variation_period
        periods = {variation_period(item) for item in existing_variations}
    except Exception:
        periods = set()
    for period, option in (("annual", "Anual"), ("lifetime", "Vitalício")):
        if period in periods:
            continue
        regular = _normalize(job.get(f"{period}_regular"))
        sale = _normalize(job.get(f"{period}_sale"))
        if not regular:
            raise ValueError(f"Informe o preço original da variação {option}.")
        variation_payload = {
            "regular_price": regular,
            "sale_price": sale,
            "downloadable": True,
            "virtual": True,
            "attributes": [{"name": "Plano", "option": option}],
            "downloads": [{"name": filename, "file": download_url}],
        }
        _wc_request(woo, "POST", f"/wp-json/wc/v3/products/{existing_id}/variations", variation_payload)

    product = woo.get_product_fresh(existing_id)
    variations = list(woo.list_variations_fresh(existing_id, per_page=100) or [])
    if str(product.get("status") or "") != "draft" or len(variations) < 2:
        raise ValueError("Rascunho criado, mas a validação final das duas variações falhou.")
    job = _update(
        job_id,
        state="draft_created",
        woo_product_id=existing_id,
        media_id=media_id,
        remote_file_name=filename,
        remote_file_path=download_url,
        error="",
    )
    return {"ok": True, "message": f"Rascunho WooCommerce #{existing_id} criado e validado.", "job": _public_job(job)}


def _publish(job_id: str, confirmation: str) -> dict[str, Any]:
    job = _row(job_id)
    product_id = int(job.get("woo_product_id") or 0)
    if not product_id or job.get("state") not in {"draft_created", "published"}:
        raise ValueError("Nenhum rascunho válido está pronto para publicação.")
    expected = f"PUBLICAR {product_id}"
    if confirmation.strip() != expected:
        raise ValueError(f'Digite "{expected}" para confirmar a publicação.')
    woo = web._build_store_woocommerce_client()
    _wc_request(woo, "PUT", f"/wp-json/wc/v3/products/{product_id}", {"status": "publish"})
    product = woo.get_product_fresh(product_id)
    variations = list(woo.list_variations_fresh(product_id, per_page=100) or [])
    if str(product.get("status") or "") != "publish" or len(variations) < 2:
        raise ValueError("WooCommerce não confirmou a publicação com as duas variações.")
    job = _update(job_id, state="completed", completed_at=_utc_now(), error="")
    return {"ok": True, "message": f"Produto #{product_id} publicado e concluído.", "job": _public_job(job)}


def _reset_job(job_id: str) -> dict[str, Any]:
    job = _row(job_id)
    if int(job.get("woo_product_id") or 0):
        raise ValueError("Este job já possui rascunho no WooCommerce e não pode ser apagado localmente sem revisão.")
    with _db() as connection:
        connection.execute("DELETE FROM addition_jobs WHERE job_id=?", (job_id,))
    _sync_approved()
    return {"ok": True, "message": "Job local reconstruído a partir da aprovação atual."}


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return html
    block = _STYLE + f"\n<script data-new-product-workflow-script>\n{script}\n</script>\n"
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def _server_factory(server_address: Any, handler_class: type, *args: Any, **kwargs: Any) -> Any:
    manager = _manager_from_handler(handler_class)

    class AdditionHandler(handler_class):
        def do_GET(self) -> None:
            path = self._request_path()
            if path == "/adicoes/data":
                try:
                    self._send_json(_snapshot())
                except Exception as error:
                    self._send_json({"ok": False, "message": str(error)}, code=500)
                return
            return super().do_GET()

        def do_POST(self) -> None:
            path = self._request_path()
            if not path.startswith("/adicoes/"):
                return super().do_POST()
            try:
                payload = self._read_json_body()
                if path == "/adicoes/conteudo":
                    result = _save_content(payload)
                elif path == "/adicoes/preparar-arquivo":
                    result = _download_source(_normalize(payload.get("job_id")), manager)
                elif path == "/adicoes/criar-rascunho":
                    result = _create_or_resume_draft(
                        _normalize(payload.get("job_id")), str(payload.get("confirmation", "") or "")
                    )
                elif path == "/adicoes/publicar":
                    result = _publish(
                        _normalize(payload.get("job_id")), str(payload.get("confirmation", "") or "")
                    )
                elif path == "/adicoes/resetar":
                    result = _reset_job(_normalize(payload.get("job_id")))
                elif path == "/adicoes/sincronizar":
                    _sync_approved()
                    result = _snapshot()
                else:
                    self._send_json({"ok": False, "message": "Rota de adição não encontrada."}, code=404)
                    return
                self._send_json(result)
            except ValueError as error:
                self._send_json({"ok": False, "message": str(error)}, code=400)
            except Exception as error:
                self._send_json({"ok": False, "message": sanitize_text(error)}, code=500)

    return _BASE_HTTP_SERVER(server_address, AdditionHandler, *args, **kwargs)


def install_new_product_workflow_policy() -> None:
    global _INSTALLED, _BASE_RENDER, _BASE_HTTP_SERVER
    if _INSTALLED:
        return
    _BASE_RENDER = web.render_panel_page
    _BASE_HTTP_SERVER = web.ThreadingHTTPServer
    web.render_panel_page = _patched_render_panel_page
    web.ThreadingHTTPServer = _server_factory
    _INSTALLED = True
