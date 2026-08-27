from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.collection.legacy_core import settings
from app.collection.legacy_core.models import Category, ScraperContext, SlotInfo, build_context

try:
    from app.core.exceptions import (
        CachePersistenceError,
        CatalogPersistenceError,
        SlotError,
        StatusPersistenceError,
        StorageError,
    )
except Exception:  # pragma: no cover
    class StorageError(RuntimeError):
        pass

    class SlotError(StorageError):
        pass

    class CatalogPersistenceError(StorageError):
        pass

    class CachePersistenceError(StorageError):
        pass

    class StatusPersistenceError(StorageError):
        pass


# ============================================================
# TIPOS / HELPERS BÁSICOS
# ============================================================

PathLike = str | Path

CATALOG_FIELDNAMES: tuple[str, ...] = (
    "tipo",
    "categoria_nome",
    "categoria_url",
    "link_produto",
    "imagem_url",
    "imagem_path",
    "pagina_oficial",
    "nome_produto",
    "versao_produto",
    "observacao",
)


def _normalize_spaces(value: Any) -> str:
    if value in (None, ""):
        return ""
    return " ".join(str(value).split()).strip()


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def now_iso() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def format_duration_seconds(total_seconds: Any) -> str:
    seconds = max(0, to_int(total_seconds, 0))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    remaining_seconds = seconds % 60
    return f"{hours}:{minutes:02d}:{remaining_seconds:02d}"


def _parse_datetime_value(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None

    for fmt in ("%d/%m/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            pass

    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def calculate_duration_seconds(
    run_started_at: str | None,
    run_finished_at: str | None = None,
) -> int:
    if not run_started_at:
        return 0

    started_at = _parse_datetime_value(run_started_at)
    if started_at is None:
        return 0

    if run_finished_at:
        finished_at = _parse_datetime_value(run_finished_at) or datetime.now()
    else:
        finished_at = datetime.now()

    return max(0, int((finished_at - started_at).total_seconds()))


def ensure_trailing_slash(url: Any) -> str:
    text = _normalize_spaces(url)
    if not text:
        return ""
    return text if text.endswith("/") else text + "/"


def get_continue_enabled_default() -> bool:
    return bool(getattr(settings, "RETOMAR_DE_ONDE_PAROU", True))


def _sanitize_filename_piece(value: Any, fallback: str = "arquivo") -> str:
    text = _normalize_spaces(value).lower()
    text = re.sub(r"[^a-z0-9._-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-._ ")
    return text or fallback


def _guess_image_extension(image_url: str) -> str:
    path = urlparse(str(image_url or "")).path or ""
    suffix = Path(path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".svg", ".avif"}:
        return suffix
    return ".jpg"


def ensure_template_image_saved(
    product: Mapping[str, Any] | None,
    context: Any = None,
    **kwargs: Any,
) -> dict[str, str]:
    item = normalize_catalog_item(product)

    if item.get("tipo") != "template":
        item["imagem_url"] = ""
        item["imagem_path"] = ""
        return item

    image_url = _normalize_spaces(item.get("imagem_url", ""))
    if not image_url:
        item["imagem_path"] = ""
        return item

    paths = build_context_paths(context, **kwargs, ensure=True)
    images_dir = ensure_dir(paths.context_dir / "template_images")

    product_url = _normalize_spaces(item.get("link_produto", ""))
    slug = _sanitize_filename_piece(Path(urlparse(product_url).path).name or "template", fallback="template")
    short_hash = hashlib.sha1(image_url.encode("utf-8")).hexdigest()[:10]
    extension = _guess_image_extension(image_url)

    filename = f"{slug}-{short_hash}{extension}"
    image_path = images_dir / filename
    relative_path = str(Path("template_images") / filename)

    if not image_path.exists() or image_path.stat().st_size <= 0:
        try:
            request = Request(
                image_url,
                headers={
                    "User-Agent": str(
                        getattr(
                            settings,
                            "PLAYWRIGHT_USER_AGENT",
                            "Mozilla/5.0",
                        )
                    )
                },
            )
            with urlopen(request, timeout=30) as response, image_path.open("wb") as file:
                file.write(response.read())
        except Exception:
            item["imagem_path"] = ""
            return item

    item["imagem_path"] = relative_path
    return item


# ============================================================
# I/O DE ARQUIVOS
# ============================================================


def coerce_path(path: PathLike) -> Path:
    return path if isinstance(path, Path) else Path(path)


def ensure_parent_dir(path: PathLike) -> Path:
    resolved = coerce_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def ensure_dir(path: PathLike) -> Path:
    resolved = coerce_path(path)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def path_exists(path: PathLike) -> bool:
    return coerce_path(path).exists()


def remove_file(path: PathLike, *, missing_ok: bool = True) -> bool:
    resolved = coerce_path(path)

    try:
        resolved.unlink()
        return True
    except FileNotFoundError:
        if missing_ok:
            return False
        raise


def read_text(
    path: PathLike,
    default: str = "",
    *,
    encoding: str = "utf-8",
) -> str:
    resolved = coerce_path(path)

    if not resolved.exists():
        return default

    try:
        return resolved.read_text(encoding=encoding)
    except Exception:
        return default


def write_text_atomic(
    path: PathLike,
    text: str,
    *,
    encoding: str = "utf-8",
) -> Path:
    resolved = ensure_parent_dir(path)
    temp_path = resolved.with_name(resolved.name + ".tmp")
    temp_path.write_text(str(text), encoding=encoding)
    temp_path.replace(resolved)
    return resolved


def append_text(
    path: PathLike,
    text: str,
    *,
    encoding: str = "utf-8",
    ensure_newline: bool = False,
) -> Path:
    resolved = ensure_parent_dir(path)

    chunk = str(text)
    if ensure_newline and chunk and not chunk.endswith("\n"):
        chunk += "\n"

    with resolved.open("a", encoding=encoding) as file:
        file.write(chunk)

    return resolved


def read_json(
    path: PathLike,
    default: Any,
    *,
    encoding: str = "utf-8",
) -> Any:
    resolved = coerce_path(path)

    if not resolved.exists():
        return default

    try:
        with resolved.open("r", encoding=encoding) as file:
            return json.load(file)
    except Exception:
        return default


def write_json_atomic(
    path: PathLike,
    data: Any,
    *,
    encoding: str = "utf-8",
    ensure_ascii: bool = False,
    indent: int = 2,
) -> Path:
    resolved = ensure_parent_dir(path)
    temp_path = resolved.with_name(resolved.name + ".tmp")

    with temp_path.open("w", encoding=encoding) as file:
        json.dump(data, file, ensure_ascii=ensure_ascii, indent=indent)

    temp_path.replace(resolved)
    return resolved


def read_csv_rows(
    path: PathLike,
    default: list[dict[str, Any]] | None = None,
    *,
    encoding: str = "utf-8-sig",
) -> list[dict[str, Any]]:
    resolved = coerce_path(path)

    if not resolved.exists():
        return list(default or [])

    try:
        with resolved.open("r", newline="", encoding=encoding) as file:
            return list(csv.DictReader(file))
    except Exception:
        return list(default or [])


def _unwrap_spreadsheet_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    match = re.fullmatch(r'=\"(.+)\"', text)
    if match:
        return match.group(1).replace('""', '"').strip()

    if text.startswith("'"):
        return text[1:].strip()

    return text


def _normalize_version_value(value: Any) -> str:
    version = _normalize_spaces(_unwrap_spreadsheet_text(value))

    if not version:
        return ""

    raw_version = version
    version = re.sub(r"^\s*vers[aã]o\s*[:#-]?\s*", "", version, flags=re.IGNORECASE).strip()
    version = version.replace(",", ".")
    version = re.sub(r"\s+", "", version)
    version = version.strip(" .-_")

    if not version:
        return ""

    if re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", version):
        return ""
    if re.fullmatch(r"\d{4}[/-]\d{1,2}[/-]\d{1,2}", version):
        return ""
    if re.fullmatch(r"\d+", version):
        has_version_label = bool(re.search(r"vers[aã]o|version|ver\.?", raw_version, flags=re.IGNORECASE))
        return version if has_version_label else ""

    semver_patterns = (
        r"(?<!\d)(\d+(?:\.\d+){1,5}(?:[._-]?(?:alpha|beta|rc|pre|pl|build|rev|hotfix)\d*)?)(?!\d)",
        r"(?<!\d)(\d+(?:\.\d+){1,5}[a-z]\d*)(?!\d)",
        r"(?<!\d)(\d+(?:\.\d+){1,5})(?!\d)",
    )

    for pattern in semver_patterns:
        match = re.search(pattern, version, flags=re.IGNORECASE)
        if match:
            return match.group(1)

    compact = re.sub(r"[^0-9A-Za-z.\-_]+", "", version).strip(" .-_")
    if not compact:
        return ""

    if re.fullmatch(r"\d{1,2}[.-]\d{1,2}[.-]\d{2,4}", compact):
        return ""

    return compact if "." in compact else ""


def _spreadsheet_safe_version(value: Any) -> str:
    clean = _normalize_version_value(value)
    if not clean:
        return ""

    escaped = clean.replace('"', '""')
    return f'="{escaped}"'


def _normalize_csv_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized_rows: list[dict[str, Any]] = []

    for row in rows:
        raw = {str(key): value for key, value in dict(row).items()}
        if "versao_produto" in raw:
            raw["versao_produto"] = _spreadsheet_safe_version(raw.get("versao_produto", ""))
        normalized_rows.append(raw)

    return normalized_rows


def write_csv_atomic(
    path: PathLike,
    fieldnames: Sequence[str],
    rows: Iterable[Mapping[str, Any]],
    *,
    encoding: str = "utf-8-sig",
    extrasaction: str = "ignore",
) -> Path:
    resolved = ensure_parent_dir(path)
    temp_path = resolved.with_name(resolved.name + ".tmp")
    normalized_rows = _normalize_csv_rows(rows)

    with temp_path.open("w", newline="", encoding=encoding) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(fieldnames),
            extrasaction=extrasaction,
        )
        writer.writeheader()
        writer.writerows(normalized_rows)

    temp_path.replace(resolved)
    return resolved


def touch_file(path: PathLike) -> Path:
    resolved = ensure_parent_dir(path)
    resolved.touch(exist_ok=True)
    return resolved


# ============================================================
# SLOT / PATHS / IDENTIDADE
# ============================================================


@dataclass(frozen=True, slots=True)
class StorageIdentity:
    site_key: str
    item_type_key: str
    account_key: str
    slot_name: str

    def as_dict(self) -> dict[str, str]:
        return {
            "site_key": self.site_key,
            "item_type_key": self.item_type_key,
            "account_key": self.account_key,
            "slot_name": self.slot_name,
        }


@dataclass(frozen=True, slots=True)
class ContextPaths:
    identity: StorageIdentity
    project_root: Path
    data_dir: Path
    logs_dir: Path
    slots_root_dir: Path
    slots_meta_path: Path
    slot_dir: Path
    context_dir: Path
    context_logs_dir: Path
    output_csv_path: Path
    output_json_path: Path
    progress_json_path: Path
    categories_cache_json_path: Path
    queue_cache_json_path: Path
    config_json_path: Path
    status_txt_path: Path
    last_logs_txt_path: Path
    runtime_log_path: Path

    def as_dict(self) -> dict[str, str]:
        return {
            "project_root": str(self.project_root),
            "data_dir": str(self.data_dir),
            "logs_dir": str(self.logs_dir),
            "slots_root_dir": str(self.slots_root_dir),
            "slots_meta_path": str(self.slots_meta_path),
            "slot_dir": str(self.slot_dir),
            "context_dir": str(self.context_dir),
            "context_logs_dir": str(self.context_logs_dir),
            "output_csv_path": str(self.output_csv_path),
            "output_json_path": str(self.output_json_path),
            "progress_json_path": str(self.progress_json_path),
            "categories_cache_json_path": str(self.categories_cache_json_path),
            "queue_cache_json_path": str(self.queue_cache_json_path),
            "config_json_path": str(self.config_json_path),
            "status_txt_path": str(self.status_txt_path),
            "last_logs_txt_path": str(self.last_logs_txt_path),
            "runtime_log_path": str(self.runtime_log_path),
            **self.identity.as_dict(),
        }


def _read_field(source: Any, *names: str) -> Any:
    if source is None:
        return None

    if isinstance(source, Mapping):
        for name in names:
            if name in source and source[name] not in (None, ""):
                return source[name]

    for name in names:
        if hasattr(source, name):
            value = getattr(source, name)
            if value not in (None, ""):
                return value

    return None


def _unwrap_key(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, Mapping):
        for name in ("key", "slug", "name", "id", "value"):
            nested = value.get(name)
            if nested not in (None, ""):
                return nested
        return None

    if isinstance(value, (str, int)):
        return value

    for name in ("key", "slug", "name", "id", "value"):
        if hasattr(value, name):
            nested = getattr(value, name)
            if nested not in (None, ""):
                return nested

    return value


def resolve_storage_identity(
    context: Any = None,
    *,
    site_key: str | None = None,
    item_type_key: str | None = None,
    account_key: str | None = None,
    slot_name: str | None = None,
) -> StorageIdentity:
    try:
        resolved_context = build_context(
            context,
            site_key=site_key,
            item_type_key=item_type_key,
            account_key=account_key,
            slot_name=slot_name,
        )
        return StorageIdentity(
            site_key=resolved_context.site_key,
            item_type_key=resolved_context.item_type_key,
            account_key=resolved_context.account_key,
            slot_name=resolved_context.slot_name,
        )
    except Exception:
        site_candidate = site_key
        if site_candidate in (None, ""):
            site_candidate = _read_field(context, "site_key", "site_slug", "site_name")
        if site_candidate in (None, ""):
            site_candidate = _unwrap_key(_read_field(context, "site"))

        item_candidate = item_type_key
        if item_candidate in (None, ""):
            item_candidate = _read_field(context, "item_type_key", "item_type_slug", "item_kind_key")
        if item_candidate in (None, ""):
            item_candidate = _unwrap_key(_read_field(context, "item_type", "item_kind", "kind"))

        account_candidate = account_key
        if account_candidate in (None, ""):
            account_candidate = _read_field(context, "account_key", "account_name", "account_slug")
        if account_candidate in (None, ""):
            account_candidate = _unwrap_key(_read_field(context, "account"))

        slot_candidate = slot_name
        if slot_candidate in (None, ""):
            slot_candidate = _read_field(context, "slot_name", "slot_key", "current_slot")
        if slot_candidate in (None, ""):
            slot_candidate = _unwrap_key(_read_field(context, "slot"))

        return StorageIdentity(
            site_key=settings.normalize_site_key(site_candidate),
            item_type_key=settings.normalize_item_type_key(item_candidate),
            account_key=settings.normalize_account_key(account_candidate),
            slot_name=settings.normalize_slot_name(slot_candidate),
        )


def get_project_root() -> Path:
    return settings.PROJECT_ROOT


def get_data_dir(*, ensure: bool = False) -> Path:
    return ensure_dir(settings.DATA_DIR) if ensure else settings.DATA_DIR


def get_logs_dir(*, ensure: bool = False) -> Path:
    return ensure_dir(settings.LOGS_DIR) if ensure else settings.LOGS_DIR


def get_slots_root_dir(*, ensure: bool = False) -> Path:
    return ensure_dir(settings.SLOTS_DIR) if ensure else settings.SLOTS_DIR


def get_slots_meta_path(*, ensure_parent: bool = True) -> Path:
    path = settings.SLOTS_META_JSON_PATH
    return ensure_parent_dir(path) if ensure_parent else path


# ============================================================
# SLOTS
# ============================================================


def ensure_slots_root_dir() -> Path:
    settings.SLOTS_DIR.mkdir(parents=True, exist_ok=True)
    settings.SLOTS_META_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    return settings.SLOTS_DIR


def get_slot_dir(slot_name: str | None = None, *, ensure: bool = False) -> Path:
    resolved_name = settings.normalize_slot_name(slot_name or get_active_slot_name())
    path = get_slots_root_dir(ensure=ensure) / resolved_name
    return ensure_dir(path) if ensure else path


def ensure_slot_dir(slot_name: str | None = None) -> Path:
    return get_slot_dir(slot_name, ensure=True)


def _normalize_slot_names(values: Any) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()

    if not isinstance(values, list):
        values = []

    for value in values:
        slot_name = settings.normalize_slot_name(value)
        if slot_name in seen:
            continue
        seen.add(slot_name)
        normalized.append(slot_name)

    if settings.DEFAULT_SLOT_NAME not in seen:
        normalized.insert(0, settings.DEFAULT_SLOT_NAME)

    return normalized


def load_slots_meta() -> dict[str, Any]:
    ensure_slots_root_dir()

    raw = read_json(settings.SLOTS_META_JSON_PATH, {})
    if not isinstance(raw, dict):
        raw = {}

    slot_names = _normalize_slot_names(raw.get("slots", []))

    default_slot = settings.normalize_slot_name(raw.get("default_slot", settings.DEFAULT_SLOT_NAME))
    if default_slot not in slot_names:
        slot_names.append(default_slot)

    active_slot = settings.normalize_slot_name(raw.get("active_slot", default_slot))
    if active_slot not in slot_names:
        slot_names.append(active_slot)

    payload = {
        "slots": sorted(set(slot_names)),
        "default_slot": default_slot,
        "active_slot": active_slot,
    }

    for slot_name in payload["slots"]:
        ensure_slot_dir(slot_name)

    return payload


def save_slots_meta(meta: dict[str, Any] | None) -> dict[str, Any]:
    ensure_slots_root_dir()

    meta = meta or {}
    slot_names = _normalize_slot_names(meta.get("slots", []) if isinstance(meta, dict) else [])

    default_slot = settings.normalize_slot_name(
        meta.get("default_slot", settings.DEFAULT_SLOT_NAME)
        if isinstance(meta, dict)
        else settings.DEFAULT_SLOT_NAME
    )
    if default_slot not in slot_names:
        slot_names.append(default_slot)

    active_slot = settings.normalize_slot_name(
        meta.get("active_slot", default_slot)
        if isinstance(meta, dict)
        else default_slot
    )
    if active_slot not in slot_names:
        slot_names.append(active_slot)

    payload = {
        "slots": sorted(set(slot_names)),
        "default_slot": default_slot,
        "active_slot": active_slot,
    }

    write_json_atomic(settings.SLOTS_META_JSON_PATH, payload)

    for slot_name in payload["slots"]:
        ensure_slot_dir(slot_name)

    return payload


def list_slot_names() -> list[str]:
    return list(load_slots_meta()["slots"])


def has_slot(slot_name: str | None) -> bool:
    return settings.normalize_slot_name(slot_name) in load_slots_meta()["slots"]


def get_default_slot_name() -> str:
    meta = load_slots_meta()
    return settings.normalize_slot_name(meta.get("default_slot", settings.DEFAULT_SLOT_NAME))


def get_active_slot_name() -> str:
    meta = load_slots_meta()
    return settings.normalize_slot_name(meta.get("active_slot", meta.get("default_slot", settings.DEFAULT_SLOT_NAME)))


def get_slot(slot_name: str | None = None) -> SlotInfo:
    meta = load_slots_meta()
    resolved_slot_name = settings.normalize_slot_name(slot_name or meta.get("active_slot", settings.DEFAULT_SLOT_NAME))

    if resolved_slot_name not in meta["slots"]:
        resolved_slot_name = settings.normalize_slot_name(meta.get("active_slot", settings.DEFAULT_SLOT_NAME))

    return SlotInfo.build(
        resolved_slot_name,
        is_default=resolved_slot_name == meta["default_slot"],
        is_active=resolved_slot_name == meta["active_slot"],
    )


def list_slots() -> list[SlotInfo]:
    meta = load_slots_meta()
    default_slot = meta["default_slot"]
    active_slot = meta["active_slot"]

    return [
        SlotInfo.build(
            slot_name,
            is_default=slot_name == default_slot,
            is_active=slot_name == active_slot,
        )
        for slot_name in meta["slots"]
    ]


def build_slot_public_dict(slot_name: str | None = None) -> dict[str, Any]:
    return get_slot(slot_name).to_dict()


def build_slots_public_list() -> list[dict[str, Any]]:
    return [slot.to_dict() for slot in list_slots()]


def set_active_slot(slot_name: str | None) -> str:
    meta = load_slots_meta()
    normalized_slot_name = settings.normalize_slot_name(slot_name)

    if normalized_slot_name not in meta["slots"]:
        meta["slots"].append(normalized_slot_name)

    meta["active_slot"] = normalized_slot_name
    save_slots_meta(meta)
    ensure_slot_dir(normalized_slot_name)
    return normalized_slot_name


def set_default_slot(slot_name: str | None) -> str:
    meta = load_slots_meta()
    normalized_slot_name = settings.normalize_slot_name(slot_name)

    if normalized_slot_name not in meta["slots"]:
        meta["slots"].append(normalized_slot_name)

    meta["default_slot"] = normalized_slot_name
    save_slots_meta(meta)
    ensure_slot_dir(normalized_slot_name)
    return normalized_slot_name


def create_slot(slot_name: str | None) -> str:
    meta = load_slots_meta()
    normalized_slot_name = settings.normalize_slot_name(slot_name)

    if normalized_slot_name not in meta["slots"]:
        meta["slots"].append(normalized_slot_name)

    meta["active_slot"] = normalized_slot_name
    save_slots_meta(meta)
    ensure_slot_dir(normalized_slot_name)
    return normalized_slot_name


def _rename_tree_checked(source: PathLike, target: PathLike) -> tuple[bool, str]:
    source_path = coerce_path(source)
    target_path = coerce_path(target)

    if not source_path.exists():
        if target_path.exists():
            return True, ""
        return False, f'A pasta de origem não existe: "{source_path}"'

    if target_path.exists():
        is_empty_dir = False

        with suppress(Exception):
            is_empty_dir = target_path.is_dir() and next(target_path.iterdir(), None) is None

        if is_empty_dir:
            with suppress(Exception):
                target_path.rmdir()

        if target_path.exists():
            return False, f'A pasta de destino já existe: "{target_path}"'

    target_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        shutil.move(str(source_path), str(target_path))
    except Exception as error:
        return False, f'Falha ao renomear "{source_path}" para "{target_path}": {error}'

    if source_path.exists():
        return False, f'Falha ao renomear "{source_path}". A pasta original ainda existe.'

    if not target_path.exists():
        return False, f'Falha ao renomear "{source_path}". A pasta de destino não foi criada.'

    return True, ""


def rename_slot(old_slot_name: str | None, new_slot_name: str | None) -> tuple[bool, str, str]:
    meta = load_slots_meta()
    old_normalized_slot_name = settings.normalize_slot_name(old_slot_name)
    new_normalized_slot_name = settings.normalize_slot_name(new_slot_name)

    if old_normalized_slot_name not in meta["slots"]:
        return False, "Slot não encontrado.", old_normalized_slot_name

    if old_normalized_slot_name == settings.DEFAULT_SLOT_NAME:
        return False, 'O catálogo "Principal" não pode ser renomeado.', old_normalized_slot_name

    if not new_normalized_slot_name:
        return False, "Informe um novo nome para o slot.", old_normalized_slot_name

    if new_normalized_slot_name == old_normalized_slot_name:
        return False, "O novo nome é igual ao atual.", old_normalized_slot_name

    if new_normalized_slot_name in meta["slots"]:
        return False, f'Já existe um slot com o nome "{new_normalized_slot_name}".', old_normalized_slot_name

    old_data_slot_dir = get_slots_root_dir() / old_normalized_slot_name
    new_data_slot_dir = get_slots_root_dir() / new_normalized_slot_name

    old_logs_slot_dir = get_logs_dir() / old_normalized_slot_name
    new_logs_slot_dir = get_logs_dir() / new_normalized_slot_name

    data_renamed = False
    logs_renamed = False
    errors: list[str] = []

    ok_data, error_data = _rename_tree_checked(old_data_slot_dir, new_data_slot_dir)
    if ok_data:
        data_renamed = old_data_slot_dir.exists() is False and new_data_slot_dir.exists()
    elif error_data:
        errors.append(error_data)

    ok_logs, error_logs = _rename_tree_checked(old_logs_slot_dir, new_logs_slot_dir)
    if ok_logs:
        logs_renamed = old_logs_slot_dir.exists() is False and new_logs_slot_dir.exists()
    elif error_logs:
        errors.append(error_logs)

    if errors:
        if data_renamed and new_data_slot_dir.exists() and not old_data_slot_dir.exists():
            with suppress(Exception):
                new_data_slot_dir.rename(old_data_slot_dir)

        if logs_renamed and new_logs_slot_dir.exists() and not old_logs_slot_dir.exists():
            with suppress(Exception):
                new_logs_slot_dir.rename(old_logs_slot_dir)

        return False, " | ".join(dict.fromkeys(errors)), old_normalized_slot_name

    if old_data_slot_dir.exists():
        return False, f'A pasta antiga do slot ainda existe: "{old_data_slot_dir}"', old_normalized_slot_name

    if old_logs_slot_dir.exists():
        return False, f'A pasta antiga de logs do slot ainda existe: "{old_logs_slot_dir}"', old_normalized_slot_name

    meta["slots"] = [
        new_normalized_slot_name if name == old_normalized_slot_name else name
        for name in meta["slots"]
    ]

    if settings.normalize_slot_name(meta.get("active_slot", "")) == old_normalized_slot_name:
        meta["active_slot"] = new_normalized_slot_name

    if settings.normalize_slot_name(meta.get("default_slot", "")) == old_normalized_slot_name:
        meta["default_slot"] = new_normalized_slot_name

    save_slots_meta(meta)

    final_new_data_slot_dir = get_slots_root_dir() / new_normalized_slot_name
    if not final_new_data_slot_dir.exists():
        return False, f'A nova pasta do slot não foi encontrada após o rename: "{final_new_data_slot_dir}"', old_normalized_slot_name

    return True, f'Slot "{old_normalized_slot_name}" renomeado para "{new_normalized_slot_name}".', new_normalized_slot_name


def get_context_dir(
    context: Any = None,
    *,
    site_key: str | None = None,
    item_type_key: str | None = None,
    account_key: str | None = None,
    slot_name: str | None = None,
    ensure: bool = False,
) -> Path:
    identity = resolve_storage_identity(
        context,
        site_key=site_key,
        item_type_key=item_type_key,
        account_key=account_key,
        slot_name=slot_name,
    )
    path = (
        get_slot_dir(identity.slot_name, ensure=ensure)
        / identity.site_key
        / identity.item_type_key
        / identity.account_key
    )
    return ensure_dir(path) if ensure else path


def get_context_logs_dir(
    context: Any = None,
    *,
    site_key: str | None = None,
    item_type_key: str | None = None,
    account_key: str | None = None,
    slot_name: str | None = None,
    ensure: bool = False,
) -> Path:
    identity = resolve_storage_identity(
        context,
        site_key=site_key,
        item_type_key=item_type_key,
        account_key=account_key,
        slot_name=slot_name,
    )
    path = (
        get_logs_dir(ensure=ensure)
        / identity.slot_name
        / identity.site_key
        / identity.item_type_key
        / identity.account_key
    )
    return ensure_dir(path) if ensure else path


def build_context_paths(
    context: Any = None,
    *,
    site_key: str | None = None,
    item_type_key: str | None = None,
    account_key: str | None = None,
    slot_name: str | None = None,
    ensure: bool = True,
) -> ContextPaths:
    identity = resolve_storage_identity(
        context,
        site_key=site_key,
        item_type_key=item_type_key,
        account_key=account_key,
        slot_name=slot_name,
    )

    project_root = get_project_root()
    data_dir = get_data_dir(ensure=ensure)
    logs_dir = get_logs_dir(ensure=ensure)
    slots_root_dir = get_slots_root_dir(ensure=ensure)
    slots_meta_path = get_slots_meta_path(ensure_parent=ensure)
    slot_dir = get_slot_dir(identity.slot_name, ensure=ensure)
    context_dir = get_context_dir(identity, ensure=ensure)
    context_logs_dir = get_context_logs_dir(identity, ensure=ensure)

    return ContextPaths(
        identity=identity,
        project_root=project_root,
        data_dir=data_dir,
        logs_dir=logs_dir,
        slots_root_dir=slots_root_dir,
        slots_meta_path=slots_meta_path,
        slot_dir=slot_dir,
        context_dir=context_dir,
        context_logs_dir=context_logs_dir,
        output_csv_path=context_dir / settings.CATALOG_CSV_FILENAME,
        output_json_path=context_dir / settings.CATALOG_JSON_FILENAME,
        progress_json_path=context_dir / settings.PROGRESS_JSON_FILENAME,
        categories_cache_json_path=context_dir / settings.CATEGORIES_CACHE_JSON_FILENAME,
        queue_cache_json_path=context_dir / settings.QUEUE_CACHE_JSON_FILENAME,
        config_json_path=context_dir / settings.CONFIG_JSON_FILENAME,
        status_txt_path=context_dir / settings.STATUS_TXT_FILENAME,
        last_logs_txt_path=context_dir / settings.LAST_LOGS_TXT_FILENAME,
        runtime_log_path=context_logs_dir / settings.RUNTIME_LOG_FILENAME,
    )


def get_output_csv_path(context: Any = None, **kwargs: Any) -> Path:
    return build_context_paths(context, **kwargs).output_csv_path


def get_output_json_path(context: Any = None, **kwargs: Any) -> Path:
    return build_context_paths(context, **kwargs).output_json_path


def get_progress_json_path(context: Any = None, **kwargs: Any) -> Path:
    return build_context_paths(context, **kwargs).progress_json_path


def get_categories_cache_json_path(context: Any = None, **kwargs: Any) -> Path:
    return build_context_paths(context, **kwargs).categories_cache_json_path


def get_queue_cache_json_path(context: Any = None, **kwargs: Any) -> Path:
    return build_context_paths(context, **kwargs).queue_cache_json_path


def get_config_json_path(context: Any = None, **kwargs: Any) -> Path:
    return build_context_paths(context, **kwargs).config_json_path


def get_status_txt_path(context: Any = None, **kwargs: Any) -> Path:
    return build_context_paths(context, **kwargs).status_txt_path


def get_last_logs_txt_path(context: Any = None, **kwargs: Any) -> Path:
    return build_context_paths(context, **kwargs).last_logs_txt_path


def get_runtime_log_path(context: Any = None, **kwargs: Any) -> Path:
    return build_context_paths(context, **kwargs).runtime_log_path


def _remove_tree_checked(path: PathLike) -> tuple[bool, str]:
    resolved = coerce_path(path)

    if not resolved.exists():
        return True, ""

    try:
        shutil.rmtree(resolved)
    except FileNotFoundError:
        return True, ""
    except Exception as error:
        if resolved.exists():
            return False, f'Falha ao remover "{resolved}": {error}'
        return True, ""

    if resolved.exists():
        remaining_items: list[str] = []
        with suppress(Exception):
            remaining_items = [str(item) for item in resolved.rglob("*")][:10]

        if remaining_items:
            details = ", ".join(remaining_items)
            return False, f'Falha ao remover "{resolved}". Restos encontrados: {details}'

        return False, f'Falha ao remover "{resolved}". A pasta ainda existe após a tentativa.'

    return True, ""


def _prune_empty_parents_up_to(path: PathLike, stop_dir: PathLike) -> None:
    current = coerce_path(path)
    stop_path = coerce_path(stop_dir)

    while True:
        if current == stop_path:
            break

        if not current.exists() or not current.is_dir():
            current = current.parent
            continue

        try:
            next(current.iterdir())
            break
        except StopIteration:
            with suppress(Exception):
                current.rmdir()
            current = current.parent
        except Exception:
            break


def remove_slot_context(
    slot_name: str | None,
    site_key: str | None,
    item_type_key: str | None,
    account_key: str | None,
) -> tuple[bool, str]:
    meta = load_slots_meta()
    raw_slot_name = str(slot_name or "").strip()
    normalized_slot_name = settings.normalize_slot_name(raw_slot_name)
    normalized_site_key = str(site_key or "").strip()
    normalized_item_type_key = str(item_type_key or "").strip()
    normalized_account_key = str(account_key or "").strip()

    if raw_slot_name != normalized_slot_name:
        return False, "Nome de slot invalido."

    if normalized_slot_name not in meta["slots"]:
        return False, "Slot não encontrado."

    if any(
        value in {".", ".."} or "/" in value or "\\" in value
        for value in (normalized_site_key, normalized_item_type_key, normalized_account_key)
    ):
        return False, "Identidade de contexto invalida."

    if not normalized_site_key or not normalized_item_type_key or not normalized_account_key:
        return False, "Informe site, tipo e conta do contexto."

    data_context_dir = get_context_dir(
        site_key=normalized_site_key,
        item_type_key=normalized_item_type_key,
        account_key=normalized_account_key,
        slot_name=normalized_slot_name,
        ensure=False,
    )

    logs_context_dir = get_context_logs_dir(
        site_key=normalized_site_key,
        item_type_key=normalized_item_type_key,
        account_key=normalized_account_key,
        slot_name=normalized_slot_name,
        ensure=False,
    )

    if not data_context_dir.exists() and not logs_context_dir.exists():
        return False, "Contexto não encontrado no slot."

    errors: list[str] = []

    ok_data, error_data = _remove_tree_checked(data_context_dir)
    if not ok_data and error_data:
        errors.append(error_data)

    ok_logs, error_logs = _remove_tree_checked(logs_context_dir)
    if not ok_logs and error_logs:
        errors.append(error_logs)

    if errors:
        return False, " | ".join(dict.fromkeys(errors))

    _prune_empty_parents_up_to(
        data_context_dir.parent,
        get_slot_dir(normalized_slot_name),
    )

    _prune_empty_parents_up_to(
        logs_context_dir.parent,
        get_logs_dir() / normalized_slot_name,
    )

    return (
        True,
        f'Contexto "{normalized_site_key}/{normalized_item_type_key}/{normalized_account_key}" removido do slot "{normalized_slot_name}".',
    )


def delete_slot(slot_name: str | None) -> tuple[bool, str]:
    meta = load_slots_meta()
    raw_slot_name = str(slot_name or "").strip()
    normalized_slot_name = settings.normalize_slot_name(raw_slot_name)

    if raw_slot_name != normalized_slot_name:
        return False, "Nome de slot invalido."

    if normalized_slot_name not in meta["slots"]:
        return False, "Slot não encontrado."

    if normalized_slot_name == settings.DEFAULT_SLOT_NAME:
        return False, "O slot default não pode ser apagado."

    if normalized_slot_name == settings.normalize_slot_name(meta.get("default_slot", settings.DEFAULT_SLOT_NAME)):
        return False, "Remova o slot como default antes de apagar."

    data_slot_dir = get_slots_root_dir() / normalized_slot_name
    logs_slot_dir = get_logs_dir() / normalized_slot_name

    errors: list[str] = []

    ok_data, error_data = _remove_tree_checked(data_slot_dir)
    if not ok_data and error_data:
        errors.append(error_data)

    ok_logs, error_logs = _remove_tree_checked(logs_slot_dir)
    if not ok_logs and error_logs:
        errors.append(error_logs)

    if path_exists(data_slot_dir):
        errors.append(f'A pasta de dados do slot ainda existe: "{data_slot_dir}"')

    if path_exists(logs_slot_dir):
        errors.append(f'A pasta de logs do slot ainda existe: "{logs_slot_dir}"')

    if errors:
        return False, " | ".join(dict.fromkeys(errors))

    meta["slots"] = [name for name in meta["slots"] if name != normalized_slot_name]
    if not meta["slots"]:
        meta["slots"] = [settings.DEFAULT_SLOT_NAME]

    if meta.get("active_slot") == normalized_slot_name:
        meta["active_slot"] = settings.normalize_slot_name(
            meta.get("default_slot", settings.DEFAULT_SLOT_NAME)
        )

    save_slots_meta(meta)
    return True, "Slot apagado."


def clear_slot_contents(slot_name: str | None) -> tuple[bool, str]:
    meta = load_slots_meta()
    normalized_slot_name = settings.normalize_slot_name(slot_name)

    if normalized_slot_name not in meta["slots"]:
        return False, "Slot não encontrado."

    data_slot_dir = get_slot_dir(normalized_slot_name)
    logs_slot_dir = get_logs_dir() / normalized_slot_name

    errors: list[str] = []

    ok_data, error_data = _remove_tree_checked(data_slot_dir)
    if not ok_data and error_data:
        errors.append(error_data)

    ok_logs, error_logs = _remove_tree_checked(logs_slot_dir)
    if not ok_logs and error_logs:
        errors.append(error_logs)

    if errors:
        return False, " | ".join(errors)

    recreated_slot_dir = ensure_slot_dir(normalized_slot_name)

    if not recreated_slot_dir.exists() or not recreated_slot_dir.is_dir():
        return False, f'Não foi possível recriar o slot "{normalized_slot_name}" após a limpeza.'

    return True, f'Slot "{normalized_slot_name}" limpo com sucesso.'


# ============================================================
# CATÁLOGO / PROGRESSO
# ============================================================


def get_default_item_type_key() -> str:
    return str(getattr(settings, "DEFAULT_ITEM_TYPE_KEY", "plugin"))


def normalize_catalog_item(
    item: Mapping[str, Any] | None,
    *,
    default_item_type: str | None = None,
) -> dict[str, str]:
    item = dict(item or {})
    item_type = _normalize_spaces(
        item.get("tipo")
        or item.get("item_type_key")
        or default_item_type
        or get_default_item_type_key()
    ) or (default_item_type or get_default_item_type_key())

    is_template = item_type == "template"

    return {
        "tipo": item_type,
        "categoria_nome": _normalize_spaces(item.get("categoria_nome") or item.get("category_name", "")),
        "categoria_url": ensure_trailing_slash(item.get("categoria_url") or item.get("category_url", "")),
        "link_produto": _normalize_spaces(item.get("link_produto") or item.get("product_url", "")),
        "imagem_url": _normalize_spaces(item.get("imagem_url", "")) if is_template else "",
        "imagem_path": _normalize_spaces(item.get("imagem_path", "")) if is_template else "",
        "pagina_oficial": _normalize_spaces(item.get("pagina_oficial") or item.get("official_page_url", "")),
        "nome_produto": _normalize_spaces(item.get("nome_produto") or item.get("product_name", "")),
        "versao_produto": _normalize_version_value(item.get("versao_produto") or item.get("product_version", "")),
        "observacao": _normalize_spaces(item.get("observacao") or item.get("observation", "")),
    }


def normalize_catalog_items(
    items: Iterable[Mapping[str, Any]] | None,
    *,
    default_item_type: str | None = None,
    skip_empty_links: bool = True,
) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []

    for item in items or []:
        cleaned = normalize_catalog_item(item, default_item_type=default_item_type)
        if skip_empty_links and not cleaned["link_produto"]:
            continue
        normalized.append(cleaned)

    return normalized


def sort_catalog_items(
    items: Iterable[Mapping[str, Any]] | None,
    *,
    default_item_type: str | None = None,
) -> list[dict[str, str]]:
    normalized = normalize_catalog_items(
        items,
        default_item_type=default_item_type,
        skip_empty_links=True,
    )

    return sorted(
        normalized,
        key=lambda item: (
            _normalize_spaces(item.get("categoria_nome", "")).lower(),
            _normalize_spaces(item.get("nome_produto", "")).lower(),
            _normalize_spaces(item.get("link_produto", "")).lower(),
        ),
    )


def build_catalog_index(
    items: Iterable[Mapping[str, Any]] | None,
    *,
    default_item_type: str | None = None,
) -> dict[str, dict[str, str]]:
    catalog: dict[str, dict[str, str]] = {}

    for item in normalize_catalog_items(items, default_item_type=default_item_type, skip_empty_links=True):
        catalog[item["link_produto"]] = item

    return catalog


def _coerce_products_input(
    products: Mapping[str, Mapping[str, Any]] | Iterable[Mapping[str, Any]] | None,
) -> list[Mapping[str, Any]]:
    if products is None:
        return []

    if isinstance(products, Mapping):
        values = list(products.values())
        if values and all(isinstance(value, Mapping) for value in values):
            return list(values)

    return list(products)


def load_catalog_items(context: Any = None, **kwargs: Any) -> list[dict[str, str]]:
    path = get_output_json_path(context, **kwargs)
    data = read_json(path, [])
    if not isinstance(data, list):
        data = []
    return sort_catalog_items(data)


def load_existing_products_dict(
    context: Any = None,
    *,
    continue_enabled: bool | None = None,
    **kwargs: Any,
) -> dict[str, dict[str, str]]:
    enabled = get_continue_enabled_default() if continue_enabled is None else bool(continue_enabled)
    if not enabled:
        return {}

    items = load_catalog_items(context, **kwargs)
    return build_catalog_index(items)


def save_catalog_items(
    items: Iterable[Mapping[str, Any]] | None,
    context: Any = None,
    *,
    fieldnames: Sequence[str] = CATALOG_FIELDNAMES,
    **kwargs: Any,
) -> dict[str, Any]:
    paths = build_context_paths(context, **kwargs, ensure=True)
    sorted_items = sort_catalog_items(items)

    try:
        write_csv_atomic(paths.output_csv_path, fieldnames=fieldnames, rows=sorted_items)
        write_json_atomic(paths.output_json_path, sorted_items)
    except Exception as error:
        raise CatalogPersistenceError("Falha ao salvar catálogo.") from error

    return {
        "items": sorted_items,
        "total_saved": len(sorted_items),
        "output_csv_path": paths.output_csv_path,
        "output_json_path": paths.output_json_path,
    }


def load_progress_data(context: Any = None, **kwargs: Any) -> dict[str, Any]:
    path = get_progress_json_path(context, **kwargs)
    data = read_json(path, {})
    return data if isinstance(data, dict) else {}


def save_progress_data(
    progress_data: Mapping[str, Any] | None,
    context: Any = None,
    **kwargs: Any,
) -> dict[str, Any]:
    path = get_progress_json_path(context, **kwargs)
    payload = dict(progress_data or {})

    try:
        write_json_atomic(path, payload)
    except Exception as error:
        raise CatalogPersistenceError("Falha ao salvar progresso.") from error

    return payload


def build_progress_payload(
    total_saved: int,
    meta: Mapping[str, Any] | None = None,
    *,
    previous_progress: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    meta_payload = dict(meta or {})
    previous_progress = dict(previous_progress or {})

    previous_meta = previous_progress.get("meta", {})
    if not isinstance(previous_meta, dict):
        previous_meta = {}

    run_started_at = meta_payload.get("run_started_at") or previous_meta.get("run_started_at") or ""
    run_finished_at = meta_payload.get("run_finished_at") or previous_meta.get("run_finished_at") or ""

    if run_started_at:
        timer_seconds = calculate_duration_seconds(run_started_at, run_finished_at or None)
    else:
        timer_seconds = to_int(meta_payload.get("timer_seconds", previous_meta.get("timer_seconds", 0)), 0)

    meta_payload["run_started_at"] = run_started_at
    meta_payload["run_finished_at"] = run_finished_at
    meta_payload["timer_seconds"] = timer_seconds
    meta_payload["timer_text"] = format_duration_seconds(timer_seconds)

    return {
        "updated_at": now_iso(),
        "total_salvos": int(total_saved),
        "meta": meta_payload,
    }


def save_catalog_state(
    products: Mapping[str, Mapping[str, Any]] | Iterable[Mapping[str, Any]] | None,
    meta: Mapping[str, Any] | None = None,
    context: Any = None,
    *,
    fieldnames: Sequence[str] = CATALOG_FIELDNAMES,
    **kwargs: Any,
) -> dict[str, Any]:
    paths = build_context_paths(context, **kwargs, ensure=True)
    items = _coerce_products_input(products)

    saved_catalog = save_catalog_items(items, paths.identity, fieldnames=fieldnames)
    previous_progress = load_progress_data(paths.identity)
    progress_payload = build_progress_payload(
        total_saved=saved_catalog["total_saved"],
        meta=meta,
        previous_progress=previous_progress,
    )
    save_progress_data(progress_payload, paths.identity)

    return {
        "items": saved_catalog["items"],
        "total_saved": saved_catalog["total_saved"],
        "progress": progress_payload,
        "output_csv_path": paths.output_csv_path,
        "output_json_path": paths.output_json_path,
        "progress_json_path": paths.progress_json_path,
    }


def clear_catalog_outputs(
    context: Any = None,
    *,
    remove_progress: bool = True,
    **kwargs: Any,
) -> dict[str, bool]:
    paths = build_context_paths(context, **kwargs, ensure=True)
    removed = {
        "output_csv_path": remove_file(paths.output_csv_path, missing_ok=True),
        "output_json_path": remove_file(paths.output_json_path, missing_ok=True),
        "progress_json_path": False,
    }
    if remove_progress:
        removed["progress_json_path"] = remove_file(paths.progress_json_path, missing_ok=True)
    return removed


def rebuild_catalog_outputs_from_json(
    context: Any = None,
    *,
    fieldnames: Sequence[str] = CATALOG_FIELDNAMES,
    **kwargs: Any,
) -> dict[str, Any]:
    items = load_catalog_items(context, **kwargs)
    return save_catalog_items(items, context, fieldnames=fieldnames, **kwargs)


def normalize_product_for_comparison(
    product: Mapping[str, Any] | None,
    *,
    default_item_type: str | None = None,
) -> dict[str, str]:
    return normalize_catalog_item(product, default_item_type=default_item_type)


def merge_existing_product(
    existing_product: Mapping[str, Any] | None,
    new_product: Mapping[str, Any] | None,
    *,
    default_item_type: str | None = None,
) -> dict[str, str]:
    existing = normalize_product_for_comparison(existing_product, default_item_type=default_item_type)
    new = normalize_product_for_comparison(new_product, default_item_type=default_item_type)

    def choose(new_value: str, old_value: str, *, allow_empty: bool = False) -> str:
        if allow_empty:
            return new_value
        return new_value if _normalize_spaces(new_value) else old_value

    resolved_type = choose(new.get("tipo", ""), existing.get("tipo", "")) or get_default_item_type_key()
    is_template = resolved_type == "template"

    return {
        "tipo": resolved_type,
        "categoria_nome": choose(new.get("categoria_nome", ""), existing.get("categoria_nome", "")),
        "categoria_url": ensure_trailing_slash(choose(new.get("categoria_url", ""), existing.get("categoria_url", ""))),
        "link_produto": choose(new.get("link_produto", ""), existing.get("link_produto", "")),
        "imagem_url": choose(new.get("imagem_url", ""), existing.get("imagem_url", "")) if is_template else "",
        "imagem_path": choose(new.get("imagem_path", ""), existing.get("imagem_path", "")) if is_template else "",
        "pagina_oficial": choose(new.get("pagina_oficial", ""), existing.get("pagina_oficial", "")),
        "nome_produto": choose(new.get("nome_produto", ""), existing.get("nome_produto", "")),
        "versao_produto": choose(new.get("versao_produto", ""), existing.get("versao_produto", "")),
        "observacao": choose(new.get("observacao", ""), existing.get("observacao", "")),
    }


def describe_product_changes(
    old_product: Mapping[str, Any] | None,
    final_product: Mapping[str, Any] | None,
    *,
    default_item_type: str | None = None,
) -> list[str]:
    old = normalize_product_for_comparison(old_product, default_item_type=default_item_type)
    final = normalize_product_for_comparison(final_product, default_item_type=default_item_type)
    changes: list[str] = []

    if old.get("nome_produto", "") != final.get("nome_produto", ""):
        changes.append("nome atualizado")
    if old.get("versao_produto", "") != final.get("versao_produto", ""):
        changes.append("versão atualizada")
    if old.get("imagem_url", "") != final.get("imagem_url", ""):
        changes.append("url da imagem atualizada")
    if old.get("imagem_path", "") != final.get("imagem_path", ""):
        changes.append("imagem baixada/atualizada")
    if old.get("pagina_oficial", "") != final.get("pagina_oficial", ""):
        changes.append("página oficial atualizada")
    if old.get("observacao", "") != final.get("observacao", ""):
        changes.append("observação atualizada")
    if old.get("categoria_nome", "") != final.get("categoria_nome", ""):
        changes.append("categoria atualizada")

    return changes


# ============================================================
# FILA / CONTINUAÇÃO
# ============================================================


def clean_queue_item(
    item: Mapping[str, Any] | None,
    *,
    default_item_type: str | None = None,
) -> dict[str, str]:
    item = dict(item or {})
    return {
        "tipo": _normalize_spaces(item.get("tipo", "")) or (default_item_type or get_default_item_type_key()),
        "categoria_nome": _normalize_spaces(item.get("categoria_nome", "")),
        "categoria_url": ensure_trailing_slash(item.get("categoria_url", "")),
        "link_produto": _normalize_spaces(item.get("link_produto", "")),
        "nome_lista": _normalize_spaces(item.get("nome_lista", "")),
        "versao_lista": _normalize_spaces(item.get("versao_lista", "")),
    }


def clean_queue_items(
    items: Iterable[Mapping[str, Any]] | None,
    *,
    default_item_type: str | None = None,
) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for item in items or []:
        normalized = clean_queue_item(item, default_item_type=default_item_type)
        if normalized["link_produto"]:
            cleaned.append(normalized)
    return cleaned


def get_resume_info(
    meta: Mapping[str, Any] | None,
    *,
    allowed_run_modes_with_detail: set[str] | None = None,
    run_mode_labels: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    meta_dict = dict(meta or {})
    allowed_run_modes = set(allowed_run_modes_with_detail or ())
    labels = dict(run_mode_labels or {})

    full_queue = clean_queue_items(meta_dict.get("resume_full_queue_items", []) or [])
    queue_total = len(full_queue) if full_queue else to_int(meta_dict.get("resume_queue_total", 0), 0)
    queue_index = max(0, to_int(meta_dict.get("resume_queue_index", 0), 0))
    if queue_index > queue_total:
        queue_index = queue_total

    run_mode = _normalize_spaces(meta_dict.get("run_mode", ""))
    status = _normalize_spaces(meta_dict.get("status", "")).lower()

    can_continue = (
        run_mode in allowed_run_modes
        and status in {"em_andamento", "interrompido"}
        and queue_total > 0
        and queue_index < queue_total
    )

    return {
        "can_continue": can_continue,
        "run_mode": run_mode,
        "run_mode_label": labels.get(run_mode, run_mode),
        "full_queue": full_queue,
        "queue_total": queue_total,
        "queue_index": queue_index,
    }


# ============================================================
# ESTADO / STATUS / LOGS
# ============================================================


def _get_run_mode_labels() -> dict[str, str]:
    labels = getattr(settings, "RUN_MODE_LABELS", None)
    if isinstance(labels, Mapping):
        return {str(key): str(value) for key, value in dict(labels).items()}
    return {
        "full_sync": "Iniciar",
        "categories_only": "Atualizar categorias",
        "links_only": "Detectar links",
        "existing_review": "Revisar existentes",
        "primary": "Iniciar",
    }


def _get_default_run_mode() -> str:
    return str(getattr(settings, "RUN_MODE_FULL", "full_sync") or "full_sync")


def _safe_build_context(
    context: Any = None,
    *,
    site_key: str | None = None,
    item_type_key: str | None = None,
    account_key: str | None = None,
    slot_name: str | None = None,
) -> Any:
    try:
        return build_context(
            context,
            site_key=site_key,
            item_type_key=item_type_key,
            account_key=account_key,
            slot_name=slot_name,
        )
    except Exception:
        fallback = {
            "site_key": site_key or getattr(settings, "DEFAULT_SITE_KEY", "ultrapackv2"),
            "item_type_key": item_type_key or getattr(settings, "DEFAULT_ITEM_TYPE_KEY", "plugin"),
            "account_key": account_key or getattr(settings, "DEFAULT_ACCOUNT_KEY", "coproducaolancamentos"),
            "slot_name": slot_name or get_active_slot_name(),
        }
        if isinstance(context, Mapping):
            fallback.update(dict(context))
        return fallback


def _read_context_field(context: Any, name: str, default: str = "") -> str:
    if context is None:
        return default
    if isinstance(context, Mapping):
        value = context.get(name, default)
    else:
        value = getattr(context, name, default)
    text = str(value or "").strip()
    return text or default


def _build_context_prefix(context: Any) -> str:
    if context is None:
        return ""

    value = getattr(context, "context_prefix", "")
    if value:
        return str(value)

    return "_".join(
        part
        for part in (
            _read_context_field(context, "site_key"),
            _read_context_field(context, "item_type_key"),
            _read_context_field(context, "account_key"),
        )
        if part
    )


def _safe_slots_public_list() -> list[dict[str, Any]]:
    try:
        return build_slots_public_list()
    except Exception:
        return []


def build_default_runtime_state(
    context: Any = None,
    *,
    site_key: str | None = None,
    item_type_key: str | None = None,
    account_key: str | None = None,
    slot_name: str | None = None,
) -> dict[str, Any]:
    resolved_context = _safe_build_context(
        context,
        site_key=site_key,
        item_type_key=item_type_key,
        account_key=account_key,
        slot_name=slot_name,
    )

    run_mode = _get_default_run_mode()
    run_mode_labels = _get_run_mode_labels()
    current_slot = _read_context_field(resolved_context, "slot_name", get_active_slot_name())
    default_slot = get_default_slot_name()

    return {
        "site_key": _read_context_field(resolved_context, "site_key", settings.DEFAULT_SITE_KEY),
        "item_type_key": _read_context_field(resolved_context, "item_type_key", settings.DEFAULT_ITEM_TYPE_KEY),
        "account_key": _read_context_field(resolved_context, "account_key", settings.DEFAULT_ACCOUNT_KEY),
        "slot_name": current_slot,
        "context_prefix": _build_context_prefix(resolved_context),
        "status": "Parado",
        "summary": "Aguardando início",
        "run_mode": run_mode,
        "run_mode_label": run_mode_labels.get(run_mode, run_mode),
        "current_phase": "-",
        "current_category": "-",
        "current_item": "-",
        "saved_count": 0,
        "pending_count": 0,
        "running": False,
        "updated_at": "",
        "reused_categories": 0,
        "refetched_categories": 0,
        "verify_mode": str(getattr(settings, "DEFAULT_VERIFY_MODE", "complete")),
        "scope_mode": str(getattr(settings, "DEFAULT_SCOPE_MODE", "all")),
        "scope_start": int(getattr(settings, "DEFAULT_SCOPE_START", 1)),
        "scope_end": int(getattr(settings, "DEFAULT_SCOPE_END", 0)),
        "scope_match_text": str(getattr(settings, "DEFAULT_SCOPE_MATCH_TEXT", "")),
        "save_every_items": int(getattr(settings, "DEFAULT_SAVE_EVERY_ITEMS", 10)),
        "save_every_minutes": int(getattr(settings, "DEFAULT_SAVE_EVERY_MINUTES", 10)),
        "available_categories": [],
        "selected_categories": [],
        "queue_detected_count": 0,
        "new_links_detected": 0,
        "existing_links_detected": 0,
        "new_items_added": 0,
        "items_updated": 0,
        "items_unchanged": 0,
        "can_continue": False,
        "primary_button_label": "▶️ Iniciar",
        "resume_run_mode": run_mode,
        "resume_run_mode_label": run_mode_labels.get(run_mode, run_mode),
        "resume_queue_index": 0,
        "resume_queue_total": 0,
        "current_slot": current_slot,
        "default_slot": default_slot,
        "slots": _safe_slots_public_list(),
        "timer_seconds": 0,
        "timer_text": "0:00:00",
        "run_started_at": "",
        "run_finished_at": "",
    }


def normalize_logs_list(
    logs: Iterable[Any] | str | None,
    *,
    max_items: int | None = None,
) -> list[str]:
    if logs is None:
        items: list[str] = []
    elif isinstance(logs, str):
        items = logs.splitlines()
    else:
        items = [str(item) for item in logs]

    if max_items is not None and max_items >= 0:
        items = items[-max_items:]

    return items


def _extract_state_data(source: Any) -> dict[str, Any]:
    if source is None:
        return {}

    if isinstance(source, Mapping):
        if isinstance(source.get("data"), Mapping):
            return dict(source.get("data", {}))
        return dict(source)

    snapshot = getattr(source, "snapshot", None)
    if callable(snapshot):
        return _extract_state_data(snapshot())

    state = getattr(source, "state", None)
    if state is not None:
        snapshot = getattr(state, "snapshot", None)
        if callable(snapshot):
            return _extract_state_data(snapshot())

    data = getattr(source, "data", None)
    if isinstance(data, Mapping):
        return dict(data)

    return {}


def _extract_full_logs_text(source: Any) -> str:
    if source is None:
        return ""

    if isinstance(source, Mapping):
        logs = source.get("logs")
        if isinstance(logs, str):
            return logs
        if logs is not None:
            return "\n".join(normalize_logs_list(logs))

    full_logs_text = getattr(source, "full_logs_text", None)
    if callable(full_logs_text):
        with suppress(Exception):
            return str(full_logs_text())

    state = getattr(source, "state", None)
    if state is not None:
        full_logs_text = getattr(state, "full_logs_text", None)
        if callable(full_logs_text):
            with suppress(Exception):
                return str(full_logs_text())

        snapshot = getattr(state, "snapshot", None)
        if callable(snapshot):
            snap = snapshot()
            if isinstance(snap, Mapping):
                logs = snap.get("logs")
                if isinstance(logs, str):
                    return logs
                if logs is not None:
                    return "\n".join(normalize_logs_list(logs))

    snapshot = getattr(source, "snapshot", None)
    if callable(snapshot):
        snap = snapshot()
        if isinstance(snap, Mapping):
            logs = snap.get("logs")
            if isinstance(logs, str):
                return logs
            if logs is not None:
                return "\n".join(normalize_logs_list(logs))

    logs = getattr(source, "logs", None)
    if isinstance(logs, str):
        return logs
    if logs is not None:
        return "\n".join(normalize_logs_list(logs))

    return ""


def normalize_state_data(
    data: Mapping[str, Any] | None,
    context: Any = None,
    *,
    site_key: str | None = None,
    item_type_key: str | None = None,
    account_key: str | None = None,
    slot_name: str | None = None,
) -> dict[str, Any]:
    normalized = build_default_runtime_state(
        context,
        site_key=site_key,
        item_type_key=item_type_key,
        account_key=account_key,
        slot_name=slot_name,
    )

    if isinstance(data, Mapping):
        normalized.update(dict(data))

    run_mode_labels = _get_run_mode_labels()
    run_mode = str(normalized.get("run_mode", _get_default_run_mode()) or _get_default_run_mode()).strip()
    resume_run_mode = str(normalized.get("resume_run_mode", run_mode) or run_mode).strip()

    normalized["run_mode"] = run_mode
    normalized["resume_run_mode"] = resume_run_mode
    normalized["run_mode_label"] = run_mode_labels.get(run_mode, str(normalized.get("run_mode_label", run_mode) or run_mode))
    normalized["resume_run_mode_label"] = run_mode_labels.get(
        resume_run_mode,
        str(normalized.get("resume_run_mode_label", resume_run_mode) or resume_run_mode),
    )

    normalized["running"] = bool(normalized.get("running", False))
    normalized["can_continue"] = bool(normalized.get("can_continue", False))

    for key in (
        "saved_count",
        "pending_count",
        "reused_categories",
        "refetched_categories",
        "scope_start",
        "scope_end",
        "save_every_items",
        "save_every_minutes",
        "queue_detected_count",
        "new_links_detected",
        "existing_links_detected",
        "new_items_added",
        "items_updated",
        "items_unchanged",
        "resume_queue_index",
        "resume_queue_total",
        "timer_seconds",
    ):
        normalized[key] = to_int(normalized.get(key, 0), 0)

    if normalized["save_every_items"] <= 0:
        normalized["save_every_items"] = int(getattr(settings, "DEFAULT_SAVE_EVERY_ITEMS", 5))
    if normalized["save_every_minutes"] <= 0:
        normalized["save_every_minutes"] = int(getattr(settings, "DEFAULT_SAVE_EVERY_MINUTES", 1))
    if normalized["scope_start"] <= 0:
        normalized["scope_start"] = 1
    if normalized["scope_end"] < 0:
        normalized["scope_end"] = 0

    for key in (
        "status",
        "summary",
        "current_phase",
        "current_category",
        "current_item",
        "verify_mode",
        "scope_mode",
        "scope_match_text",
        "run_started_at",
        "run_finished_at",
        "updated_at",
        "current_slot",
        "default_slot",
        "site_key",
        "item_type_key",
        "account_key",
        "slot_name",
        "context_prefix",
    ):
        normalized[key] = str(normalized.get(key, "") or "")

    if not normalized["current_slot"]:
        normalized["current_slot"] = normalized.get("slot_name") or get_active_slot_name()
    if not normalized["slot_name"]:
        normalized["slot_name"] = normalized["current_slot"]
    if not normalized["default_slot"]:
        normalized["default_slot"] = get_default_slot_name()

    normalized["available_categories"] = normalize_available_categories_list(normalized.get("available_categories", []))

    selected_categories_raw = normalized.get("selected_categories", [])
    if not isinstance(selected_categories_raw, list):
        selected_categories_raw = []
    normalized["selected_categories"] = sorted({
        ensure_trailing_slash(_normalize_spaces(value))
        for value in selected_categories_raw
        if _normalize_spaces(value)
    })

    if not isinstance(normalized.get("slots"), list):
        normalized["slots"] = _safe_slots_public_list()

    saved_count = normalized["saved_count"]
    if not str(normalized.get("primary_button_label", "")).strip():
        normalized["primary_button_label"] = "▶️ Retomar" if saved_count > 0 else "▶️ Iniciar"

    run_started_at = normalized.get("run_started_at", "")
    run_finished_at = normalized.get("run_finished_at", "")
    if run_started_at and normalized["running"]:
        timer_seconds = calculate_duration_seconds(run_started_at)
    elif run_started_at and run_finished_at:
        timer_seconds = calculate_duration_seconds(run_started_at, run_finished_at)
    else:
        timer_seconds = to_int(normalized.get("timer_seconds", 0), 0)

    normalized["timer_seconds"] = max(0, timer_seconds)
    normalized["timer_text"] = format_duration_seconds(normalized["timer_seconds"])

    return normalized


def build_state_payload(
    data: Mapping[str, Any] | None = None,
    logs: Iterable[Any] | str | None = None,
    context: Any = None,
    *,
    site_key: str | None = None,
    item_type_key: str | None = None,
    account_key: str | None = None,
    slot_name: str | None = None,
    max_logs: int | None = 600,
) -> dict[str, Any]:
    return {
        "data": normalize_state_data(
            data,
            context,
            site_key=site_key,
            item_type_key=item_type_key,
            account_key=account_key,
            slot_name=slot_name,
        ),
        "logs": normalize_logs_list(logs, max_items=max_logs),
    }


def build_status_text(
    source: Any = None,
    context: Any = None,
    *,
    site_key: str | None = None,
    item_type_key: str | None = None,
    account_key: str | None = None,
    slot_name: str | None = None,
) -> str:
    state_data = normalize_state_data(
        _extract_state_data(source),
        context,
        site_key=site_key,
        item_type_key=item_type_key,
        account_key=account_key,
        slot_name=slot_name,
    )

    resume_total = to_int(state_data.get("resume_queue_total", 0), 0)
    resume_label = state_data.get("resume_run_mode_label", "-") if resume_total > 0 else "-"

    lines = [
        f"Site atual: {state_data.get('site_key', '-') or '-'}",
        f"Tipo atual: {state_data.get('item_type_key', '-') or '-'}",
        f"Conta atual: {state_data.get('account_key', '-') or '-'}",
        f"Slot atual: {state_data.get('current_slot', '-') or '-'}",
        f"Slot default: {state_data.get('default_slot', '-') or '-'}",
    ]

    context_prefix = str(state_data.get("context_prefix", "") or "").strip()
    if context_prefix:
        lines.append(f"Prefixo do contexto: {context_prefix}")

    lines.extend([
        f"Estado: {state_data.get('status', '-') or '-'}",
        f"Fluxo atual: {state_data.get('run_mode_label', '-') or '-'}",
        f"Fase atual: {state_data.get('current_phase', '-') or '-'}",
        f"Tempo: {state_data.get('timer_text', '0:00:00') or '0:00:00'}",
        f"Resumo: {state_data.get('summary', '-') or '-'}",
        f"Validação atual: {state_data.get('verify_mode', '-') or '-'}",
        f"Escopo atual: {state_data.get('scope_mode', '-') or '-'}",
        f"Salvar a cada itens: {to_int(state_data.get('save_every_items', 0), 0)}",
        f"Salvar a cada minutos: {to_int(state_data.get('save_every_minutes', 0), 0)}",
        f"Categoria atual: {state_data.get('current_category', '-') or '-'}",
        f"Item atual: {state_data.get('current_item', '-') or '-'}",
        f"Itens salvos: {to_int(state_data.get('saved_count', 0), 0)}",
        f"Itens pendentes: {to_int(state_data.get('pending_count', 0), 0)}",
        f"Itens em fila: {to_int(state_data.get('queue_detected_count', 0), 0)}",
        f"Novos links detectados: {to_int(state_data.get('new_links_detected', 0), 0)}",
        f"Links existentes detectados: {to_int(state_data.get('existing_links_detected', 0), 0)}",
        f"Novos itens adicionados: {to_int(state_data.get('new_items_added', 0), 0)}",
        f"Itens atualizados: {to_int(state_data.get('items_updated', 0), 0)}",
        f"Itens sem mudança: {to_int(state_data.get('items_unchanged', 0), 0)}",
        f"Categorias reutilizadas: {to_int(state_data.get('reused_categories', 0), 0)}",
        f"Categorias refeitas: {to_int(state_data.get('refetched_categories', 0), 0)}",
        (
            "Fila de continuação: "
            f"{to_int(state_data.get('resume_queue_index', 0), 0)}/"
            f"{resume_total} • {resume_label}"
        ),
        f"Última atualização: {state_data.get('updated_at', '-') or '-'}",
        f"Run started at: {state_data.get('run_started_at', '-') or '-'}",
        f"Run finished at: {state_data.get('run_finished_at', '-') or '-'}",
    ])

    return "\n".join(lines) + "\n"


def load_status_text(context: Any = None, **kwargs: Any) -> str:
    return read_text(get_status_txt_path(context, **kwargs), "")


def save_status_text(
    source: Any = None,
    context: Any = None,
    *,
    path: str | Path | None = None,
    **kwargs: Any,
) -> Path:
    target_path = Path(path) if path is not None else get_status_txt_path(context, **kwargs)
    text = build_status_text(source, context, **kwargs)
    try:
        return write_text_atomic(target_path, text)
    except Exception as error:
        raise StatusPersistenceError("Falha ao salvar status.txt.") from error


def load_full_logs_text(context: Any = None, **kwargs: Any) -> str:
    return read_text(get_last_logs_txt_path(context, **kwargs), "")


def save_full_logs_text(
    source: Any = None,
    context: Any = None,
    *,
    path: str | Path | None = None,
    also_save_status: bool = True,
    **kwargs: Any,
) -> Path:
    target_path = Path(path) if path is not None else get_last_logs_txt_path(context, **kwargs)
    logs_text = _extract_full_logs_text(source)
    try:
        saved_path = write_text_atomic(target_path, logs_text)
    except Exception as error:
        raise StatusPersistenceError("Falha ao salvar logs completos.") from error

    if also_save_status:
        save_status_text(source, context, **kwargs)

    return saved_path


def load_runtime_log_text(context: Any = None, **kwargs: Any) -> str:
    return read_text(get_runtime_log_path(context, **kwargs), "")


def format_log_line(message: Any, *, timestamp: str | None = None) -> str:
    prefix_time = str(timestamp or now_iso())
    return f"[{prefix_time}] {str(message or '').rstrip()}"


def append_runtime_log_line(
    message: Any,
    context: Any = None,
    *,
    timestamp: str | None = None,
    **kwargs: Any,
) -> Path:
    path = get_runtime_log_path(context, **kwargs)
    try:
        return append_text(path, format_log_line(message, timestamp=timestamp), ensure_newline=True)
    except Exception as error:
        raise StatusPersistenceError("Falha ao acrescentar runtime log.") from error


def clear_status_files(
    context: Any = None,
    *,
    remove_status: bool = True,
    remove_last_logs: bool = True,
    remove_runtime_log: bool = True,
    **kwargs: Any,
) -> dict[str, bool]:
    paths = build_context_paths(context, **kwargs, ensure=True)
    removed = {
        "status_txt_path": False,
        "last_logs_txt_path": False,
        "runtime_log_path": False,
    }
    if remove_status:
        removed["status_txt_path"] = remove_file(paths.status_txt_path, missing_ok=True)
    if remove_last_logs:
        removed["last_logs_txt_path"] = remove_file(paths.last_logs_txt_path, missing_ok=True)
    if remove_runtime_log:
        removed["runtime_log_path"] = remove_file(paths.runtime_log_path, missing_ok=True)
    return removed


# ============================================================
# CONFIG / CACHE / ESCOPO
# ============================================================


def _get_default_run_options() -> dict[str, Any]:
    builder = getattr(settings, "build_default_run_options", None)
    if callable(builder):
        with suppress(Exception):
            data = builder()
            if isinstance(data, dict):
                return dict(data)

    return {
        "verify_mode": str(getattr(settings, "DEFAULT_VERIFY_MODE", "complete")),
        "scope_mode": "all",
        "scope_start": 1,
        "scope_end": 0,
        "scope_match_text": "",
        "save_every_items": int(getattr(settings, "DEFAULT_SAVE_EVERY_ITEMS", 10)),
        "save_every_minutes": int(getattr(settings, "DEFAULT_SAVE_EVERY_MINUTES", 10)),
        "selected_categories": [],
    }


def _get_allowed_verify_modes() -> set[str]:
    values = getattr(settings, "VERIFY_MODES", {"normal", "complete"})
    try:
        return {str(value).strip().lower() for value in values if str(value).strip()}
    except Exception:
        return {"normal", "complete"}


def _get_allowed_scope_modes() -> set[str]:
    values = getattr(settings, "SCOPE_MODES", {"all", "range", "match", "selected"})
    try:
        return {str(value).strip().lower() for value in values if str(value).strip()}
    except Exception:
        return {"all", "range", "match", "selected"}


def build_default_config() -> dict[str, Any]:
    base = _get_default_run_options()
    return {
        "verify_mode": str(base.get("verify_mode", settings.DEFAULT_VERIFY_MODE) or settings.DEFAULT_VERIFY_MODE),
        "scope_mode": str(base.get("scope_mode", "all") or "all"),
        "scope_start": max(1, to_int(base.get("scope_start", 1), 1)),
        "scope_end": max(0, to_int(base.get("scope_end", 0), 0)),
        "scope_match_text": str(base.get("scope_match_text", "") or ""),
        "save_every_items": max(1, to_int(base.get("save_every_items", settings.DEFAULT_SAVE_EVERY_ITEMS), settings.DEFAULT_SAVE_EVERY_ITEMS)),
        "save_every_minutes": max(1, to_int(base.get("save_every_minutes", settings.DEFAULT_SAVE_EVERY_MINUTES), settings.DEFAULT_SAVE_EVERY_MINUTES)),
        "selected_categories": list(base.get("selected_categories", []) or []),
    }


def normalize_config_dict(config: Mapping[str, Any] | None) -> dict[str, Any]:
    base = build_default_config()
    if isinstance(config, Mapping):
        base.update(dict(config))

    verify_mode = str(base.get("verify_mode", settings.DEFAULT_VERIFY_MODE) or settings.DEFAULT_VERIFY_MODE).strip().lower()
    if verify_mode not in _get_allowed_verify_modes():
        verify_mode = settings.DEFAULT_VERIFY_MODE

    scope_mode = str(base.get("scope_mode", "all") or "all").strip().lower()
    if scope_mode not in _get_allowed_scope_modes():
        scope_mode = "all"

    scope_start = max(1, to_int(base.get("scope_start", 1), 1))
    scope_end = max(0, to_int(base.get("scope_end", 0), 0))
    scope_match_text = str(base.get("scope_match_text", "") or "")
    save_every_items = max(1, to_int(base.get("save_every_items", settings.DEFAULT_SAVE_EVERY_ITEMS), settings.DEFAULT_SAVE_EVERY_ITEMS))
    save_every_minutes = max(1, to_int(base.get("save_every_minutes", settings.DEFAULT_SAVE_EVERY_MINUTES), settings.DEFAULT_SAVE_EVERY_MINUTES))

    selected_categories_raw = base.get("selected_categories", [])
    if not isinstance(selected_categories_raw, list):
        selected_categories_raw = []

    selected_categories = sorted({
        ensure_trailing_slash(_normalize_spaces(value))
        for value in selected_categories_raw
        if _normalize_spaces(value)
    })

    return {
        "verify_mode": verify_mode,
        "scope_mode": scope_mode,
        "scope_start": scope_start,
        "scope_end": scope_end,
        "scope_match_text": scope_match_text,
        "save_every_items": save_every_items,
        "save_every_minutes": save_every_minutes,
        "selected_categories": selected_categories,
    }


def load_context_config(context: Any = None, **kwargs: Any) -> dict[str, Any]:
    path = get_config_json_path(context, **kwargs)
    raw = read_json(path, {})
    if not isinstance(raw, dict):
        raw = {}
    return normalize_config_dict(raw)


def save_context_config(
    config: Mapping[str, Any] | None,
    context: Any = None,
    **kwargs: Any,
) -> dict[str, Any]:
    current = load_context_config(context, **kwargs)
    if isinstance(config, Mapping):
        current.update(dict(config))
    normalized = normalize_config_dict(current)

    try:
        write_json_atomic(get_config_json_path(context, **kwargs), normalized)
    except Exception as error:
        raise CachePersistenceError("Falha ao salvar config.json.") from error

    return normalized


def _normalize_queue_context_entry(entry: Mapping[str, Any] | None) -> dict[str, str]:
    raw = dict(entry or {})

    return {
        "site_key": settings.normalize_site_key(raw.get("site_key")),
        "item_type_key": settings.normalize_item_type_key(raw.get("item_type_key")),
        "account_key": settings.normalize_account_key(raw.get("account_key")),
        "slot_name": settings.normalize_slot_name(raw.get("slot_name")),
    }


def _queue_context_key(entry: Mapping[str, Any] | None) -> tuple[str, str, str, str]:
    normalized = _normalize_queue_context_entry(entry)
    return (
        normalized["site_key"],
        normalized["item_type_key"],
        normalized["account_key"],
        normalized["slot_name"],
    )


def normalize_run_queue_rules(rules: Any) -> list[dict[str, Any]]:
    normalized_rules: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str, str, str], tuple[str, str, str, str]]] = set()

    if not isinstance(rules, list):
        rules = []

    for index, raw in enumerate(rules, start=1):
        if not isinstance(raw, Mapping):
            continue

        source = _normalize_queue_context_entry(raw.get("source"))
        target = _normalize_queue_context_entry(raw.get("target"))

        if source == target:
            continue

        pair_key = (_queue_context_key(source), _queue_context_key(target))
        if pair_key in seen:
            continue
        adjacency: dict[tuple[str, str, str, str], set[tuple[str, str, str, str]]] = {}
        for existing in normalized_rules:
            adjacency.setdefault(_queue_context_key(existing["source"]),set()).add(_queue_context_key(existing["target"]))
        pending=[pair_key[1]];visited=set();creates_cycle=False
        while pending:
            current=pending.pop()
            if current==pair_key[0]:creates_cycle=True;break
            if current in visited:continue
            visited.add(current);pending.extend(adjacency.get(current,set()))
        if creates_cycle:
            continue
        seen.add(pair_key)

        normalized_rules.append(
            {
                "id": _normalize_spaces(raw.get("id")) or f"fila-{index}",
                "enabled": bool(raw.get("enabled", True)),
                "source": source,
                "target": target,
            }
        )

    return normalized_rules


def load_run_queue_rules() -> list[dict[str, Any]]:
    raw = read_json(settings.FILA_JSON_PATH, {"rules": []})

    if isinstance(raw, Mapping):
        rules = raw.get("rules", [])
    else:
        rules = []

    return normalize_run_queue_rules(rules)


def save_run_queue_rules(rules: Any) -> list[dict[str, Any]]:
    normalized = normalize_run_queue_rules(rules)

    try:
        write_json_atomic(settings.FILA_JSON_PATH, {"rules": normalized})
    except Exception as error:
        raise CachePersistenceError("Falha ao salvar fila.json.") from error

    return normalized


def _normalize_category_cache_entry(entry: Mapping[str, Any] | None, *, fallback_url: str = "") -> dict[str, Any]:
    entry = dict(entry or {})
    category_url = ensure_trailing_slash(entry.get("categoria_url", "") or fallback_url)
    return {
        "categoria_nome": _normalize_spaces(entry.get("categoria_nome", "")),
        "categoria_url": category_url,
        "total_esperado": to_int(entry.get("total_esperado", 0), 0),
        "total_coletado": to_int(entry.get("total_coletado", 0), 0),
        "catalogada": bool(entry.get("catalogada", False)),
        "origem": _normalize_spaces(entry.get("origem", "")),
        "links_signature": _normalize_spaces(entry.get("links_signature", "")),
        "links_count": to_int(entry.get("links_count", 0), 0),
        "coletados_brutos": to_int(entry.get("coletados_brutos", 0), 0),
        "coletados_unicos": to_int(entry.get("coletados_unicos", 0), 0),
        "duplicados_internos": to_int(entry.get("duplicados_internos", 0), 0),
        "paginas_visitadas": to_int(entry.get("paginas_visitadas", 0), 0),
        "paginas_repetidas": to_int(entry.get("paginas_repetidas", 0), 0),
        "paginas_sem_ganho": to_int(entry.get("paginas_sem_ganho", 0), 0),
        "faltantes_estimados": to_int(entry.get("faltantes_estimados", 0), 0),
        "resgatados_do_cache": to_int(entry.get("resgatados_do_cache", 0), 0),
        "itens_novos_fila": to_int(entry.get("itens_novos_fila", 0), 0),
        "itens_existentes_fila": to_int(entry.get("itens_existentes_fila", 0), 0),
        "status_coleta": _normalize_spaces(entry.get("status_coleta", "")),
        "diagnostico_resumido": _normalize_spaces(entry.get("diagnostico_resumido", "")),
        "confiabilidade_score": to_int(entry.get("confiabilidade_score", 100), 100),
        "execucoes_total": to_int(entry.get("execucoes_total", 0), 0),
        "execucoes_ok": to_int(entry.get("execucoes_ok", 0), 0),
        "execucoes_incompletas": to_int(entry.get("execucoes_incompletas", 0), 0),
        "consecutivas_incompletas": to_int(entry.get("consecutivas_incompletas", 0), 0),
        "ultima_verificacao_integridade": str(entry.get("ultima_verificacao_integridade", "") or ""),
        "ultima_atualizacao": str(entry.get("ultima_atualizacao", "") or ""),
    }


def _normalize_queue_cache_entry(entry: Mapping[str, Any] | None, *, fallback_url: str = "") -> dict[str, Any]:
    entry = dict(entry or {})
    items = clean_queue_items(entry.get("itens", []) or [])
    return {
        "categoria_nome": _normalize_spaces(entry.get("categoria_nome", "")),
        "categoria_url": ensure_trailing_slash(entry.get("categoria_url", "") or fallback_url),
        "total_esperado": to_int(entry.get("total_esperado", 0), 0),
        "total_coletado": to_int(entry.get("total_coletado", len(items)), len(items)),
        "links_signature": _normalize_spaces(entry.get("links_signature", "")),
        "links_count": to_int(entry.get("links_count", len(items)), len(items)),
        "itens": items,
        "ultima_verificacao_integridade": str(entry.get("ultima_verificacao_integridade", "") or ""),
        "ultima_atualizacao": str(entry.get("ultima_atualizacao", "") or ""),
    }


def _normalize_categories_cache_payload(data: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(data or {})
    categories_raw = payload.get("categories", {})
    if not isinstance(categories_raw, Mapping):
        categories_raw = {}

    normalized_categories: dict[str, dict[str, Any]] = {}
    for key, value in categories_raw.items():
        normalized_key = ensure_trailing_slash(key)
        if not normalized_key:
            normalized_key = ensure_trailing_slash(dict(value or {}).get("categoria_url", ""))
        if not normalized_key:
            continue
        normalized_categories[normalized_key] = _normalize_category_cache_entry(value, fallback_url=normalized_key)

    return {
        "categories": normalized_categories,
        "available_categories": normalize_available_categories_list(payload.get("available_categories", [])),
    }


def _normalize_queue_cache_payload(data: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(data or {})
    categories_raw = payload.get("categories", {})
    if not isinstance(categories_raw, Mapping):
        categories_raw = {}

    normalized_categories: dict[str, dict[str, Any]] = {}
    for key, value in categories_raw.items():
        normalized_key = ensure_trailing_slash(key)
        if not normalized_key:
            normalized_key = ensure_trailing_slash(dict(value or {}).get("categoria_url", ""))
        if not normalized_key:
            continue
        normalized_categories[normalized_key] = _normalize_queue_cache_entry(value, fallback_url=normalized_key)

    return {"categories": normalized_categories}


def load_categories_cache(context: Any = None, **kwargs: Any) -> dict[str, Any]:
    path = get_categories_cache_json_path(context, **kwargs)
    raw = read_json(path, {"categories": {}})
    if not isinstance(raw, dict):
        raw = {"categories": {}}
    return _normalize_categories_cache_payload(raw)


def load_queue_cache(context: Any = None, **kwargs: Any) -> dict[str, Any]:
    path = get_queue_cache_json_path(context, **kwargs)
    raw = read_json(path, {"categories": {}})
    if not isinstance(raw, dict):
        raw = {"categories": {}}
    return _normalize_queue_cache_payload(raw)


def save_categories_cache(cache: Mapping[str, Any] | None, context: Any = None, **kwargs: Any) -> dict[str, Any]:
    normalized = _normalize_categories_cache_payload(cache)
    try:
        write_json_atomic(get_categories_cache_json_path(context, **kwargs), normalized)
    except Exception as error:
        raise CachePersistenceError("Falha ao salvar categories_cache.json.") from error
    return normalized


def save_queue_cache(cache: Mapping[str, Any] | None, context: Any = None, **kwargs: Any) -> dict[str, Any]:
    normalized = _normalize_queue_cache_payload(cache)
    try:
        write_json_atomic(get_queue_cache_json_path(context, **kwargs), normalized)
    except Exception as error:
        raise CachePersistenceError("Falha ao salvar queue_cache.json.") from error
    return normalized


def normalize_available_categories_list(categories: Iterable[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()

    for category in categories or []:
        raw = dict(category)
        raw_url = _normalize_spaces(raw.get("url") or raw.get("categoria_url", ""))
        url = ensure_trailing_slash(raw_url) if raw_url else ""
        name = _normalize_spaces(raw.get("nome") or raw.get("categoria_nome", ""))

        if not url or url in seen:
            continue

        total = to_int(raw.get("total", raw.get("total_esperado", 0)), 0)
        seen.add(url)
        result.append({"nome": name or url, "url": url, "total": total})

    return sorted(result, key=lambda item: _normalize_spaces(item.get("nome", "")).lower())


def save_available_categories(categories: Iterable[Mapping[str, Any]] | None, context: Any = None, **kwargs: Any) -> list[dict[str, Any]]:
    cache = load_categories_cache(context, **kwargs)
    cache["available_categories"] = normalize_available_categories_list(categories)
    saved = save_categories_cache(cache, context, **kwargs)
    return list(saved.get("available_categories", []) or [])


def load_available_categories(context: Any = None, **kwargs: Any) -> list[dict[str, Any]]:
    cache = load_categories_cache(context, **kwargs)
    saved = normalize_available_categories_list(cache.get("available_categories", []))
    if saved:
        return saved

    derived_from_cache = normalize_available_categories_list([
        {
            "nome": item.get("categoria_nome", ""),
            "url": item.get("categoria_url", url),
            "total": item.get("total_esperado", item.get("total_coletado", 0)),
        }
        for url, item in (cache.get("categories", {}) or {}).items()
    ])
    if derived_from_cache:
        return derived_from_cache

    catalog_items = load_catalog_items(context, **kwargs)
    grouped: dict[str, dict[str, Any]] = {}
    for item in catalog_items:
        raw_url = _normalize_spaces(item.get("categoria_url", ""))
        url = ensure_trailing_slash(raw_url) if raw_url else ""
        name = _normalize_spaces(item.get("categoria_nome", ""))
        if not url:
            continue
        if url not in grouped:
            grouped[url] = {"nome": name or url, "url": url, "total": 0}
        grouped[url]["total"] += 1

    return normalize_available_categories_list(grouped.values())


def calculate_links_signature(category_items: Iterable[Mapping[str, Any]] | None) -> tuple[str, int]:
    links = sorted({
        _normalize_spaces(dict(item).get("link_produto", ""))
        for item in (category_items or [])
        if _normalize_spaces(dict(item).get("link_produto", ""))
    })
    base = "\n".join(links)
    signature = hashlib.sha1(base.encode("utf-8")).hexdigest()
    return signature, len(links)


def save_individual_category_cache(
    categories_cache: Mapping[str, Any] | None,
    queue_cache: Mapping[str, Any] | None,
    category: Mapping[str, Any],
    category_items: Iterable[Mapping[str, Any]] | None,
    source: str,
    context: Any = None,
    diagnostics: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    normalized_categories_cache = _normalize_categories_cache_payload(categories_cache)
    normalized_queue_cache = _normalize_queue_cache_payload(queue_cache)

    category_dict = dict(category or {})
    key = ensure_trailing_slash(category_dict.get("categoria_url", ""))
    if not key:
        raise CachePersistenceError("A categoria precisa ter 'categoria_url'.")

    previous_meta = dict(normalized_categories_cache.get("categories", {}).get(key, {}) or {})
    timestamp = now_iso()
    cleaned_items = clean_queue_items(category_items)
    links_signature, links_count = calculate_links_signature(cleaned_items)

    diagnostics_dict = dict(diagnostics or {})
    total_coletado = len(cleaned_items)
    total_esperado = to_int(category_dict.get("total_esperado", 0), 0)
    coletados_brutos = max(total_coletado, to_int(diagnostics_dict.get("coletados_brutos", total_coletado), total_coletado))
    coletados_unicos = max(total_coletado, to_int(diagnostics_dict.get("coletados_unicos", total_coletado), total_coletado))
    duplicados_internos = max(0, to_int(diagnostics_dict.get("duplicados_internos", coletados_brutos - coletados_unicos), coletados_brutos - coletados_unicos))
    paginas_visitadas = max(0, to_int(diagnostics_dict.get("paginas_visitadas", 0), 0))
    paginas_repetidas = max(0, to_int(diagnostics_dict.get("paginas_repetidas", 0), 0))
    paginas_sem_ganho = max(0, to_int(diagnostics_dict.get("paginas_sem_ganho", 0), 0))
    faltantes_estimados = max(0, to_int(diagnostics_dict.get("faltantes_estimados", max(0, total_esperado - coletados_unicos)), max(0, total_esperado - coletados_unicos)))
    resgatados_do_cache = max(0, to_int(diagnostics_dict.get("resgatados_do_cache", 0), 0))
    itens_novos_fila = max(0, to_int(diagnostics_dict.get("itens_novos_fila", 0), 0))
    itens_existentes_fila = max(0, to_int(diagnostics_dict.get("itens_existentes_fila", 0), 0))

    status_coleta = _normalize_spaces(diagnostics_dict.get("status_coleta", ""))
    if not status_coleta:
        status_coleta = "ok" if faltantes_estimados <= 0 else "incompleta"

    diagnostico_resumido = (
        f"brutos={coletados_brutos} | "
        f"unicos={coletados_unicos} | "
        f"duplicados={duplicados_internos} | "
        f"paginas_repetidas={paginas_repetidas} | "
        f"faltantes={faltantes_estimados} | "
        f"resgatados_cache={resgatados_do_cache} | "
        f"status={status_coleta}"
    )

    execucoes_total = max(0, to_int(previous_meta.get("execucoes_total", 0), 0)) + 1
    previous_execucoes_ok = max(0, to_int(previous_meta.get("execucoes_ok", 0), 0))
    previous_execucoes_incompletas = max(0, to_int(previous_meta.get("execucoes_incompletas", 0), 0))
    previous_consecutivas_incompletas = max(0, to_int(previous_meta.get("consecutivas_incompletas", 0), 0))

    is_ok = status_coleta in {"ok", "ok_resgatado"} and faltantes_estimados <= 0

    execucoes_ok = previous_execucoes_ok + (1 if is_ok else 0)
    execucoes_incompletas = previous_execucoes_incompletas + (0 if is_ok else 1)
    consecutivas_incompletas = 0 if is_ok else previous_consecutivas_incompletas + 1

    confiabilidade_base = int(round((execucoes_ok / execucoes_total) * 100)) if execucoes_total > 0 else 100
    confiabilidade_score = max(
        0,
        min(
            100,
            confiabilidade_base
            - min(20, faltantes_estimados * 3)
            - min(15, paginas_repetidas * 5)
            - min(15, consecutivas_incompletas * 5),
        ),
    )

    normalized_categories_cache["categories"][key] = {
        "categoria_nome": _normalize_spaces(category_dict.get("categoria_nome", "")),
        "categoria_url": key,
        "total_esperado": total_esperado,
        "total_coletado": total_coletado,
        "catalogada": True,
        "origem": _normalize_spaces(source),
        "links_signature": links_signature,
        "links_count": links_count,
        "coletados_brutos": coletados_brutos,
        "coletados_unicos": coletados_unicos,
        "duplicados_internos": duplicados_internos,
        "paginas_visitadas": paginas_visitadas,
        "paginas_repetidas": paginas_repetidas,
        "paginas_sem_ganho": paginas_sem_ganho,
        "faltantes_estimados": faltantes_estimados,
        "resgatados_do_cache": resgatados_do_cache,
        "itens_novos_fila": itens_novos_fila,
        "itens_existentes_fila": itens_existentes_fila,
        "status_coleta": status_coleta,
        "diagnostico_resumido": diagnostico_resumido,
        "confiabilidade_score": confiabilidade_score,
        "execucoes_total": execucoes_total,
        "execucoes_ok": execucoes_ok,
        "execucoes_incompletas": execucoes_incompletas,
        "consecutivas_incompletas": consecutivas_incompletas,
        "ultima_verificacao_integridade": timestamp,
        "ultima_atualizacao": timestamp,
    }
    normalized_queue_cache["categories"][key] = {
        "categoria_nome": _normalize_spaces(category_dict.get("categoria_nome", "")),
        "categoria_url": key,
        "total_esperado": total_esperado,
        "total_coletado": total_coletado,
        "links_signature": links_signature,
        "links_count": links_count,
        "coletados_brutos": coletados_brutos,
        "coletados_unicos": coletados_unicos,
        "duplicados_internos": duplicados_internos,
        "paginas_visitadas": paginas_visitadas,
        "paginas_repetidas": paginas_repetidas,
        "paginas_sem_ganho": paginas_sem_ganho,
        "faltantes_estimados": faltantes_estimados,
        "resgatados_do_cache": resgatados_do_cache,
        "itens_novos_fila": itens_novos_fila,
        "itens_existentes_fila": itens_existentes_fila,
        "status_coleta": status_coleta,
        "diagnostico_resumido": diagnostico_resumido,
        "itens": cleaned_items,
        "ultima_verificacao_integridade": timestamp,
        "ultima_atualizacao": timestamp,
    }

    saved_categories_cache = save_categories_cache(normalized_categories_cache, context, **kwargs)
    saved_queue_cache = save_queue_cache(normalized_queue_cache, context, **kwargs)

    return {
        "categories_cache": saved_categories_cache,
        "queue_cache": saved_queue_cache,
        "category_key": key,
        "links_signature": links_signature,
        "links_count": links_count,
        "total_items": len(cleaned_items),
        "status_coleta": status_coleta,
        "confiabilidade_score": confiabilidade_score,
        "faltantes_estimados": faltantes_estimados,
    }


def is_category_cache_valid_normal(
    current_category: Mapping[str, Any],
    categories_cache: Mapping[str, Any] | None,
    queue_cache: Mapping[str, Any] | None,
) -> tuple[bool, str]:
    category_dict = dict(current_category or {})
    key = ensure_trailing_slash(category_dict.get("categoria_url", ""))
    categories_payload = _normalize_categories_cache_payload(categories_cache)
    queue_payload = _normalize_queue_cache_payload(queue_cache)

    meta = categories_payload.get("categories", {}).get(key)
    queue_entry = queue_payload.get("categories", {}).get(key)

    if not meta or not queue_entry:
        return False, "sem cache"

    current_total = to_int(category_dict.get("total_esperado", 0), 0)
    meta_total_expected = to_int(meta.get("total_esperado", -1), -1)
    meta_total_collected = to_int(meta.get("total_coletado", -1), -1)
    items = queue_entry.get("itens", []) or []
    status_coleta = _normalize_spaces(meta.get("status_coleta", ""))
    consecutivas_incompletas = to_int(meta.get("consecutivas_incompletas", 0), 0)
    faltantes_estimados = to_int(meta.get("faltantes_estimados", 0), 0)

    if not meta.get("catalogada"):
        return False, "cache incompleto"
    if current_total != meta_total_expected:
        return False, "quantidade do catálogo mudou"
    if current_total != meta_total_collected:
        return False, "quantidade coletada não bate"
    if current_total != len(items):
        return False, "fila salva não bate"
    if status_coleta and status_coleta not in {"ok", "ok_resgatado", "cache"}:
        return False, "cache marcado como instável"
    if consecutivas_incompletas > 0:
        return False, "histórico instável"
    if faltantes_estimados > 0:
        return False, "cache com faltantes estimados"

    return True, "cache válido"


def compare_complete_integrity(
    current_category: Mapping[str, Any],
    categories_cache: Mapping[str, Any] | None,
    queue_cache: Mapping[str, Any] | None,
    live_items: Iterable[Mapping[str, Any]] | None,
) -> tuple[bool, str, str, int]:
    category_dict = dict(current_category or {})
    key = ensure_trailing_slash(category_dict.get("categoria_url", ""))
    categories_payload = _normalize_categories_cache_payload(categories_cache)
    queue_payload = _normalize_queue_cache_payload(queue_cache)

    meta = categories_payload.get("categories", {}).get(key)
    queue_entry = queue_payload.get("categories", {}).get(key)
    live_signature, live_links_count = calculate_links_signature(live_items)

    cache_signature = ""
    cache_links_count = -1
    cache_total_expected = -1
    cache_total_collected = -1

    if meta:
        cache_signature = _normalize_spaces(meta.get("links_signature", ""))
        cache_links_count = to_int(meta.get("links_count", -1), -1)
        cache_total_expected = to_int(meta.get("total_esperado", -1), -1)
        cache_total_collected = to_int(meta.get("total_coletado", -1), -1)
    elif queue_entry:
        cache_signature = _normalize_spaces(queue_entry.get("links_signature", ""))
        cache_links_count = to_int(queue_entry.get("links_count", -1), -1)
        cache_total_expected = to_int(queue_entry.get("total_esperado", -1), -1)
        cache_total_collected = to_int(queue_entry.get("total_coletado", -1), -1)

    current_total = to_int(category_dict.get("total_esperado", 0), 0)

    if not meta or not queue_entry:
        return False, "sem cache", live_signature, live_links_count
    if not cache_signature:
        return False, "sem assinatura antiga", live_signature, live_links_count
    if current_total != cache_total_expected:
        return False, "quantidade do catálogo mudou", live_signature, live_links_count
    if current_total != cache_total_collected:
        return False, "quantidade coletada antiga não bate", live_signature, live_links_count
    if live_links_count != cache_links_count:
        return False, "links_count mudou", live_signature, live_links_count
    if live_signature != cache_signature:
        return False, "links_signature mudou", live_signature, live_links_count

    return True, "integridade confirmada", live_signature, live_links_count


def _split_scope_terms(raw: Any) -> list[str]:
    return [
        _normalize_spaces(value).lower()
        for value in re.split(r"[\n,;]+", str(raw or ""))
        if _normalize_spaces(value)
    ]


def filter_categories_by_scope(
    categories: list[Mapping[str, Any]],
    run_options: Mapping[str, Any] | None,
) -> list[Mapping[str, Any]]:
    options = dict(run_options or {})
    scope_mode = str(options.get("scope_mode", "all") or "all").strip().lower()

    if scope_mode == "all":
        return list(categories)

    if scope_mode == "range":
        start = max(1, to_int(options.get("scope_start", 1), 1))
        end = to_int(options.get("scope_end", 0), 0)
        if end <= 0:
            end = len(categories)
        if end < start:
            end = start
        return list(categories)[start - 1:end]

    if scope_mode == "match":
        terms = _split_scope_terms(options.get("scope_match_text", ""))
        if not terms:
            return list(categories)

        filtered: list[Mapping[str, Any]] = []
        for category in categories:
            category_name = _normalize_spaces(dict(category).get("categoria_nome", dict(category).get("nome", ""))).lower()
            category_url = ensure_trailing_slash(dict(category).get("categoria_url", dict(category).get("url", ""))).lower()
            if any(term in category_name or term in category_url for term in terms):
                filtered.append(category)
        return filtered

    if scope_mode == "selected":
        selected = {
            ensure_trailing_slash(_normalize_spaces(value))
            for value in (options.get("selected_categories", []) or [])
            if _normalize_spaces(value)
        }
        if not selected:
            return []
        return [
            category
            for category in categories
            if ensure_trailing_slash(dict(category).get("categoria_url", dict(category).get("url", ""))) in selected
        ]

    return list(categories)


def filter_existing_products_by_scope(
    products_dict: Mapping[str, Mapping[str, Any]] | Iterable[Mapping[str, Any]],
    run_options: Mapping[str, Any] | None,
    context: Any = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    items = list(products_dict.values()) if isinstance(products_dict, Mapping) else list(products_dict or [])
    options = dict(run_options or {})
    scope_mode = str(options.get("scope_mode", "all") or "all").strip().lower()

    if scope_mode == "all":
        return items

    if scope_mode == "range":
        categories = load_available_categories(context, **kwargs)
        category_index_map = {ensure_trailing_slash(category.get("url", "")): index + 1 for index, category in enumerate(categories)}
        start = max(1, to_int(options.get("scope_start", 1), 1))
        end = to_int(options.get("scope_end", 0), 0)
        if end <= 0:
            end = len(category_index_map) or 999999
        if end < start:
            end = start
        return [
            item
            for item in items
            if start <= category_index_map.get(ensure_trailing_slash(dict(item).get("categoria_url", "")), 999999) <= end
        ]

    if scope_mode == "match":
        terms = _split_scope_terms(options.get("scope_match_text", ""))
        if not terms:
            return items
        return [
            item
            for item in items
            if any(
                term in _normalize_spaces(dict(item).get("categoria_nome", "")).lower()
                or term in _normalize_spaces(dict(item).get("categoria_url", "")).lower()
                for term in terms
            )
        ]

    if scope_mode == "selected":
        selected = {
            ensure_trailing_slash(_normalize_spaces(value))
            for value in (options.get("selected_categories", []) or [])
            if _normalize_spaces(value)
        }
        if not selected:
            return []
        return [
            item
            for item in items
            if ensure_trailing_slash(dict(item).get("categoria_url", "")) in selected
        ]

    return items


def clear_cache_files(
    context: Any = None,
    *,
    remove_config: bool = False,
    **kwargs: Any,
) -> dict[str, bool]:
    paths = build_context_paths(context, **kwargs, ensure=True)
    removed = {
        "categories_cache_json_path": remove_file(paths.categories_cache_json_path, missing_ok=True),
        "queue_cache_json_path": remove_file(paths.queue_cache_json_path, missing_ok=True),
        "config_json_path": False,
    }
    if remove_config:
        removed["config_json_path"] = remove_file(paths.config_json_path, missing_ok=True)
    return removed


def clear_context_records(
    context: Any = None,
    *,
    remove_catalog: bool = True,
    remove_progress: bool = True,
    remove_cache: bool = True,
    remove_status: bool = True,
    remove_logs: bool = True,
    remove_config: bool = False,
    **kwargs: Any,
) -> dict[str, bool]:
    removed: dict[str, bool] = {}

    if remove_catalog:
        removed.update(clear_catalog_outputs(context, remove_progress=remove_progress, **kwargs))
    elif remove_progress:
        removed["progress_json_path"] = remove_file(get_progress_json_path(context, **kwargs), missing_ok=True)

    if remove_cache:
        removed.update(clear_cache_files(context, remove_config=remove_config, **kwargs))
    elif remove_config:
        removed["config_json_path"] = remove_file(get_config_json_path(context, **kwargs), missing_ok=True)

    if remove_status or remove_logs:
        removed.update(
            clear_status_files(
                context,
                remove_status=remove_status,
                remove_last_logs=remove_logs,
                remove_runtime_log=remove_logs,
                **kwargs,
            )
        )

    return removed


# ============================================================
# ALIASES EM PT-BR
# ============================================================

carregar_json = read_json
carregar_texto = read_text
escrever_json_atomico = write_json_atomic
escrever_csv_atomico = write_csv_atomic
escrever_texto_atomico = write_text_atomic
apagar_arquivo = remove_file
garantir_pasta_pai = ensure_parent_dir
garantir_pasta = ensure_dir

agora_iso = now_iso
formatar_duracao_segundos = format_duration_seconds
calcular_timer_segundos = calculate_duration_seconds
normalizar_espacos = _normalize_spaces
ordenar_produtos = sort_catalog_items
carregar_catalogo = load_catalog_items
carregar_produtos_existentes = load_existing_products_dict
carregar_progresso_catalogo = load_progress_data
salvar_progresso_catalogo = save_progress_data
salvar_estado = save_catalog_state
limpar_item_de_fila = clean_queue_item
limpar_lista_de_fila = clean_queue_items
obter_resume_info = get_resume_info
normalizar_produto_para_comparacao = normalize_product_for_comparison
mesclar_produto_existente = merge_existing_product
descrever_mudancas_produto = describe_product_changes

obter_estado_inicial = build_default_runtime_state
normalizar_dados_estado = normalize_state_data
montar_payload_estado = build_state_payload
montar_status_txt = build_status_text
carregar_status_txt = load_status_text
salvar_status_txt = save_status_text
carregar_log_completo_txt = load_full_logs_text
salvar_log_completo_txt = save_full_logs_text
carregar_log_runtime_txt = load_runtime_log_text
formatar_linha_log = format_log_line
acrescentar_linha_log_runtime = append_runtime_log_line
apagar_arquivos_status = clear_status_files

obter_config_padrao = build_default_config
carregar_config_slot = load_context_config
salvar_config_slot = save_context_config
carregar_cache_categorias = load_categories_cache
carregar_cache_fila = load_queue_cache
salvar_cache_categorias = save_categories_cache
salvar_cache_fila = save_queue_cache
normalizar_lista_categorias_disponiveis = normalize_available_categories_list
salvar_categorias_disponiveis_salvas = save_available_categories
carregar_categorias_disponiveis_salvas = load_available_categories
salvar_cache_categoria_individual = save_individual_category_cache
categoria_cache_valida_normal = is_category_cache_valid_normal
comparar_integridade_completa = compare_complete_integrity
filtrar_categorias_por_escopo = filter_categories_by_scope
filtrar_produtos_existentes_por_escopo = filter_existing_products_by_scope
apagar_arquivos_cache = clear_cache_files
apagar_registros_do_contexto = clear_context_records


__all__ = [
    "PathLike",
    "CATALOG_FIELDNAMES",
    "StorageIdentity",
    "ContextPaths",
    # file io
    "coerce_path",
    "ensure_parent_dir",
    "ensure_dir",
    "path_exists",
    "remove_file",
    "read_text",
    "write_text_atomic",
    "append_text",
    "read_json",
    "write_json_atomic",
    "read_csv_rows",
    "write_csv_atomic",
    "touch_file",
    # paths / slots
    "resolve_storage_identity",
    "get_project_root",
    "get_data_dir",
    "get_logs_dir",
    "get_slots_root_dir",
    "get_slots_meta_path",
    "ensure_slots_root_dir",
    "get_slot_dir",
    "ensure_slot_dir",
    "load_slots_meta",
    "save_slots_meta",
    "list_slot_names",
    "has_slot",
    "get_default_slot_name",
    "get_active_slot_name",
    "get_slot",
    "list_slots",
    "build_slot_public_dict",
    "build_slots_public_list",
    "set_active_slot",
    "set_default_slot",
    "create_slot",
    "delete_slot",
    "get_context_dir",
    "get_context_logs_dir",
    "build_context_paths",
    "get_output_csv_path",
    "get_output_json_path",
    "get_progress_json_path",
    "get_categories_cache_json_path",
    "get_queue_cache_json_path",
    "get_config_json_path",
    "get_status_txt_path",
    "get_last_logs_txt_path",
    "get_runtime_log_path",
    # catalog / progress
    "to_int",
    "now_iso",
    "format_duration_seconds",
    "calculate_duration_seconds",
    "ensure_trailing_slash",
    "get_continue_enabled_default",
    "get_default_item_type_key",
    "normalize_catalog_item",
    "normalize_catalog_items",
    "sort_catalog_items",
    "build_catalog_index",
    "load_catalog_items",
    "load_existing_products_dict",
    "save_catalog_items",
    "load_progress_data",
    "save_progress_data",
    "build_progress_payload",
    "save_catalog_state",
    "clear_catalog_outputs",
    "rebuild_catalog_outputs_from_json",
    "normalize_product_for_comparison",
    "merge_existing_product",
    "describe_product_changes",
    # queue / resume
    "clean_queue_item",
    "clean_queue_items",
    "get_resume_info",
    # state / status
    "build_default_runtime_state",
    "normalize_logs_list",
    "normalize_state_data",
    "build_state_payload",
    "build_status_text",
    "load_status_text",
    "save_status_text",
    "load_full_logs_text",
    "save_full_logs_text",
    "load_runtime_log_text",
    "format_log_line",
    "append_runtime_log_line",
    "clear_status_files",
    # config / cache
    "build_default_config",
    "normalize_config_dict",
    "load_context_config",
    "save_context_config",
    "load_categories_cache",
    "load_queue_cache",
    "save_categories_cache",
    "save_queue_cache",
    "normalize_available_categories_list",
    "save_available_categories",
    "load_available_categories",
    "calculate_links_signature",
    "save_individual_category_cache",
    "is_category_cache_valid_normal",
    "compare_complete_integrity",
    "filter_categories_by_scope",
    "filter_existing_products_by_scope",
    "clear_cache_files",
    "clear_context_records",
    # aliases pt-br
    "carregar_json",
    "carregar_texto",
    "escrever_json_atomico",
    "escrever_csv_atomico",
    "escrever_texto_atomico",
    "apagar_arquivo",
    "garantir_pasta_pai",
    "garantir_pasta",
    "agora_iso",
    "formatar_duracao_segundos",
    "calcular_timer_segundos",
    "normalizar_espacos",
    "ordenar_produtos",
    "carregar_catalogo",
    "carregar_produtos_existentes",
    "carregar_progresso_catalogo",
    "salvar_progresso_catalogo",
    "salvar_estado",
    "limpar_item_de_fila",
    "limpar_lista_de_fila",
    "obter_resume_info",
    "normalizar_produto_para_comparacao",
    "mesclar_produto_existente",
    "descrever_mudancas_produto",
    "obter_estado_inicial",
    "normalizar_dados_estado",
    "montar_payload_estado",
    "montar_status_txt",
    "carregar_status_txt",
    "salvar_status_txt",
    "carregar_log_completo_txt",
    "salvar_log_completo_txt",
    "carregar_log_runtime_txt",
    "formatar_linha_log",
    "acrescentar_linha_log_runtime",
    "apagar_arquivos_status",
    "obter_config_padrao",
    "carregar_config_slot",
    "salvar_config_slot",
    "carregar_cache_categorias",
    "carregar_cache_fila",
    "salvar_cache_categorias",
    "salvar_cache_fila",
    "normalizar_lista_categorias_disponiveis",
    "salvar_categorias_disponiveis_salvas",
    "carregar_categorias_disponiveis_salvas",
    "salvar_cache_categoria_individual",
    "categoria_cache_valida_normal",
    "comparar_integridade_completa",
    "filtrar_categorias_por_escopo",
    "filtrar_produtos_existentes_por_escopo",
    "apagar_arquivos_cache",
    "apagar_registros_do_contexto",
]
