from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import sqlite3
import threading
import unicodedata
from contextlib import contextmanager, suppress
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from urllib.parse import quote
from urllib.request import Request, urlopen

from app import settings
from app.comparison_decisions import list_approved_additions
from app.integrations.plugintheme_download import PluginThemeDownloader, SourceDownloader
from app.integrations.ssh_storage import SSHStorageConfig
from app.integrations.ultrapack_download import UltrapackDownloader
from app.integrations.woocommerce import WooCommerceClient

DB_PATH = settings.DATA_DIR / "addition_workflow.sqlite3"
STAGING_ROOT = settings.DATA_DIR / "staging" / "additions"
IMAGE_MAX_BYTES = 8 * 1024 * 1024
_LOCK = threading.RLock()
_WORKERS: dict[str, threading.Thread] = {}

STATE_LABELS = {
    "approved": "Aguardando",
    "preparing": "Preparando arquivo",
    "awaiting_content": "Aguardando conteúdo",
    "content_ready": "Conteúdo pronto",
    "creating_draft": "Criando rascunho",
    "draft_created": "Rascunho criado",
    "publishing": "Publicando",
    "completed": "Concluído",
    "blocked": "Bloqueado",
    "error": "Erro",
}
ACTIVE_STATES = {
    "approved", "preparing", "awaiting_content", "content_ready",
    "creating_draft", "draft_created", "publishing", "blocked", "error",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join(re.findall(r"[a-z0-9]+", text.encode("ascii", "ignore").decode().lower()))


def _slug(value: Any) -> str:
    text = _fold(value).replace(" ", "-")
    text = re.sub(r"[^a-z0-9._-]+", "-", text)
    return re.sub(r"-{2,}", "-", text).strip("-._") or "produto"


def _job_id(comparison_item_id: str) -> str:
    return "add-" + hashlib.sha1(comparison_item_id.encode("utf-8")).hexdigest()[:16]


@contextmanager
def _db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        connection = sqlite3.connect(str(DB_PATH), timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=30000")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def initialize() -> None:
    with _db() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS addition_jobs (
                job_id TEXT PRIMARY KEY,
                comparison_item_id TEXT NOT NULL UNIQUE,
                state TEXT NOT NULL,
                source_name TEXT NOT NULL DEFAULT '',
                source_version TEXT NOT NULL DEFAULT '',
                source_product_url TEXT NOT NULL DEFAULT '',
                source_official_url TEXT NOT NULL DEFAULT '',
                item_type TEXT NOT NULL DEFAULT 'plugin',
                title TEXT NOT NULL DEFAULT '',
                short_description TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                meta_description TEXT NOT NULL DEFAULT '',
                tags_text TEXT NOT NULL DEFAULT '',
                image_path TEXT NOT NULL DEFAULT '',
                image_name TEXT NOT NULL DEFAULT '',
                zip_path TEXT NOT NULL DEFAULT '',
                zip_file_name TEXT NOT NULL DEFAULT '',
                zip_sha256 TEXT NOT NULL DEFAULT '',
                zip_size INTEGER NOT NULL DEFAULT 0,
                zip_entries INTEGER NOT NULL DEFAULT 0,
                remote_zip_path TEXT NOT NULL DEFAULT '',
                remote_zip_url TEXT NOT NULL DEFAULT '',
                category_id INTEGER NOT NULL DEFAULT 0,
                category_name TEXT NOT NULL DEFAULT '',
                template_product_id INTEGER NOT NULL DEFAULT 0,
                media_id INTEGER NOT NULL DEFAULT 0,
                woo_product_id INTEGER NOT NULL DEFAULT 0,
                woo_status TEXT NOT NULL DEFAULT '',
                prompt_text TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT '',
                logs_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_addition_jobs_state ON addition_jobs(state);
            """
        )


def _row(job_id: str) -> dict[str, Any] | None:
    initialize()
    with _db() as connection:
        row = connection.execute("SELECT * FROM addition_jobs WHERE job_id=?", (job_id,)).fetchone()
    return dict(row) if row else None


def _update(job_id: str, **values: Any) -> dict[str, Any]:
    if not values:
        current = _row(job_id)
        if not current:
            raise KeyError(job_id)
        return current
    values["updated_at"] = _now()
    columns = ", ".join(f"{key}=?" for key in values)
    with _db() as connection:
        connection.execute(
            f"UPDATE addition_jobs SET {columns} WHERE job_id=?",
            [*values.values(), job_id],
        )
    current = _row(job_id)
    if not current:
        raise KeyError(job_id)
    return current


def _log(job_id: str, message: str) -> None:
    current = _row(job_id)
    if not current:
        return
    try:
        logs = json.loads(current.get("logs_json") or "[]")
    except Exception:
        logs = []
    if not isinstance(logs, list):
        logs = []
    logs.append({"at": datetime.now().strftime("%H:%M:%S"), "message": str(message)})
    logs = logs[-120:]
    _update(job_id, logs_json=json.dumps(logs, ensure_ascii=False))


def _infer_item_type(source_name: str, source_url: str) -> str:
    folded = _fold(source_name + " " + source_url)
    if "wordpress theme" in folded or "woocommerce theme" in folded or " tema " in f" {folded} ":
        return "theme"
    return "plugin"


def _build_prompt(job: Mapping[str, Any]) -> str:
    kind = "tema WordPress" if job.get("item_type") == "theme" else "plugin WordPress"
    return (
        "Crie o conteúdo comercial para um novo produto da PluginTema usando SOMENTE as informações abaixo "
        "e informações verificáveis da página oficial. Não invente recursos, integrações, compatibilidades ou promessas.\n\n"
        f"Produto: {job.get('source_name','')}\n"
        f"Tipo: {kind}\n"
        f"Versão: {job.get('source_version','')}\n"
        f"Página da fonte: {job.get('source_product_url','')}\n"
        f"Página oficial: {job.get('source_official_url','')}\n\n"
        "Entregue:\n"
        "1. TÍTULO — nome comercial limpo, sem versão.\n"
        "2. BREVE DESCRIÇÃO — 1 parágrafo curto e objetivo.\n"
        "3. DESCRIÇÃO COMPLETA — em HTML simples, com introdução, principais recursos e para quem é indicado.\n"
        "4. META DESCRIPTION — até aproximadamente 155 caracteres.\n"
        "5. TAGS — lista curta separada por vírgulas.\n"
        "6. IMAGEM — gere uma imagem quadrada 1:1 apropriada para catálogo, limpa, profissional, sem preço, "
        "sem selo promocional e sem inventar logotipos que não existam.\n\n"
        "Eu vou copiar os textos e baixar a imagem manualmente para o CrapScraper."
    )


def materialize() -> dict[str, Any]:
    initialize()
    decisions = list_approved_additions()
    created = 0
    with _db() as connection:
        for decision in decisions:
            comparison_id = str(decision.get("comparison_item_id") or "").strip()
            if not comparison_id:
                continue
            exists = connection.execute(
                "SELECT job_id FROM addition_jobs WHERE comparison_item_id=?", (comparison_id,)
            ).fetchone()
            if exists:
                continue
            job_id = _job_id(comparison_id)
            source_name = str(decision.get("source_name") or "").strip()
            source_url = str(decision.get("source_product_url") or "").strip()
            item_type = _infer_item_type(source_name, source_url)
            now = _now()
            base = {
                "job_id": job_id,
                "comparison_item_id": comparison_id,
                "state": "approved",
                "source_name": source_name,
                "source_version": str(decision.get("source_version") or "").strip(),
                "source_product_url": source_url,
                "source_official_url": str(decision.get("source_official_url") or "").strip(),
                "item_type": item_type,
            }
            prompt = _build_prompt(base)
            connection.execute(
                """INSERT INTO addition_jobs (
                    job_id, comparison_item_id, state, source_name, source_version,
                    source_product_url, source_official_url, item_type, title, prompt_text,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job_id, comparison_id, "approved", source_name, base["source_version"],
                    source_url, base["source_official_url"], item_type, source_name, prompt, now, now,
                ),
            )
            created += 1
    return {"created": created, **snapshot()}


def _public(row: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(row)
    try:
        item["logs"] = json.loads(item.pop("logs_json", "[]") or "[]")
    except Exception:
        item["logs"] = []
    item["state_label"] = STATE_LABELS.get(str(item.get("state")), str(item.get("state")))
    item["has_zip"] = bool(item.get("zip_path") and Path(str(item.get("zip_path"))).is_file())
    item["has_content"] = bool(item.get("title") and item.get("short_description") and item.get("description"))
    item["has_image"] = bool(item.get("image_path") and Path(str(item.get("image_path"))).is_file())
    return item


def snapshot() -> dict[str, Any]:
    initialize()
    with _db() as connection:
        rows = [dict(row) for row in connection.execute(
            "SELECT * FROM addition_jobs ORDER BY updated_at DESC"
        ).fetchall()]
    jobs = [_public(row) for row in rows]
    active = [job for job in jobs if job.get("state") in ACTIVE_STATES]
    history = [job for job in jobs if job.get("state") == "completed"]
    counts = {key: 0 for key in STATE_LABELS}
    for job in jobs:
        counts[str(job.get("state"))] = counts.get(str(job.get("state")), 0) + 1
    counts["total"] = len(jobs)
    counts["active"] = len(active)
    return {"ok": True, "jobs": jobs, "active": active, "history": history, "counts": counts}


def _woo() -> WooCommerceClient:
    base = os.getenv("SCRAPER_WP_BASE_URL", "").strip()
    key = os.getenv("SCRAPER_WC_CONSUMER_KEY", "").strip()
    secret = os.getenv("SCRAPER_WC_CONSUMER_SECRET", "").strip()
    if not all((base, key, secret)):
        raise RuntimeError("Configuração WooCommerce incompleta.")
    return WooCommerceClient(base, key, secret, timeout=20, retries=1)


def _writes_enabled() -> bool:
    return os.getenv("SCRAPER_UPDATE_EXECUTION_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def _duplicate_product(name: str) -> Mapping[str, Any] | None:
    folded = _fold(name)
    if not folded:
        return None
    for product in _woo().search_products(name, per_page=20):
        candidate = _fold(product.get("name"))
        if candidate == folded or SequenceMatcher(None, candidate, folded).ratio() >= 0.97:
            return product
    return None


def _session_for(app: Any, url: str) -> Any:
    from app.integrations.ultrapack_session import (
        get_authenticated_plugintheme_session,
        get_authenticated_ultrapack_session,
    )
    if SourceDownloader.is_plugintheme(url):
        return get_authenticated_plugintheme_session(app, url).session
    return get_authenticated_ultrapack_session(app, url).session


def _prepare(job_id: str, app: Any) -> None:
    job = _row(job_id)
    if not job:
        return
    try:
        _update(job_id, state="preparing", error="")
        _log(job_id, "Verificando se o produto já existe no PluginTema")
        duplicate = _duplicate_product(str(job.get("source_name") or job.get("title") or ""))
        if duplicate:
            raise RuntimeError(
                f"Possível produto já existente no WooCommerce: #{duplicate.get('id')} · {duplicate.get('name')}. Revise antes de cadastrar."
            )
        source_url = str(job.get("source_product_url") or "").strip()
        if not source_url:
            raise RuntimeError("URL da fonte ausente na decisão aprovada.")
        _log(job_id, "Validando sessão da fonte")
        session = _session_for(app, source_url)
        downloader = SourceDownloader(UltrapackDownloader(session), PluginThemeDownloader(session))
        target = STAGING_ROOT / job_id
        target.mkdir(parents=True, exist_ok=True)
        _log(job_id, "Baixando ZIP para staging local")
        artifact, detected_version = downloader.download(source_url, target)
        version = str(detected_version or job.get("source_version") or "").strip()
        _log(job_id, f"ZIP validado · {artifact.entries} entradas · SHA-256 {artifact.sha256[:12]}…")
        refreshed = {**job, "source_version": version}
        refreshed["prompt_text"] = _build_prompt(refreshed)
        _update(
            job_id,
            state="awaiting_content",
            source_version=version,
            zip_path=artifact.path,
            zip_file_name=artifact.file_name,
            zip_sha256=artifact.sha256,
            zip_size=artifact.size,
            zip_entries=artifact.entries,
            prompt_text=refreshed["prompt_text"],
            error="",
        )
        _log(job_id, "Arquivo pronto. Aguardando conteúdo e imagem do ChatGPT")
    except Exception as error:
        _update(job_id, state="blocked" if "já existente" in str(error) else "error", error=str(error))
        _log(job_id, f"Falha: {error}")


def _start(job_id: str, operation: str, target) -> dict[str, Any]:
    key = f"{operation}:{job_id}"
    with _LOCK:
        worker = _WORKERS.get(key)
        if worker and worker.is_alive():
            return {"ok": True, "started": False, "message": "Operação já está em andamento."}
        worker = threading.Thread(target=target, name=key, daemon=True)
        _WORKERS[key] = worker
        worker.start()
    return {"ok": True, "started": True}


def start_prepare(job_id: str, app: Any, *, item_type: str = "") -> dict[str, Any]:
    job = _row(job_id)
    if not job:
        raise ValueError("Job de adição não encontrado.")
    normalized_type = str(item_type or job.get("item_type") or "plugin").strip().lower()
    if normalized_type not in {"plugin", "theme"}:
        raise ValueError("Tipo deve ser plugin ou theme.")
    _update(job_id, item_type=normalized_type, prompt_text=_build_prompt({**job, "item_type": normalized_type}))
    return _start(job_id, "prepare", lambda: _prepare(job_id, app))


def _save_image(job_id: str, image_data: str, image_name: str) -> tuple[str, str]:
    if not image_data:
        current = _row(job_id) or {}
        return str(current.get("image_path") or ""), str(current.get("image_name") or "")
    raw = image_data
    mime = ""
    if raw.startswith("data:"):
        header, raw = raw.split(",", 1)
        mime = header.split(";", 1)[0].split(":", 1)[-1]
    data = base64.b64decode(raw, validate=True)
    if not data or len(data) > IMAGE_MAX_BYTES:
        raise ValueError("Imagem vazia ou maior que 8 MB.")
    allowed = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    ext = allowed.get(mime)
    if not ext:
        ext = Path(image_name or "").suffix.lower()
        if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise ValueError("Use imagem JPG, PNG ou WEBP.")
        if ext == ".jpeg":
            ext = ".jpg"
    folder = STAGING_ROOT / job_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ("catalog-image" + ext)
    path.write_bytes(data)
    return str(path), Path(image_name or path.name).name


def save_content(job_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    job = _row(job_id)
    if not job:
        raise ValueError("Job de adição não encontrado.")
    item_type = str(payload.get("item_type") or job.get("item_type") or "plugin").strip().lower()
    if item_type not in {"plugin", "theme"}:
        raise ValueError("Tipo inválido.")
    title = str(payload.get("title") or "").strip()
    short = str(payload.get("short_description") or "").strip()
    description = str(payload.get("description") or "").strip()
    if not title or not short or not description:
        raise ValueError("Título, breve descrição e descrição completa são obrigatórios.")
    image_path, image_name = _save_image(
        job_id, str(payload.get("image_data") or ""), str(payload.get("image_name") or "")
    )
    state = "content_ready" if job.get("zip_path") and Path(str(job.get("zip_path"))).is_file() else "approved"
    current = _update(
        job_id,
        item_type=item_type,
        title=title,
        short_description=short,
        description=description,
        meta_description=str(payload.get("meta_description") or "").strip(),
        tags_text=str(payload.get("tags_text") or "").strip(),
        image_path=image_path,
        image_name=image_name,
        state=state,
        prompt_text=_build_prompt({**job, "item_type": item_type, "title": title}),
        error="",
    )
    _log(job_id, "Conteúdo editorial salvo")
    return {"ok": True, "job": _public(current)}


def _basic(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    return "Basic " + token


def _json_request(method: str, url: str, username: str, password: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
    body = json.dumps(dict(payload), ensure_ascii=False).encode("utf-8")
    request = Request(url, data=body, method=method, headers={
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": _basic(username, password),
        "User-Agent": "CrapScraper-addition/1.0",
    })
    try:
        with urlopen(request, timeout=45) as response:
            raw = response.read()
    except Exception as error:
        raise RuntimeError(f"Falha na escrita WordPress/WooCommerce: {error}") from None
    decoded = json.loads(raw or b"{}")
    if not isinstance(decoded, Mapping):
        raise RuntimeError("Resposta inválida da API.")
    return decoded


def _woo_write(method: str, path: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
    base = os.getenv("SCRAPER_WP_BASE_URL", "").strip().rstrip("/")
    key = os.getenv("SCRAPER_WC_CONSUMER_KEY", "").strip()
    secret = os.getenv("SCRAPER_WC_CONSUMER_SECRET", "").strip()
    if not all((base, key, secret)):
        raise RuntimeError("Credenciais WooCommerce ausentes.")
    return _json_request(method, base + "/" + path.lstrip("/"), key, secret, payload)


def _upload_media(path: str, image_name: str) -> int:
    if not path:
        return 0
    username = os.getenv("SCRAPER_WP_USERNAME", "").strip()
    password = os.getenv("SCRAPER_WP_APPLICATION_PASSWORD", "").strip()
    base = os.getenv("SCRAPER_WP_BASE_URL", "").strip().rstrip("/")
    if not all((username, password, base)):
        raise RuntimeError("Credenciais WordPress para mídia não estão configuradas.")
    file_path = Path(path)
    data = file_path.read_bytes()
    mime = mimetypes.guess_type(file_path.name)[0] or "image/jpeg"
    request = Request(
        base + "/wp-json/wp/v2/media",
        data=data,
        method="POST",
        headers={
            "Authorization": _basic(username, password),
            "Content-Type": mime,
            "Content-Disposition": f'attachment; filename="{Path(image_name or file_path.name).name}"',
            "User-Agent": "CrapScraper-addition-media/1.0",
        },
    )
    try:
        with urlopen(request, timeout=60) as response:
            result = json.loads(response.read() or b"{}")
    except Exception as error:
        raise RuntimeError(f"Falha ao enviar imagem para WordPress: {error}") from None
    media_id = int(result.get("id") or 0) if isinstance(result, Mapping) else 0
    if media_id <= 0:
        raise RuntimeError("WordPress não retornou o ID da mídia.")
    return media_id


def _remote_file_name(job: Mapping[str, Any]) -> str:
    version = re.sub(r"[^0-9A-Za-z._-]+", "-", str(job.get("source_version") or "").strip())
    suffix = f"-v{version}" if version else ""
    return (_slug(job.get("title") or job.get("source_name"))[:145] + suffix + ".zip")[:195]


def _upload_new_zip(job: Mapping[str, Any]) -> tuple[str, str]:
    local = Path(str(job.get("zip_path") or ""))
    if not local.is_file():
        raise RuntimeError("ZIP local preparado não existe.")
    expected = str(job.get("zip_sha256") or "").lower()
    config = SSHStorageConfig.from_env()
    file_name = _remote_file_name(job)
    target = str(PurePosixPath(config.root) / file_name)
    try:
        import paramiko
    except ImportError:
        raise RuntimeError("Paramiko não instalado. Instale requirements-ssh.txt.") from None
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.connect(
            hostname=config.host, port=config.port, username=config.username, password=config.password,
            look_for_keys=False, allow_agent=False, timeout=15, banner_timeout=15, auth_timeout=15,
        )
        sftp = client.open_sftp()
        root = str(PurePosixPath(sftp.normalize(config.root)))
        resolved_target = str(PurePosixPath(root) / file_name)
        try:
            sftp.stat(resolved_target)
            # Reuso somente se o conteúdo for idêntico.
            digest = hashlib.sha256()
            with sftp.open(resolved_target, "rb") as remote:
                while chunk := remote.read(1024 * 1024):
                    digest.update(chunk)
            if digest.hexdigest().lower() != expected:
                raise RuntimeError("Já existe um ZIP remoto com o mesmo nome e conteúdo diferente.")
        except FileNotFoundError:
            with local.open("rb") as source, sftp.open(resolved_target, "x") as remote:
                while chunk := source.read(1024 * 1024):
                    remote.write(chunk)
            with suppress(Exception):
                sftp.chmod(resolved_target, 0o644)
            digest = hashlib.sha256()
            with sftp.open(resolved_target, "rb") as remote:
                while chunk := remote.read(1024 * 1024):
                    digest.update(chunk)
            if digest.hexdigest().lower() != expected:
                raise RuntimeError("SHA-256 do ZIP remoto diverge do staging local.")
        finally:
            with suppress(Exception):
                sftp.close()
    finally:
        client.close()
    base = os.getenv("SCRAPER_WP_BASE_URL", "").strip().rstrip("/")
    return target, base + "/downloads/" + quote(file_name)


def _find_category(item_type: str) -> tuple[int, str]:
    wanted = {"plugin", "plugins"} if item_type == "plugin" else {"tema", "temas", "theme", "themes"}
    woo = _woo()
    page = 1
    while True:
        rows = woo.list_product_categories(page=page, per_page=100)
        for category in rows:
            if _fold(category.get("name")) in wanted:
                return int(category.get("id") or 0), str(category.get("name") or "")
        if len(rows) < 100:
            break
        page += 1
    raise RuntimeError("Categoria de Plugins/Temas não encontrada no WooCommerce.")


def _period(variation: Mapping[str, Any]) -> str:
    text = _fold(" ".join(str(item.get("option") or "") for item in variation.get("attributes", []) or [] if isinstance(item, Mapping)))
    if any(token in text for token in ("vitalicio", "lifetime", "vitalicia")):
        return "lifetime"
    if any(token in text for token in ("anual", "annual", "12 meses", "1 ano")):
        return "annual"
    return ""


def _template(item_type: str, category_id: int) -> tuple[Mapping[str, Any], list[Mapping[str, Any]]]:
    woo = _woo()
    candidates = woo.list_products(
        page=1, per_page=25, status="publish", type="variable", category=category_id,
        _fields="id,name,type,attributes,default_attributes,categories",
    )
    for candidate in candidates:
        product_id = int(candidate.get("id") or 0)
        if not product_id:
            continue
        full = woo.get_product(product_id)
        variations = woo.list_variations(product_id, per_page=100)
        selected = [row for row in variations if _period(row) in {"annual", "lifetime"}]
        if { _period(row) for row in selected } >= {"annual", "lifetime"}:
            return full, selected
    raise RuntimeError("Não encontrei um produto variável modelo com variações Anual e Vitalícia nessa categoria.")


def _attributes_for_write(product: Mapping[str, Any]) -> list[dict[str, Any]]:
    result = []
    for attr in product.get("attributes", []) or []:
        if not isinstance(attr, Mapping):
            continue
        item = {key: attr[key] for key in ("id", "name", "position", "visible", "variation", "options") if key in attr}
        if item:
            result.append(item)
    return result


def _ensure_draft(job_id: str) -> None:
    job = _row(job_id)
    if not job:
        return
    try:
        if not _writes_enabled():
            raise RuntimeError("Escrita real está desabilitada. Habilite SCRAPER_UPDATE_EXECUTION_ENABLED=true.")
        if job.get("state") not in {"content_ready", "creating_draft", "error"}:
            raise RuntimeError("O item precisa ter ZIP e conteúdo prontos antes de criar o rascunho.")
        _update(job_id, state="creating_draft", error="")
        _log(job_id, "Revalidando duplicidade antes da criação")
        duplicate = _duplicate_product(str(job.get("title") or job.get("source_name") or ""))
        if duplicate and int(duplicate.get("id") or 0) != int(job.get("woo_product_id") or 0):
            raise RuntimeError(f"Produto semelhante já existe no WooCommerce: #{duplicate.get('id')} · {duplicate.get('name')}")

        remote_path = str(job.get("remote_zip_path") or "")
        remote_url = str(job.get("remote_zip_url") or "")
        if not remote_path:
            _log(job_id, "Enviando novo ZIP ao diretório de downloads sem sobrescrever arquivos existentes")
            remote_path, remote_url = _upload_new_zip(job)
            _update(job_id, remote_zip_path=remote_path, remote_zip_url=remote_url)
            _log(job_id, "ZIP remoto validado pelo SHA-256")

        category_id = int(job.get("category_id") or 0)
        category_name = str(job.get("category_name") or "")
        if category_id <= 0:
            category_id, category_name = _find_category(str(job.get("item_type") or "plugin"))
            _update(job_id, category_id=category_id, category_name=category_name)
        template, template_variations = _template(str(job.get("item_type") or "plugin"), category_id)
        _update(job_id, template_product_id=int(template.get("id") or 0))

        media_id = int(job.get("media_id") or 0)
        if not media_id and job.get("image_path"):
            _log(job_id, "Enviando imagem ao WordPress")
            media_id = _upload_media(str(job.get("image_path")), str(job.get("image_name") or "catalog-image"))
            _update(job_id, media_id=media_id)

        woo_product_id = int(job.get("woo_product_id") or 0)
        if woo_product_id <= 0:
            _log(job_id, "Criando produto como rascunho no WooCommerce")
            payload: dict[str, Any] = {
                "name": str(job.get("title") or job.get("source_name") or "").strip(),
                "type": "variable",
                "status": "draft",
                "description": str(job.get("description") or ""),
                "short_description": str(job.get("short_description") or ""),
                "categories": [{"id": category_id}],
                "attributes": _attributes_for_write(template),
                "meta_data": [
                    {"key": "pt_versao", "value": str(job.get("source_version") or "")},
                    {"key": "_crapscraper_source_url", "value": str(job.get("source_product_url") or "")},
                    {"key": "_crapscraper_official_url", "value": str(job.get("source_official_url") or "")},
                ],
            }
            if media_id:
                payload["images"] = [{"id": media_id}]
            created = _woo_write("POST", "/wp-json/wc/v3/products", payload)
            woo_product_id = int(created.get("id") or 0)
            if woo_product_id <= 0:
                raise RuntimeError("WooCommerce não confirmou o ID do rascunho.")
            _update(job_id, woo_product_id=woo_product_id, woo_status=str(created.get("status") or "draft"))

        current_variations = _woo().list_variations(woo_product_id, per_page=100)
        existing_keys = {
            tuple((str(a.get("id") or a.get("name") or ""), str(a.get("option") or "")) for a in row.get("attributes", []) or [])
            for row in current_variations
        }
        for source_var in template_variations:
            attrs = [dict(item) for item in source_var.get("attributes", []) or [] if isinstance(item, Mapping)]
            key = tuple((str(a.get("id") or a.get("name") or ""), str(a.get("option") or "")) for a in attrs)
            if key in existing_keys:
                continue
            label = "Anual" if _period(source_var) == "annual" else "Vitalício"
            _log(job_id, f"Criando variação {label}")
            _woo_write(
                "POST",
                f"/wp-json/wc/v3/products/{woo_product_id}/variations",
                {
                    "status": "publish",
                    "regular_price": str(source_var.get("regular_price") or ""),
                    "sale_price": str(source_var.get("sale_price") or ""),
                    "virtual": True,
                    "downloadable": True,
                    "download_limit": -1,
                    "download_expiry": -1,
                    "downloads": [{"name": Path(remote_path).name, "file": remote_url}],
                    "attributes": attrs,
                },
            )
            existing_keys.add(key)

        product = _woo().get_product_fresh(woo_product_id)
        variations = _woo().list_variations_fresh(woo_product_id, per_page=100)
        periods = {_period(row) for row in variations}
        if str(product.get("status")) != "draft" or not {"annual", "lifetime"}.issubset(periods):
            raise RuntimeError("Rascunho criado, mas a validação das variações não foi concluída.")
        _update(job_id, state="draft_created", woo_status="draft", error="")
        _log(job_id, f"Rascunho #{woo_product_id} criado e validado")
    except Exception as error:
        _update(job_id, state="error", error=str(error))
        _log(job_id, f"Falha ao criar rascunho: {error}")


def start_create_draft(job_id: str, confirmation: str) -> dict[str, Any]:
    if confirmation != "CRIAR RASCUNHO":
        raise ValueError('Confirmação inválida. Era esperado "CRIAR RASCUNHO".')
    if not _row(job_id):
        raise ValueError("Job de adição não encontrado.")
    return _start(job_id, "draft", lambda: _ensure_draft(job_id))


def _publish(job_id: str) -> None:
    job = _row(job_id)
    if not job:
        return
    try:
        if not _writes_enabled():
            raise RuntimeError("Escrita real está desabilitada.")
        product_id = int(job.get("woo_product_id") or 0)
        if product_id <= 0:
            raise RuntimeError("Rascunho WooCommerce ausente.")
        _update(job_id, state="publishing", error="")
        _log(job_id, "Executando validação final do rascunho")
        product = _woo().get_product_fresh(product_id)
        variations = _woo().list_variations_fresh(product_id, per_page=100)
        periods = {_period(row) for row in variations}
        if str(product.get("status")) != "draft":
            if str(product.get("status")) == "publish":
                _update(job_id, state="completed", woo_status="publish", completed_at=_now(), error="")
                _log(job_id, "Produto já estava publicado; ciclo concluído")
                return
            raise RuntimeError("Produto não está em estado de rascunho.")
        if not {"annual", "lifetime"}.issubset(periods):
            raise RuntimeError("Variações Anual e Vitalícia não estão prontas.")
        if not str(job.get("remote_zip_url") or ""):
            raise RuntimeError("Download remoto não está preparado.")
        _log(job_id, "Publicando produto")
        _woo_write("PUT", f"/wp-json/wc/v3/products/{product_id}", {"status": "publish"})
        verified = _woo().get_product_fresh(product_id)
        if str(verified.get("status")) != "publish":
            raise RuntimeError("WooCommerce não confirmou a publicação.")
        _update(job_id, state="completed", woo_status="publish", completed_at=_now(), error="")
        _log(job_id, "Produto publicado e ciclo concluído")
    except Exception as error:
        _update(job_id, state="error", error=str(error))
        _log(job_id, f"Falha ao publicar: {error}")


def start_publish(job_id: str, confirmation: str) -> dict[str, Any]:
    if confirmation != "PUBLICAR":
        raise ValueError('Confirmação inválida. Era esperado "PUBLICAR".')
    job = _row(job_id)
    if not job or job.get("state") not in {"draft_created", "publishing", "error"}:
        raise ValueError("Rascunho não está pronto para publicação.")
    return _start(job_id, "publish", lambda: _publish(job_id))


def retry(job_id: str, app: Any) -> dict[str, Any]:
    job = _row(job_id)
    if not job:
        raise ValueError("Job de adição não encontrado.")
    if int(job.get("woo_product_id") or 0) > 0:
        state = "draft_created"
    elif job.get("zip_path") and job.get("title") and job.get("short_description") and job.get("description"):
        state = "content_ready"
    elif job.get("zip_path"):
        state = "awaiting_content"
    else:
        state = "approved"
    _update(job_id, state=state, error="")
    _log(job_id, "Item liberado para nova tentativa")
    if state == "approved":
        return start_prepare(job_id, app)
    return {"ok": True, "started": False, "state": state}


def active_processes() -> list[dict[str, Any]]:
    data = snapshot()
    result = []
    for job in data["active"]:
        if job.get("state") in {"preparing", "creating_draft", "publishing"}:
            logs = job.get("logs") or []
            result.append({
                "id": job.get("job_id"),
                "kind": "addition",
                "title": job.get("title") or job.get("source_name"),
                "state": job.get("state_label"),
                "message": logs[-1].get("message") if logs else "Processando novo produto",
            })
    return result
