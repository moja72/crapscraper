from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from app.collection.legacy_core import settings


# ============================================================
# HELPERS INTERNOS
# ============================================================


def _normalize_spaces(value: Any) -> str:
    if value in (None, ""):
        return ""
    return " ".join(str(value).split()).strip()


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value

    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "sim"}:
        return True
    if text in {"0", "false", "no", "n", "off", "nao", "não"}:
        return False
    return default


def _now_iso() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def _ensure_trailing_slash(url: Any) -> str:
    text = _normalize_spaces(url)
    if not text:
        return ""
    return text if text.endswith("/") else text + "/"


def _context_prefix(site_key: str, item_type_key: str, account_key: str) -> str:
    return f"{site_key}_{item_type_key}_{account_key}"


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


def _normalize_url_list(values: Any) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple, set)):
        return ()

    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        url = _normalize_spaces(value)
        if not url or url in seen:
            continue
        seen.add(url)
        result.append(url)

    return tuple(result)


# ============================================================
# SLOT
# ============================================================


@dataclass(frozen=True, slots=True)
class SlotInfo:
    name: str
    path: Path
    is_default: bool = False
    is_active: bool = False

    @classmethod
    def build(
        cls,
        slot_name: str | None = None,
        *,
        is_default: bool = False,
        is_active: bool = False,
    ) -> "SlotInfo":
        normalized = settings.normalize_slot_name(slot_name)
        return cls(
            name=normalized,
            path=settings.SLOTS_DIR / normalized,
            is_default=bool(is_default),
            is_active=bool(is_active),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": str(self.path),
            "is_default": self.is_default,
            "is_active": self.is_active,
        }


# ============================================================
# CONTEXTO
# ============================================================


@dataclass(frozen=True, slots=True)
class ScraperContext:
    site_key: str
    item_type_key: str
    account_key: str
    slot_name: str

    @property
    def context_prefix(self) -> str:
        return _context_prefix(
            self.site_key,
            self.item_type_key,
            self.account_key,
        )

    @property
    def slot_path(self) -> Path:
        return settings.SLOTS_DIR / self.slot_name

    def to_dict(self) -> dict[str, str]:
        return {
            "site_key": self.site_key,
            "item_type_key": self.item_type_key,
            "account_key": self.account_key,
            "slot_name": self.slot_name,
        }

    def to_public_dict(self) -> dict[str, Any]:
        site = settings.get_site(self.site_key)
        item_type = settings.get_item_type(self.item_type_key)
        account = settings.get_account(self.account_key)

        return {
            **self.to_dict(),
            "context_prefix": self.context_prefix,
            "site": {
                "key": site.key,
                "label": site.label,
                "base_url": site.base_url,
                "supported_item_types": list(site.supported_item_types),
            },
            "item_type": {
                "key": item_type.key,
                "label_singular": item_type.label_singular,
                "label_plural": item_type.label_plural,
                "slug_plural": item_type.slug_plural,
                "default_catalog_path": item_type.default_catalog_path,
                "default_item_kind_value": item_type.default_item_kind_value,
                "supports_categories": item_type.supports_categories,
                "supports_versioning": item_type.supports_versioning,
                "supports_observation": item_type.supports_observation,
            },
            "account": {
                "key": account.key,
                "label": account.label,
                "supported_item_types": list(account.supported_item_types),
                "supported_sites": list(account.site_credentials.keys()),
                "notes": account.notes,
            },
            "slot": SlotInfo.build(self.slot_name).to_dict(),
        }

    def with_updates(self, **changes: Any) -> "ScraperContext":
        return build_context(self, **changes)


def normalize_context_dict(
    value: ScraperContext | Mapping[str, Any] | None = None,
    *,
    site_key: str | None = None,
    item_type_key: str | None = None,
    account_key: str | None = None,
    slot_name: str | None = None,
) -> dict[str, str]:
    base = settings.build_default_context()

    if isinstance(value, ScraperContext):
        base.update(value.to_dict())
    elif isinstance(value, Mapping):
        base.update(dict(value))
    elif value is not None:
        raise TypeError(
            "O contexto deve ser None, Mapping ou ScraperContext."
        )

    if site_key is not None:
        base["site_key"] = site_key
    if item_type_key is not None:
        base["item_type_key"] = item_type_key
    if account_key is not None:
        base["account_key"] = account_key
    if slot_name is not None:
        base["slot_name"] = slot_name

    raw_site_key = str(base.get("site_key", "") or "").strip()
    raw_item_type_key = str(base.get("item_type_key", "") or "").strip()
    raw_account_key = str(base.get("account_key", "") or "").strip()

    if raw_site_key and not settings.has_site(raw_site_key):
        raise ValueError(f"Site inválido: {raw_site_key!r}")

    if raw_item_type_key and not settings.has_item_type(raw_item_type_key):
        raise ValueError(f"Tipo inválido: {raw_item_type_key!r}")

    if raw_account_key and not settings.has_account(raw_account_key):
        raise ValueError(f"Conta inválida: {raw_account_key!r}")

    normalized_site_key = settings.normalize_site_key(raw_site_key)
    normalized_item_type_key = settings.ensure_supported_item_type(
        normalized_site_key,
        raw_item_type_key or settings.DEFAULT_ITEM_TYPE_KEY,
    )
    normalized_account_key = settings.ensure_account_supported(
        normalized_site_key,
        normalized_item_type_key,
        raw_account_key or settings.DEFAULT_ACCOUNT_KEY,
    )
    normalized_slot_name = settings.normalize_slot_name(base.get("slot_name"))

    return {
        "site_key": normalized_site_key,
        "item_type_key": normalized_item_type_key,
        "account_key": normalized_account_key,
        "slot_name": normalized_slot_name,
    }


def build_context(
    value: ScraperContext | Mapping[str, Any] | None = None,
    *,
    site_key: str | None = None,
    item_type_key: str | None = None,
    account_key: str | None = None,
    slot_name: str | None = None,
) -> ScraperContext:
    normalized = normalize_context_dict(
        value,
        site_key=site_key,
        item_type_key=item_type_key,
        account_key=account_key,
        slot_name=slot_name,
    )
    return ScraperContext(**normalized)


def get_default_context() -> ScraperContext:
    return build_context()


def is_context_supported(
    value: ScraperContext | Mapping[str, Any] | None = None,
    *,
    site_key: str | None = None,
    item_type_key: str | None = None,
    account_key: str | None = None,
    slot_name: str | None = None,
) -> bool:
    try:
        build_context(
            value,
            site_key=site_key,
            item_type_key=item_type_key,
            account_key=account_key,
            slot_name=slot_name,
        )
        return True
    except (TypeError, ValueError):
        return False


def build_context_public_dict(
    value: ScraperContext | Mapping[str, Any] | None = None,
    *,
    site_key: str | None = None,
    item_type_key: str | None = None,
    account_key: str | None = None,
    slot_name: str | None = None,
) -> dict[str, Any]:
    return build_context(
        value,
        site_key=site_key,
        item_type_key=item_type_key,
        account_key=account_key,
        slot_name=slot_name,
    ).to_public_dict()


def resolve_context_credentials(
    value: ScraperContext | Mapping[str, Any] | None = None,
    *,
    site_key: str | None = None,
    item_type_key: str | None = None,
    account_key: str | None = None,
    slot_name: str | None = None,
) -> dict[str, str | None]:
    context = build_context(
        value,
        site_key=site_key,
        item_type_key=item_type_key,
        account_key=account_key,
        slot_name=slot_name,
    )
    return settings.resolve_account_credentials(
        account_key=context.account_key,
        site_key=context.site_key,
    )


def is_context_configured(
    value: ScraperContext | Mapping[str, Any] | None = None,
    *,
    site_key: str | None = None,
    item_type_key: str | None = None,
    account_key: str | None = None,
    slot_name: str | None = None,
) -> bool:
    context = build_context(
        value,
        site_key=site_key,
        item_type_key=item_type_key,
        account_key=account_key,
        slot_name=slot_name,
    )
    return settings.is_account_configured(
        account_key=context.account_key,
        site_key=context.site_key,
    )


def build_runtime_context_dict(
    value: ScraperContext | Mapping[str, Any] | None = None,
    *,
    site_key: str | None = None,
    item_type_key: str | None = None,
    account_key: str | None = None,
    slot_name: str | None = None,
) -> dict[str, Any]:
    context = build_context(
        value,
        site_key=site_key,
        item_type_key=item_type_key,
        account_key=account_key,
        slot_name=slot_name,
    )

    site = settings.get_site(context.site_key)
    item_type = settings.get_item_type(context.item_type_key)
    account = settings.get_account(context.account_key)
    credentials = settings.resolve_account_credentials(
        account_key=context.account_key,
        site_key=context.site_key,
    )

    return {
        "site_key": context.site_key,
        "site_label": site.label,
        "item_type_key": context.item_type_key,
        "item_type_label_singular": item_type.label_singular,
        "item_type_label_plural": item_type.label_plural,
        "account_key": context.account_key,
        "account_label": account.label,
        "slot_name": context.slot_name,
        "slot_path": str(context.slot_path),
        "context_prefix": context.context_prefix,
        "base_url": site.base_url,
        "catalog_url": settings.build_catalog_url(
            site_key=context.site_key,
            item_type_key=context.item_type_key,
        ),
        "login_urls": settings.build_login_urls(context.site_key),
        "grouped_category_hints": list(
            settings.get_grouped_category_hints(
                site_key=context.site_key,
                item_type_key=context.item_type_key,
            )
        ),
        "login_email": credentials["login_email"],
        "login_password": credentials["login_password"],
        "env_email_var": credentials["env_email_var"],
        "env_password_var": credentials["env_password_var"],
        "is_configured": bool(
            credentials["login_email"] and credentials["login_password"]
        ),
    }


# ============================================================
# RUN OPTIONS
# ============================================================


@dataclass(frozen=True, slots=True)
class RunOptions:
    verify_mode: str = settings.DEFAULT_VERIFY_MODE
    scope_mode: str = settings.DEFAULT_SCOPE_MODE
    scope_start: int = settings.DEFAULT_SCOPE_START
    scope_end: int = settings.DEFAULT_SCOPE_END
    scope_match_text: str = settings.DEFAULT_SCOPE_MATCH_TEXT
    save_every_items: int = settings.DEFAULT_SAVE_EVERY_ITEMS
    save_every_minutes: int = settings.DEFAULT_SAVE_EVERY_MINUTES
    selected_categories: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "verify_mode": self.verify_mode,
            "scope_mode": self.scope_mode,
            "scope_start": self.scope_start,
            "scope_end": self.scope_end,
            "scope_match_text": self.scope_match_text,
            "save_every_items": self.save_every_items,
            "save_every_minutes": self.save_every_minutes,
            "selected_categories": list(self.selected_categories),
        }

    def with_updates(self, **changes: Any) -> "RunOptions":
        payload = self.to_dict()
        payload.update(changes)
        return build_run_options(payload)


def build_run_options(
    value: RunOptions | Mapping[str, Any] | None = None,
    *,
    verify_mode: str | None = None,
    scope_mode: str | None = None,
    scope_start: int | None = None,
    scope_end: int | None = None,
    scope_match_text: str | None = None,
    save_every_items: int | None = None,
    save_every_minutes: int | None = None,
    selected_categories: Any = None,
) -> RunOptions:
    base = settings.build_default_run_options()

    if isinstance(value, RunOptions):
        base.update(value.to_dict())
    elif isinstance(value, Mapping):
        base.update(dict(value))
    elif value is not None:
        raise TypeError("RunOptions deve ser None, Mapping ou RunOptions.")

    if verify_mode is not None:
        base["verify_mode"] = verify_mode
    if scope_mode is not None:
        base["scope_mode"] = scope_mode
    if scope_start is not None:
        base["scope_start"] = scope_start
    if scope_end is not None:
        base["scope_end"] = scope_end
    if scope_match_text is not None:
        base["scope_match_text"] = scope_match_text
    if save_every_items is not None:
        base["save_every_items"] = save_every_items
    if save_every_minutes is not None:
        base["save_every_minutes"] = save_every_minutes
    if selected_categories is not None:
        base["selected_categories"] = selected_categories

    normalized_verify_mode = str(
        base.get("verify_mode", settings.DEFAULT_VERIFY_MODE) or settings.DEFAULT_VERIFY_MODE
    ).strip().lower()
    if normalized_verify_mode not in settings.VERIFY_MODES:
        normalized_verify_mode = settings.DEFAULT_VERIFY_MODE

    normalized_scope_mode = str(
        base.get("scope_mode", settings.DEFAULT_SCOPE_MODE) or settings.DEFAULT_SCOPE_MODE
    ).strip().lower()
    if normalized_scope_mode not in settings.SCOPE_MODES:
        normalized_scope_mode = settings.DEFAULT_SCOPE_MODE

    normalized_scope_start = max(1, _to_int(base.get("scope_start"), settings.DEFAULT_SCOPE_START))
    normalized_scope_end = max(0, _to_int(base.get("scope_end"), settings.DEFAULT_SCOPE_END))
    normalized_save_every_items = max(
        1,
        _to_int(base.get("save_every_items"), settings.DEFAULT_SAVE_EVERY_ITEMS),
    )
    normalized_save_every_minutes = max(
        1,
        _to_int(base.get("save_every_minutes"), settings.DEFAULT_SAVE_EVERY_MINUTES),
    )
    normalized_scope_match_text = _normalize_spaces(base.get("scope_match_text", ""))

    selected = base.get("selected_categories", ())
    normalized_selected = _normalize_url_list(selected)

    return RunOptions(
        verify_mode=normalized_verify_mode,
        scope_mode=normalized_scope_mode,
        scope_start=normalized_scope_start,
        scope_end=normalized_scope_end,
        scope_match_text=normalized_scope_match_text,
        save_every_items=normalized_save_every_items,
        save_every_minutes=normalized_save_every_minutes,
        selected_categories=normalized_selected,
    )


def get_default_run_options() -> RunOptions:
    return build_run_options()


# ============================================================
# CATEGORIA
# ============================================================


@dataclass(frozen=True, slots=True)
class Category:
    name: str
    url: str
    expected_total: int = 0
    item_type_key: str = settings.DEFAULT_ITEM_TYPE_KEY

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "url": self.url,
            "expected_total": self.expected_total,
            "item_type_key": self.item_type_key,
            "nome": self.name,
            "total": self.expected_total,
            "categoria_nome": self.name,
            "categoria_url": self.url,
            "total_esperado": self.expected_total,
            "tipo": self.item_type_key,
        }

    @classmethod
    def from_value(
        cls,
        value: "Category | Mapping[str, Any] | None",
        *,
        item_type_key: str | None = None,
    ) -> "Category":
        if isinstance(value, Category):
            if item_type_key and value.item_type_key != item_type_key:
                return replace(value, item_type_key=item_type_key)
            return value

        data = dict(value or {})
        resolved_item_type_key = settings.normalize_item_type_key(
            data.get("item_type_key")
            or data.get("tipo")
            or item_type_key
            or settings.DEFAULT_ITEM_TYPE_KEY
        )

        return cls(
            name=_normalize_spaces(
                data.get("name")
                or data.get("nome")
                or data.get("categoria_nome")
                or ""
            ),
            url=_ensure_trailing_slash(
                data.get("url")
                or data.get("categoria_url")
                or ""
            ),
            expected_total=max(
                0,
                _to_int(
                    data.get("expected_total", data.get("total", data.get("total_esperado", 0))),
                    0,
                ),
            ),
            item_type_key=resolved_item_type_key,
        )


# ============================================================
# ITEM DE CATÁLOGO
# ============================================================


@dataclass(frozen=True, slots=True)
class CatalogItem:
    item_type_key: str
    category_name: str
    category_url: str
    product_url: str
    product_name: str = ""
    product_version: str = ""
    observation: str = ""

    @property
    def key(self) -> str:
        return self.product_url

    def to_dict(self) -> dict[str, str]:
        return {
            "item_type_key": self.item_type_key,
            "category_name": self.category_name,
            "category_url": self.category_url,
            "product_url": self.product_url,
            "product_name": self.product_name,
            "product_version": self.product_version,
            "observation": self.observation,
            "tipo": self.item_type_key,
            "categoria_nome": self.category_name,
            "categoria_url": self.category_url,
            "link_produto": self.product_url,
            "nome_produto": self.product_name,
            "versao_produto": self.product_version,
            "observacao": self.observation,
        }

    @classmethod
    def from_value(
        cls,
        value: "CatalogItem | Mapping[str, Any] | None",
        *,
        default_item_type: str | None = None,
    ) -> "CatalogItem":
        if isinstance(value, CatalogItem):
            return value

        data = dict(value or {})
        resolved_item_type_key = settings.normalize_item_type_key(
            data.get("item_type_key")
            or data.get("tipo")
            or default_item_type
            or settings.DEFAULT_ITEM_TYPE_KEY
        )

        return cls(
            item_type_key=resolved_item_type_key,
            category_name=_normalize_spaces(
                data.get("category_name")
                or data.get("categoria_nome")
                or ""
            ),
            category_url=_ensure_trailing_slash(
                data.get("category_url")
                or data.get("categoria_url")
                or ""
            ),
            product_url=_normalize_spaces(
                data.get("product_url")
                or data.get("link_produto")
                or ""
            ),
            product_name=_normalize_spaces(
                data.get("product_name")
                or data.get("nome_produto")
                or ""
            ),
            product_version=_normalize_spaces(
                data.get("product_version")
                or data.get("versao_produto")
                or ""
            ),
            observation=_normalize_spaces(
                data.get("observation")
                or data.get("observacao")
                or ""
            ),
        )


# ============================================================
# CONTADORES
# ============================================================


@dataclass(frozen=True, slots=True)
class RunCounters:
    saved_count: int = 0
    pending_count: int = 0
    reused_categories: int = 0
    refetched_categories: int = 0
    queue_detected_count: int = 0
    new_links_detected: int = 0
    existing_links_detected: int = 0
    new_items_added: int = 0
    items_updated: int = 0
    items_unchanged: int = 0
    resume_queue_index: int = 0
    resume_queue_total: int = 0
    timer_seconds: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "saved_count": self.saved_count,
            "pending_count": self.pending_count,
            "reused_categories": self.reused_categories,
            "refetched_categories": self.refetched_categories,
            "queue_detected_count": self.queue_detected_count,
            "new_links_detected": self.new_links_detected,
            "existing_links_detected": self.existing_links_detected,
            "new_items_added": self.new_items_added,
            "items_updated": self.items_updated,
            "items_unchanged": self.items_unchanged,
            "resume_queue_index": self.resume_queue_index,
            "resume_queue_total": self.resume_queue_total,
            "timer_seconds": self.timer_seconds,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None = None) -> "RunCounters":
        data = dict(value or {})
        return cls(
            saved_count=max(0, _to_int(data.get("saved_count"), 0)),
            pending_count=max(0, _to_int(data.get("pending_count"), 0)),
            reused_categories=max(0, _to_int(data.get("reused_categories"), 0)),
            refetched_categories=max(0, _to_int(data.get("refetched_categories"), 0)),
            queue_detected_count=max(0, _to_int(data.get("queue_detected_count"), 0)),
            new_links_detected=max(0, _to_int(data.get("new_links_detected"), 0)),
            existing_links_detected=max(0, _to_int(data.get("existing_links_detected"), 0)),
            new_items_added=max(0, _to_int(data.get("new_items_added"), 0)),
            items_updated=max(0, _to_int(data.get("items_updated"), 0)),
            items_unchanged=max(0, _to_int(data.get("items_unchanged"), 0)),
            resume_queue_index=max(0, _to_int(data.get("resume_queue_index"), 0)),
            resume_queue_total=max(0, _to_int(data.get("resume_queue_total"), 0)),
            timer_seconds=max(0, _to_int(data.get("timer_seconds"), 0)),
        )


# ============================================================
# SESSÃO DE BROWSER
# ============================================================


@dataclass(slots=True)
class BrowserSessionData:
    browser_type: str = "chromium"
    headless: bool = settings.HEADLESS
    viewport: dict[str, int] = field(
        default_factory=lambda: dict(settings.PLAYWRIGHT_VIEWPORT)
    )
    user_agent: str = settings.PLAYWRIGHT_USER_AGENT
    launch_args: tuple[str, ...] = field(
        default_factory=lambda: tuple(settings.PLAYWRIGHT_LAUNCH_ARGS)
    )
    locale: str | None = settings.PLAYWRIGHT_LOCALE
    timezone_id: str | None = settings.PLAYWRIGHT_TIMEZONE_ID
    color_scheme: str | None = settings.PLAYWRIGHT_COLOR_SCHEME
    timeout_ms: int = settings.TIMEOUT
    default_delay_seconds: float = settings.DELAY
    started_at: str = field(default_factory=_now_iso)
    context: ScraperContext | None = None
    runtime_context: dict[str, Any] = field(default_factory=dict)
    playwright: Any = field(default=None, repr=False, compare=False)
    browser: Any = field(default=None, repr=False, compare=False)
    browser_context: Any = field(default=None, repr=False, compare=False)
    page: Any = field(default=None, repr=False, compare=False)

    @classmethod
    def build(
        cls,
        context: ScraperContext | Mapping[str, Any] | None = None,
        *,
        headless: bool | None = None,
        timeout_ms: int | None = None,
        runtime_context: Mapping[str, Any] | None = None,
    ) -> "BrowserSessionData":
        resolved_context = build_context(context) if context is not None else None
        resolved_runtime_context = (
            build_runtime_context_dict(resolved_context)
            if resolved_context is not None
            else {}
        )
        if isinstance(runtime_context, Mapping):
            resolved_runtime_context.update(dict(runtime_context))

        return cls(
            headless=settings.HEADLESS if headless is None else bool(headless),
            timeout_ms=max(1, _to_int(timeout_ms, settings.TIMEOUT)),
            context=resolved_context,
            runtime_context=resolved_runtime_context,
        )

    def is_open(self) -> bool:
        return self.browser is not None and self.page is not None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "browser_type": self.browser_type,
            "headless": self.headless,
            "viewport": dict(self.viewport),
            "user_agent": self.user_agent,
            "launch_args": list(self.launch_args),
            "locale": self.locale,
            "timezone_id": self.timezone_id,
            "color_scheme": self.color_scheme,
            "timeout_ms": self.timeout_ms,
            "started_at": self.started_at,
            "context": self.context.to_dict() if self.context else None,
            "runtime_context": dict(self.runtime_context),
            "is_open": self.is_open(),
            "current_url": getattr(self.page, "url", "") if self.page is not None else "",
        }


# ============================================================
# SNAPSHOT DE ESTADO / UI
# ============================================================


@dataclass(frozen=True, slots=True)
class RuntimeStateSnapshot:
    context: ScraperContext
    run_options: RunOptions
    counters: RunCounters = field(default_factory=RunCounters)

    run_mode: str = settings.RUN_MODE_PRIMARY
    run_mode_label: str = settings.RUN_MODE_LABELS[settings.RUN_MODE_PRIMARY]
    resume_run_mode: str = settings.RUN_MODE_PRIMARY
    resume_run_mode_label: str = settings.RUN_MODE_LABELS[settings.RUN_MODE_PRIMARY]

    status: str = "Pronto"
    summary: str = ""
    current_phase: str = ""
    current_category: str = ""
    current_item: str = ""

    running: bool = False
    paused: bool = False
    stop_requested: bool = False
    can_continue: bool = False
    worker_name: str = ""
    worker_ident: int | None = None
    worker_alive: bool = False

    run_started_at: str = ""
    run_finished_at: str = ""
    updated_at: str = field(default_factory=_now_iso)

    timer_text: str = "0:00:00"

    current_slot: str = ""
    default_slot: str = ""
    primary_button_label: str = settings.RUN_MODE_LABELS[settings.RUN_MODE_PRIMARY]

    available_categories: tuple[Category, ...] = ()
    selected_categories: tuple[str, ...] = ()
    slots: tuple[SlotInfo, ...] = ()
    logs: tuple[str, ...] = ()

    current_run_payload: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def build_default(
        cls,
        context: ScraperContext | Mapping[str, Any] | None = None,
        *,
        run_options: RunOptions | Mapping[str, Any] | None = None,
    ) -> "RuntimeStateSnapshot":
        resolved_context = build_context(context)
        resolved_run_options = build_run_options(run_options)

        return cls(
            context=resolved_context,
            run_options=resolved_run_options,
            counters=RunCounters(),
            run_mode=settings.RUN_MODE_PRIMARY,
            run_mode_label=settings.get_run_mode_label(settings.RUN_MODE_PRIMARY),
            resume_run_mode=settings.RUN_MODE_PRIMARY,
            resume_run_mode_label=settings.get_run_mode_label(settings.RUN_MODE_PRIMARY),
            status="Pronto",
            summary="",
            current_phase="",
            current_category="",
            current_item="",
            running=False,
            paused=False,
            stop_requested=False,
            can_continue=False,
            worker_name="",
            worker_ident=None,
            worker_alive=False,
            run_started_at="",
            run_finished_at="",
            updated_at=_now_iso(),
            timer_text="0:00:00",
            current_slot=resolved_context.slot_name,
            default_slot=resolved_context.slot_name,
            primary_button_label=settings.get_run_mode_label(settings.RUN_MODE_PRIMARY),
            available_categories=(),
            selected_categories=resolved_run_options.selected_categories,
            slots=(SlotInfo.build(resolved_context.slot_name, is_default=True, is_active=True),),
            logs=(),
            current_run_payload={},
            extra={},
        )

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any] | None = None,
        *,
        context: ScraperContext | Mapping[str, Any] | None = None,
        logs: Any = None,
    ) -> "RuntimeStateSnapshot":
        data = dict(value or {})
        resolved_context = build_context(context or data)
        run_mode = str(data.get("run_mode", settings.RUN_MODE_PRIMARY) or settings.RUN_MODE_PRIMARY).strip().lower()
        resume_run_mode = str(data.get("resume_run_mode", run_mode) or run_mode).strip().lower()

        run_options = build_run_options(data)
        counters = RunCounters.from_mapping(data)

        available_categories_raw = data.get("available_categories", ())
        available_categories = tuple(
            Category.from_value(item, item_type_key=resolved_context.item_type_key)
            for item in (available_categories_raw or [])
        )

        selected_categories = _normalize_url_list(
            data.get("selected_categories", run_options.selected_categories)
        )

        slots_raw = data.get("slots", ())
        parsed_slots: list[SlotInfo] = []
        for raw_slot in slots_raw or []:
            parsed_slots.append(
                SlotInfo.build(
                    _read_field(raw_slot, "name"),
                    is_default=_to_bool(_read_field(raw_slot, "is_default"), False),
                    is_active=_to_bool(_read_field(raw_slot, "is_active"), False),
                )
            )

        normalized_logs = tuple(str(item).rstrip() for item in (logs if logs is not None else data.get("logs", ())) or ())

        known_keys = {
            "site_key",
            "item_type_key",
            "account_key",
            "slot_name",
            "run_mode",
            "run_mode_label",
            "resume_run_mode",
            "resume_run_mode_label",
            "status",
            "summary",
            "current_phase",
            "current_category",
            "current_item",
            "running",
            "paused",
            "stop_requested",
            "can_continue",
            "worker_name",
            "worker_ident",
            "worker_alive",
            "run_started_at",
            "run_finished_at",
            "updated_at",
            "timer_text",
            "current_slot",
            "default_slot",
            "primary_button_label",
            "available_categories",
            "selected_categories",
            "slots",
            "logs",
            "current_run_payload",
            "verify_mode",
            "scope_mode",
            "scope_start",
            "scope_end",
            "scope_match_text",
            "save_every_items",
            "save_every_minutes",
            "saved_count",
            "pending_count",
            "reused_categories",
            "refetched_categories",
            "queue_detected_count",
            "new_links_detected",
            "existing_links_detected",
            "new_items_added",
            "items_updated",
            "items_unchanged",
            "resume_queue_index",
            "resume_queue_total",
            "timer_seconds",
        }

        extra = {key: value for key, value in data.items() if key not in known_keys}

        return cls(
            context=resolved_context,
            run_options=run_options,
            counters=counters,
            run_mode=run_mode,
            run_mode_label=str(
                data.get("run_mode_label")
                or settings.get_run_mode_label(run_mode)
            ),
            resume_run_mode=resume_run_mode,
            resume_run_mode_label=str(
                data.get("resume_run_mode_label")
                or settings.get_run_mode_label(resume_run_mode)
            ),
            status=_normalize_spaces(data.get("status", "Pronto")) or "Pronto",
            summary=_normalize_spaces(data.get("summary", "")),
            current_phase=_normalize_spaces(data.get("current_phase", "")),
            current_category=_normalize_spaces(data.get("current_category", "")),
            current_item=_normalize_spaces(data.get("current_item", "")),
            running=_to_bool(data.get("running"), False),
            paused=_to_bool(data.get("paused"), False),
            stop_requested=_to_bool(data.get("stop_requested"), False),
            can_continue=_to_bool(data.get("can_continue"), False),
            worker_name=_normalize_spaces(data.get("worker_name", "")),
            worker_ident=(
                _to_int(data.get("worker_ident"), 0)
                if data.get("worker_ident") not in (None, "")
                else None
            ),
            worker_alive=_to_bool(data.get("worker_alive"), False),
            run_started_at=_normalize_spaces(data.get("run_started_at", "")),
            run_finished_at=_normalize_spaces(data.get("run_finished_at", "")),
            updated_at=_normalize_spaces(data.get("updated_at", "")) or _now_iso(),
            timer_text=_normalize_spaces(data.get("timer_text", "")) or "0:00:00",
            current_slot=_normalize_spaces(data.get("current_slot", "")) or resolved_context.slot_name,
            default_slot=_normalize_spaces(data.get("default_slot", "")) or resolved_context.slot_name,
            primary_button_label=_normalize_spaces(
                data.get("primary_button_label", settings.get_run_mode_label(settings.RUN_MODE_PRIMARY))
            ) or settings.get_run_mode_label(settings.RUN_MODE_PRIMARY),
            available_categories=available_categories,
            selected_categories=selected_categories,
            slots=tuple(parsed_slots),
            logs=normalized_logs,
            current_run_payload=dict(data.get("current_run_payload", {}) or {}),
            extra=extra,
        )

    def to_data_dict(self) -> dict[str, Any]:
        payload = {
            **self.context.to_dict(),
            "context_prefix": self.context.context_prefix,
            "run_mode": self.run_mode,
            "run_mode_label": self.run_mode_label,
            "resume_run_mode": self.resume_run_mode,
            "resume_run_mode_label": self.resume_run_mode_label,
            "status": self.status,
            "summary": self.summary,
            "current_phase": self.current_phase,
            "current_category": self.current_category,
            "current_item": self.current_item,
            "running": self.running,
            "paused": self.paused,
            "stop_requested": self.stop_requested,
            "can_continue": self.can_continue,
            "worker_name": self.worker_name,
            "worker_ident": self.worker_ident,
            "worker_alive": self.worker_alive,
            "run_started_at": self.run_started_at,
            "run_finished_at": self.run_finished_at,
            "updated_at": self.updated_at,
            "timer_seconds": self.counters.timer_seconds,
            "timer_text": self.timer_text,
            "saved_count": self.counters.saved_count,
            "pending_count": self.counters.pending_count,
            "reused_categories": self.counters.reused_categories,
            "refetched_categories": self.counters.refetched_categories,
            "queue_detected_count": self.counters.queue_detected_count,
            "new_links_detected": self.counters.new_links_detected,
            "existing_links_detected": self.counters.existing_links_detected,
            "new_items_added": self.counters.new_items_added,
            "items_updated": self.counters.items_updated,
            "items_unchanged": self.counters.items_unchanged,
            "resume_queue_index": self.counters.resume_queue_index,
            "resume_queue_total": self.counters.resume_queue_total,
            "verify_mode": self.run_options.verify_mode,
            "scope_mode": self.run_options.scope_mode,
            "scope_start": self.run_options.scope_start,
            "scope_end": self.run_options.scope_end,
            "scope_match_text": self.run_options.scope_match_text,
            "save_every_items": self.run_options.save_every_items,
            "save_every_minutes": self.run_options.save_every_minutes,
            "available_categories": [item.to_dict() for item in self.available_categories],
            "selected_categories": list(self.selected_categories),
            "slots": [slot.to_dict() for slot in self.slots],
            "current_slot": self.current_slot or self.context.slot_name,
            "default_slot": self.default_slot or self.context.slot_name,
            "primary_button_label": self.primary_button_label,
            "current_run_payload": dict(self.current_run_payload),
        }

        if self.extra:
            payload.update(self.extra)

        return payload

    def to_public_payload(self, *, max_logs: int | None = None) -> dict[str, Any]:
        logs = list(self.logs)
        if max_logs is not None:
            logs = logs[-max(0, int(max_logs)):]

        return {
            "data": self.to_data_dict(),
            "logs": logs,
            "context": self.context.to_dict(),
        }


# ============================================================
# HELPERS DE COMPATIBILIDADE
# ============================================================


def build_state_public_payload(
    source: RuntimeStateSnapshot | Mapping[str, Any] | None,
    *,
    context: ScraperContext | Mapping[str, Any] | None = None,
    logs: Any = None,
    max_logs: int | None = None,
) -> dict[str, Any]:
    if isinstance(source, RuntimeStateSnapshot):
        return source.to_public_payload(max_logs=max_logs)

    snapshot = RuntimeStateSnapshot.from_mapping(
        source,
        context=context,
        logs=logs,
    )
    return snapshot.to_public_payload(max_logs=max_logs)


# ============================================================
# EXPORTS
# ============================================================


__all__ = [
    "SlotInfo",
    "ScraperContext",
    "RunOptions",
    "Category",
    "CatalogItem",
    "RunCounters",
    "BrowserSessionData",
    "RuntimeStateSnapshot",
    "normalize_context_dict",
    "build_context",
    "get_default_context",
    "is_context_supported",
    "build_context_public_dict",
    "build_runtime_context_dict",
    "resolve_context_credentials",
    "is_context_configured",
    "build_run_options",
    "get_default_run_options",
    "build_state_public_payload",
]