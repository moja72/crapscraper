from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final
from urllib.parse import urljoin
from app.configuration import parse_update_execution_allowed_product_ids


# ============================================================
# CAMINHOS BASE DO PROJETO
# ============================================================

SETTINGS_FILE: Final[Path] = Path(__file__).resolve()
APP_DIR: Final[Path] = SETTINGS_FILE.parent
PROJECT_ROOT: Final[Path] = APP_DIR.parent

DATA_DIR: Final[Path] = PROJECT_ROOT / "data"
LOGS_DIR: Final[Path] = PROJECT_ROOT / "logs"
SLOTS_DIR: Final[Path] = DATA_DIR / "slots"
SLOTS_META_JSON_PATH: Final[Path] = DATA_DIR / "slots_meta.json"
FILA_JSON_PATH: Final[Path] = DATA_DIR / "fila.json"

# Arquivos usados pela primeira etapa da comparação de catálogos.
# Depois, o catálogo do Ultrapack poderá vir diretamente do slot ativo e
# o catálogo PluginTema poderá vir da API do WordPress.
COMPARISON_ULTRAPACK_CSV_PATH: Final[Path] = Path(
    os.getenv(
        "SCRAPER_COMPARISON_ULTRAPACK_CSV",
        str(PROJECT_ROOT / "Temas - Ultrapackv2.csv"),
    )
).expanduser()
COMPARISON_PLUGINTEMA_CSV_PATH: Final[Path] = Path(
    os.getenv(
        "SCRAPER_COMPARISON_PLUGINTEMA_CSV",
        str(PROJECT_ROOT / "Temas - PluginTema.csv"),
    )
).expanduser()
COMPARISON_DEFAULT_PAGE_SIZE: Final[int] = 100
COMPARISON_MAX_PAGE_SIZE: Final[int] = 1000
COMPARISON_IMPORTS_DIR: Final[Path] = DATA_DIR / "imports"
COMPARISON_DECISIONS_DB_PATH: Final[Path] = (
    DATA_DIR / "comparison_decisions.sqlite3"
)

# Trava de seguranca da integracao WordPress/WooCommerce. Esta fase e
# deliberadamente read-only; habilitar escrita exige uma alteracao de codigo
# revisada, alem da trava independente ``dry_run`` do executor.
WORDPRESS_WRITE_ENABLED: Final[bool] = False

# Trava independente do armazenamento SSH/SFTP. Nao deve ser derivada de
# variavel de ambiente: habilita-la exige uma alteracao de codigo revisada.
SSH_STORAGE_WRITE_ENABLED: Final[bool] = False
SSH_DOWNLOAD_ROOT: Final[str] = "/home/plugintema.com/downloads"
# Trava adicional: nem mesmo o cliente restrito executa sudo nesta etapa.
SSH_HELPER_EXECUTION_ENABLED: Final[bool] = False
UPDATE_EXECUTION_ENABLED: Final[bool] = os.getenv(
    "SCRAPER_UPDATE_EXECUTION_ENABLED", ""
).strip().lower() in {"1", "true", "yes", "on"}
UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS: Final[frozenset[int]] = (
    parse_update_execution_allowed_product_ids(
        os.getenv("SCRAPER_UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS")
    )
)
UPDATE_RUNTIME_PATH: Final[Path] = DATA_DIR / "update_runtime.json"
UPDATE_QUEUES_DIR: Final[Path] = DATA_DIR / "update_queues"
UPDATE_BATCH_CONCURRENCY: Final[int] = 1
UPDATE_BACKUP_RETENTION_DAYS: Final[int] = 30
# Cleanup remoto permanece uma operacao manual futura, nunca parte do execute.
UPDATE_REMOTE_CLEANUP_ENABLED: Final[bool] = False

PANEL_CSS_PATH: Final[Path] = APP_DIR / "static" / "panel.css"
PANEL_JS_PATH: Final[Path] = APP_DIR / "static" / "panel.js"

CATALOG_CSV_FILENAME: Final[str] = "catalog.csv"
CATALOG_JSON_FILENAME: Final[str] = "catalog.json"
PROGRESS_JSON_FILENAME: Final[str] = "progress.json"
CATEGORIES_CACHE_JSON_FILENAME: Final[str] = "categories_cache.json"
QUEUE_CACHE_JSON_FILENAME: Final[str] = "queue_cache.json"
CONFIG_JSON_FILENAME: Final[str] = "config.json"
STATUS_TXT_FILENAME: Final[str] = "status.txt"
LAST_LOGS_TXT_FILENAME: Final[str] = "last_logs.txt"
RUNTIME_LOG_FILENAME: Final[str] = "runtime.log"


# ============================================================
# CONTEXTO PADRÃO
# ============================================================

DEFAULT_SITE_KEY: Final[str] = "ultrapackv2"
DEFAULT_ITEM_TYPE_KEY: Final[str] = "plugin"
DEFAULT_ACCOUNT_KEY: Final[str] = "coproducaolancamentos"
DEFAULT_SLOT_NAME: Final[str] = "default"


# ============================================================
# EXECUÇÃO DO SCRAPER
# ============================================================

HEADLESS: Final[bool] = False
DELAY: Final[float] = 1.4
TIMEOUT: Final[int] = 30_000
MAX_PAGINAS_FALLBACK: Final[int] = 200
RETOMAR_DE_ONDE_PAROU: Final[bool] = True

TEST_MODE: Final[bool] = False
TESTE_MAX_CATEGORIAS: Final[int] = 2
TESTE_MAX_ITENS_POR_CATEGORIA: Final[int] = 15

DEFAULT_VERIFY_MODE: Final[str] = "complete"
DEFAULT_SCOPE_MODE: Final[str] = "all"
DEFAULT_SCOPE_START: Final[int] = 1
DEFAULT_SCOPE_END: Final[int] = 0
DEFAULT_SCOPE_MATCH_TEXT: Final[str] = ""
DEFAULT_SAVE_EVERY_ITEMS: Final[int] = 10
DEFAULT_SAVE_EVERY_MINUTES: Final[int] = 10

VERIFY_MODES: Final[frozenset[str]] = frozenset({"normal", "complete"})
SCOPE_MODES: Final[frozenset[str]] = frozenset({"all", "range", "match", "selected"})

PLUGINTHEME_USE_HTTP_LISTING: Final[bool] = True
ULTRAPACKV2_USE_HTTP_LISTING: Final[bool] = False
ULTRAPACKV2_HTTP_PAGE_SIZE: Final[int] = 128
ULTRAPACKV2_GROUPED_CATEGORY_SINGLE_PAGE: Final[bool] = True
ULTRAPACKV2_HTTP_CATEGORY_COOLDOWN_SECONDS: Final[float] = 0.45

HTTP_RETRY_ATTEMPTS: Final[int] = 3
HTTP_RETRY_DELAY_SECONDS: Final[float] = 1.2
HTTP_ACCEPT_HEADER: Final[str] = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8"
)
HTTP_ACCEPT_LANGUAGE: Final[str] = "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"
HTTP_ACCEPT_ENCODING: Final[str] = "gzip, deflate"


# ============================================================
# PLAYWRIGHT / NAVEGADOR
# ============================================================

PLAYWRIGHT_VIEWPORT: Final[dict[str, int]] = {"width": 1440, "height": 900}
PLAYWRIGHT_USER_AGENT: Final[str] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
PLAYWRIGHT_LAUNCH_ARGS: Final[tuple[str, ...]] = (
    "--disable-blink-features=AutomationControlled",
)
PLAYWRIGHT_LOCALE: Final[str | None] = "pt-BR"
PLAYWRIGHT_TIMEZONE_ID: Final[str | None] = "America/Sao_Paulo"
PLAYWRIGHT_COLOR_SCHEME: Final[str | None] = "dark"
PLUGINTHEME_BROWSER_PROFILES_DIR: Final[Path] = (
    DATA_DIR / "browser_profiles" / "plugintheme"
)


# ============================================================
# PAINEL WEB
# ============================================================

PANEL_HOST: Final[str] = "127.0.0.1"
PANEL_PORT: Final[int] = 8765
PANEL_AUTO_OPEN_BROWSER: Final[bool] = True
STATE_POLL_INTERVAL_MS: Final[int] = 1200
STATE_MAX_LOGS_IN_MEMORY: Final[int] = 5000
STATE_SNAPSHOT_LOGS_LIMIT: Final[int] = 600


# ============================================================
# MODOS DE EXECUÇÃO
# ============================================================

RUN_MODE_FULL: Final[str] = "full_sync"
RUN_MODE_CATEGORIES_ONLY: Final[str] = "categories_only"
RUN_MODE_LINKS_ONLY: Final[str] = "links_only"
RUN_MODE_EXISTING_REVIEW: Final[str] = "existing_review"
RUN_MODE_PRIMARY: Final[str] = "primary"

RUN_MODES: Final[frozenset[str]] = frozenset(
    {
        RUN_MODE_FULL,
        RUN_MODE_CATEGORIES_ONLY,
        RUN_MODE_LINKS_ONLY,
        RUN_MODE_EXISTING_REVIEW,
        RUN_MODE_PRIMARY,
    }
)

RUN_MODES_WITH_DETAIL: Final[frozenset[str]] = frozenset(
    {
        RUN_MODE_FULL,
        RUN_MODE_EXISTING_REVIEW,
    }
)

RUN_MODE_LABELS: Final[dict[str, str]] = {
    RUN_MODE_FULL: "Iniciar",
    RUN_MODE_CATEGORIES_ONLY: "Atualizar categorias",
    RUN_MODE_LINKS_ONLY: "Detectar links",
    RUN_MODE_EXISTING_REVIEW: "Revisar salvos",
    RUN_MODE_PRIMARY: "Iniciar",
}


# ============================================================
# MODELOS DE CADASTRO ESTRUTURAL
# ============================================================


@dataclass(frozen=True, slots=True)
class ItemTypeDefinition:
    key: str
    label_singular: str
    label_plural: str
    slug_plural: str
    default_catalog_path: str
    default_item_kind_value: str
    supports_categories: bool = True
    supports_versioning: bool = True
    supports_observation: bool = True


@dataclass(frozen=True, slots=True)
class SiteDefinition:
    key: str
    label: str
    base_url: str
    supported_item_types: tuple[str, ...]
    login_path_candidates: tuple[str, ...] = (
        "/login",
        "/minha-conta",
        "/my-account",
        "/wp-login.php",
        "/entrar",
        "/account",
    )
    catalog_path_by_item_type: dict[str, str] = field(default_factory=dict)
    grouped_category_hints_by_item_type: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AccountSiteCredentials:
    site_key: str
    login_email: str = ""
    login_password: str = ""
    env_email_var: str | None = None
    env_password_var: str | None = None


@dataclass(frozen=True, slots=True)
class AccountDefinition:
    key: str
    label: str
    supported_item_types: tuple[str, ...]
    site_credentials: dict[str, AccountSiteCredentials]
    notes: str = ""


# ============================================================
# CADASTRO DE TIPOS DE ITEM
# ============================================================

ITEM_TYPES: Final[dict[str, ItemTypeDefinition]] = {
    "plugin": ItemTypeDefinition(
        key="plugin",
        label_singular="Plugin",
        label_plural="Plugins",
        slug_plural="plugins",
        default_catalog_path="/plugins/",
        default_item_kind_value="plugin",
    ),
    "theme": ItemTypeDefinition(
        key="theme",
        label_singular="Tema",
        label_plural="Temas",
        slug_plural="temas",
        default_catalog_path="/temas/",
        default_item_kind_value="tema",
    ),
    "plugin_theme": ItemTypeDefinition(
        key="plugin_theme",
        label_singular="Plugin e Tema",
        label_plural="Plugin e Tema",
        slug_plural="plugin-e-tema",
        default_catalog_path="/pt-BR/brands",
        default_item_kind_value="plugin/theme",
    ),
    "template": ItemTypeDefinition(
        key="template",
        label_singular="Template",
        label_plural="Templates",
        slug_plural="templates",
        default_catalog_path="/extras/elementor-template-kits/",
        default_item_kind_value="template",
        supports_categories=False,
    ),
}


# ============================================================
# CADASTRO DE SITES
# ============================================================

SITES: Final[dict[str, SiteDefinition]] = {
    "ultrapackv2": SiteDefinition(
        key="ultrapackv2",
        label="UltraPackV2",
        base_url="https://www.ultrapackv2.com",
        supported_item_types=("plugin", "theme", "template"),
        grouped_category_hints_by_item_type={
            "plugin": (
                "https://www.ultrapackv2.com/plugins/codecanyon/",
            ),
            "theme": (
                "https://www.ultrapackv2.com/temas/themeforest/",
            ),
            "template": (),
        },
    ),

  "plugintheme": SiteDefinition(
    key="plugintheme",
    label="PluginTheme",
    base_url="https://plugintheme.net",
    supported_item_types=("plugin_theme",),
    login_path_candidates=(
        "/auth/login",
        "/pt-BR/auth/login",
        "/pt-BR/account",
        "/account",
        "/login",
        "/minha-conta",
        "/my-account",
        "/wp-login.php",
        "/entrar",
    ),
    catalog_path_by_item_type={
        "plugin_theme": "/pt-BR/brands",
    },
    grouped_category_hints_by_item_type={
        "plugin_theme": (),
    },
),
}


# ============================================================
# CADASTRO DE CONTAS
# ============================================================

ACCOUNTS: Final[dict[str, AccountDefinition]] = {
    "coproducaolancamentos": AccountDefinition(
        key="coproducaolancamentos",
        label="Coprodução Lançamentos",
        supported_item_types=("plugin", "theme", "plugin_theme", "template"),
        site_credentials={
            "ultrapackv2": AccountSiteCredentials(
                site_key="ultrapackv2",
                login_email="",
                login_password="",
                env_email_var="SCRAPER_ULTRAPACKV2_COPRODUCAOLANCAMENTOS_EMAIL",
                env_password_var="SCRAPER_ULTRAPACKV2_COPRODUCAOLANCAMENTOS_PASSWORD",
            ),
            "plugintheme": AccountSiteCredentials(
                site_key="plugintheme",
                login_email="",
                login_password="",
                env_email_var="SCRAPER_PLUGINTHEME_COPRODUCAOLANCAMENTOS_EMAIL",
                env_password_var="SCRAPER_PLUGINTHEME_COPRODUCAOLANCAMENTOS_PASSWORD",
            ),
        },
        notes="Conta principal atual.",
    ),

    "bernardes1992": AccountDefinition(
        key="bernardes1992",
        label="Bernardes 1992",
        supported_item_types=("plugin", "theme", "plugin_theme", "template"),
        site_credentials={
            "ultrapackv2": AccountSiteCredentials(
                site_key="ultrapackv2",
                login_email="",
                login_password="",
                env_email_var="SCRAPER_ULTRAPACKV2_BERNARDES1992_EMAIL",
                env_password_var="SCRAPER_ULTRAPACKV2_BERNARDES1992_PASSWORD",
            ),
            "plugintheme": AccountSiteCredentials(
                site_key="plugintheme",
                login_email="",
                login_password="",
                env_email_var="SCRAPER_PLUGINTHEME_BERNARDES1992_EMAIL",
                env_password_var="SCRAPER_PLUGINTHEME_BERNARDES1992_PASSWORD",
            ),
        },
        notes="Conta secundária.",
    ),
}


# ============================================================
# HELPERS DE NORMALIZAÇÃO
# ============================================================

_KEY_SANITIZER_RE: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9._-]+")
_SLOT_SANITIZER_RE: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9._ -]+")


def normalize_registry_key(value: str | None, fallback: str) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("\\", "-").replace("/", "-").replace(":", "-")
    text = re.sub(r"\s+", "-", text)
    text = _KEY_SANITIZER_RE.sub("", text)
    text = re.sub(r"-{2,}", "-", text).strip("-._ ")
    return text or fallback


def normalize_slot_name(value: str | None) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("\\", " ").replace("/", " ").replace(":", " ")
    text = _SLOT_SANITIZER_RE.sub("", text)
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-._ ")
    return text or DEFAULT_SLOT_NAME


def normalize_site_key(value: str | None) -> str:
    key = normalize_registry_key(value, DEFAULT_SITE_KEY)
    return key if key in SITES else DEFAULT_SITE_KEY


def normalize_item_type_key(value: str | None) -> str:
    key = normalize_registry_key(value, DEFAULT_ITEM_TYPE_KEY)
    return key if key in ITEM_TYPES else DEFAULT_ITEM_TYPE_KEY


def normalize_account_key(value: str | None) -> str:
    key = normalize_registry_key(value, DEFAULT_ACCOUNT_KEY)
    return key if key in ACCOUNTS else DEFAULT_ACCOUNT_KEY


# ============================================================
# HELPERS DE CONSULTA
# ============================================================


def has_site(value: str | None) -> bool:
    return normalize_registry_key(value, "") in SITES


def has_item_type(value: str | None) -> bool:
    return normalize_registry_key(value, "") in ITEM_TYPES


def has_account(value: str | None) -> bool:
    return normalize_registry_key(value, "") in ACCOUNTS


def get_site(value: str | None = None) -> SiteDefinition:
    return SITES[normalize_site_key(value)]


def get_item_type(value: str | None = None) -> ItemTypeDefinition:
    return ITEM_TYPES[normalize_item_type_key(value)]


def get_account(value: str | None = None) -> AccountDefinition:
    return ACCOUNTS[normalize_account_key(value)]


def list_sites() -> list[SiteDefinition]:
    return list(SITES.values())


def list_item_types() -> list[ItemTypeDefinition]:
    return list(ITEM_TYPES.values())


def list_accounts() -> list[AccountDefinition]:
    return list(ACCOUNTS.values())


def list_site_keys() -> list[str]:
    return list(SITES.keys())


def list_item_type_keys() -> list[str]:
    return list(ITEM_TYPES.keys())


def list_account_keys() -> list[str]:
    return list(ACCOUNTS.keys())


# ============================================================
# REGRAS DE SUPORTE / COMPATIBILIDADE
# ============================================================


def site_supports_item_type(site_key: str | None, item_type_key: str | None) -> bool:
    site = get_site(site_key)
    item_type = normalize_item_type_key(item_type_key)
    return item_type in site.supported_item_types


def ensure_supported_item_type(site_key: str | None, item_type_key: str | None) -> str:
    normalized_item_type = normalize_item_type_key(item_type_key)

    if normalized_item_type not in ITEM_TYPES:
        raise ValueError(f"Tipo inválido: {item_type_key!r}")

    site = get_site(site_key)
    if normalized_item_type not in site.supported_item_types:
        raise ValueError(
            f"O site '{site.key}' não suporta o tipo '{normalized_item_type}'."
        )

    return normalized_item_type


def account_supports_site(account_key: str | None, site_key: str | None) -> bool:
    if not has_site(site_key):
        return False
    account = get_account(account_key)
    return normalize_site_key(site_key) in account.site_credentials


def account_supports_item_type(account_key: str | None, item_type_key: str | None) -> bool:
    if not has_item_type(item_type_key):
        return False
    account = get_account(account_key)
    return normalize_item_type_key(item_type_key) in account.supported_item_types


def ensure_account_supported(
    site_key: str | None,
    item_type_key: str | None,
    account_key: str | None,
) -> str:
    normalized_site_key = normalize_site_key(site_key)
    normalized_item_type_key = normalize_item_type_key(item_type_key)
    normalized_account_key = normalize_account_key(account_key)

    if normalized_site_key not in SITES:
        raise ValueError(f"Site inválido: {site_key!r}")

    if normalized_item_type_key not in ITEM_TYPES:
        raise ValueError(f"Tipo inválido: {item_type_key!r}")

    if normalized_account_key not in ACCOUNTS:
        raise ValueError(f"Conta inválida: {account_key!r}")

    if not account_supports_site(normalized_account_key, normalized_site_key):
        raise ValueError(
            f"A conta '{normalized_account_key}' não suporta o site '{normalized_site_key}'."
        )

    if not account_supports_item_type(normalized_account_key, normalized_item_type_key):
        raise ValueError(
            f"A conta '{normalized_account_key}' não suporta o tipo '{normalized_item_type_key}'."
        )

    return normalized_account_key


# ============================================================
# HELPERS DE URL / CREDENCIAIS
# ============================================================


def build_site_base_url(site_key: str | None = None) -> str:
    return get_site(site_key).base_url.rstrip("/")


def build_catalog_url(site_key: str | None = None, item_type_key: str | None = None) -> str:
    site = get_site(site_key)
    normalized_item_type = ensure_supported_item_type(site.key, item_type_key)

    site_catalog_path = str(
        site.catalog_path_by_item_type.get(normalized_item_type, "") or ""
    ).strip()

    if site_catalog_path:
        return urljoin(site.base_url.rstrip("/") + "/", site_catalog_path.lstrip("/"))

    item_type = get_item_type(normalized_item_type)
    return urljoin(site.base_url.rstrip("/") + "/", item_type.default_catalog_path.lstrip("/"))


def build_login_urls(site_key: str | None = None) -> list[str]:
    site = get_site(site_key)
    base = site.base_url.rstrip("/") + "/"
    return [urljoin(base, path.lstrip("/")) for path in site.login_path_candidates]


def get_grouped_category_hints(
    site_key: str | None = None,
    item_type_key: str | None = None,
) -> tuple[str, ...]:
    site = get_site(site_key)
    normalized_item_type = ensure_supported_item_type(site.key, item_type_key)
    return tuple(site.grouped_category_hints_by_item_type.get(normalized_item_type, ()))


def get_account_site_credentials(
    account_key: str | None = None,
    site_key: str | None = None,
) -> AccountSiteCredentials:
    normalized_account_key = normalize_account_key(account_key)
    normalized_site_key = normalize_site_key(site_key)

    if not account_supports_site(normalized_account_key, normalized_site_key):
        raise ValueError(
            f"A conta '{normalized_account_key}' não possui credenciais para o site '{normalized_site_key}'."
        )

    return get_account(normalized_account_key).site_credentials[normalized_site_key]


def resolve_account_credentials(
    account_key: str | None = None,
    site_key: str | None = None,
) -> dict[str, str | None]:
    creds = get_account_site_credentials(account_key, site_key)

    email = (
        os.getenv(creds.env_email_var, "").strip()
        if creds.env_email_var
        else ""
    ) or creds.login_email

    password = (
        os.getenv(creds.env_password_var, "").strip()
        if creds.env_password_var
        else ""
    ) or creds.login_password

    resolved_email_var = creds.env_email_var
    resolved_password_var = creds.env_password_var
    credential_source = creds.site_key

    # PluginTheme usa as mesmas contas cadastradas no UltraPack. Mantemos a
    # possibilidade de sobrescrever por site, mas herdamos as credenciais da
    # mesma conta quando as variáveis específicas não estiverem preenchidas.
    if creds.site_key == "plugintheme" and (not email or not password):
        ultrapack = get_account_site_credentials(account_key, "ultrapackv2")
        fallback_email = (
            os.getenv(ultrapack.env_email_var, "").strip()
            if ultrapack.env_email_var else ""
        ) or ultrapack.login_email
        fallback_password = (
            os.getenv(ultrapack.env_password_var, "").strip()
            if ultrapack.env_password_var else ""
        ) or ultrapack.login_password
        if not email and fallback_email:
            email, resolved_email_var = fallback_email, ultrapack.env_email_var
        if not password and fallback_password:
            password, resolved_password_var = fallback_password, ultrapack.env_password_var
        if email and password:
            credential_source = "ultrapackv2"

    return {
        "site_key": creds.site_key,
        "login_email": email,
        "login_password": password,
        "env_email_var": resolved_email_var,
        "env_password_var": resolved_password_var,
        "credential_source": credential_source,
    }


def is_account_configured(
    account_key: str | None = None,
    site_key: str | None = None,
) -> bool:
    creds = resolve_account_credentials(account_key, site_key)
    return bool(creds["login_email"] and creds["login_password"])


# ============================================================
# HELPERS DE CONFIG / DEFAULTS
# ============================================================


def build_default_context() -> dict[str, str]:
    return {
        "site_key": DEFAULT_SITE_KEY,
        "item_type_key": DEFAULT_ITEM_TYPE_KEY,
        "account_key": DEFAULT_ACCOUNT_KEY,
        "slot_name": DEFAULT_SLOT_NAME,
    }


def build_default_run_options() -> dict[str, Any]:
    return {
        "verify_mode": DEFAULT_VERIFY_MODE,
        "scope_mode": DEFAULT_SCOPE_MODE,
        "scope_start": DEFAULT_SCOPE_START,
        "scope_end": DEFAULT_SCOPE_END,
        "scope_match_text": DEFAULT_SCOPE_MATCH_TEXT,
        "save_every_items": DEFAULT_SAVE_EVERY_ITEMS,
        "save_every_minutes": DEFAULT_SAVE_EVERY_MINUTES,
        "selected_categories": [],
    }


def get_run_mode_label(value: str | None) -> str:
    run_mode = str(value or "").strip().lower()
    return RUN_MODE_LABELS.get(run_mode, RUN_MODE_LABELS[RUN_MODE_PRIMARY])


def build_structural_public_settings() -> dict[str, Any]:
    return {
        "default_context": build_default_context(),
        "run_modes": list(RUN_MODES),
        "run_mode_labels": dict(RUN_MODE_LABELS),
        "verify_modes": list(VERIFY_MODES),
        "scope_modes": list(SCOPE_MODES),
        "sites": [
            {
                "key": site.key,
                "label": site.label,
                "base_url": site.base_url,
                "supported_item_types": list(site.supported_item_types),
                "login_path_candidates": list(site.login_path_candidates),
                "catalog_path_by_item_type": dict(site.catalog_path_by_item_type),
                "grouped_category_hints_by_item_type": {
                    key: list(value)
                    for key, value in site.grouped_category_hints_by_item_type.items()
                },
            }
            for site in list_sites()
        ],
        "item_types": [
            {
                "key": item.key,
                "label_singular": item.label_singular,
                "label_plural": item.label_plural,
                "slug_plural": item.slug_plural,
                "default_catalog_path": item.default_catalog_path,
                "default_item_kind_value": item.default_item_kind_value,
                "supports_categories": item.supports_categories,
                "supports_versioning": item.supports_versioning,
                "supports_observation": item.supports_observation,
            }
            for item in list_item_types()
        ],
        "accounts": [
            {
                "key": account.key,
                "label": account.label,
                "supported_item_types": list(account.supported_item_types),
                "supported_sites": list(account.site_credentials.keys()),
                "notes": account.notes,
            }
            for account in list_accounts()
        ],
    }


__all__ = [
    # paths
    "SETTINGS_FILE",
    "APP_DIR",
    "PROJECT_ROOT",
    "DATA_DIR",
    "LOGS_DIR",
    "SLOTS_DIR",
    "SLOTS_META_JSON_PATH",
    "FILA_JSON_PATH",
    "UPDATE_QUEUES_DIR",
    "COMPARISON_ULTRAPACK_CSV_PATH",
    "COMPARISON_PLUGINTEMA_CSV_PATH",
    "COMPARISON_DEFAULT_PAGE_SIZE",
    "COMPARISON_MAX_PAGE_SIZE",
    "COMPARISON_IMPORTS_DIR",
    "COMPARISON_DECISIONS_DB_PATH",
    "PANEL_CSS_PATH",
    "PANEL_JS_PATH",
    "CATALOG_CSV_FILENAME",
    "CATALOG_JSON_FILENAME",
    "PROGRESS_JSON_FILENAME",
    "CATEGORIES_CACHE_JSON_FILENAME",
    "QUEUE_CACHE_JSON_FILENAME",
    "CONFIG_JSON_FILENAME",
    "STATUS_TXT_FILENAME",
    "LAST_LOGS_TXT_FILENAME",
    "RUNTIME_LOG_FILENAME",
    # defaults
    "DEFAULT_SITE_KEY",
    "DEFAULT_ITEM_TYPE_KEY",
    "DEFAULT_ACCOUNT_KEY",
    "DEFAULT_SLOT_NAME",
    # execution
    "HEADLESS",
    "DELAY",
    "TIMEOUT",
    "MAX_PAGINAS_FALLBACK",
    "RETOMAR_DE_ONDE_PAROU",
    "TEST_MODE",
    "TESTE_MAX_CATEGORIAS",
    "TESTE_MAX_ITENS_POR_CATEGORIA",
    "DEFAULT_VERIFY_MODE",
    "DEFAULT_SCOPE_MODE",
    "DEFAULT_SCOPE_START",
    "DEFAULT_SCOPE_END",
    "DEFAULT_SCOPE_MATCH_TEXT",
    "DEFAULT_SAVE_EVERY_ITEMS",
    "DEFAULT_SAVE_EVERY_MINUTES",
    "VERIFY_MODES",
    "SCOPE_MODES",
    "PLUGINTHEME_USE_HTTP_LISTING",
    "ULTRAPACKV2_USE_HTTP_LISTING",
    # browser/web
    "PLAYWRIGHT_VIEWPORT",
    "PLAYWRIGHT_USER_AGENT",
    "PLAYWRIGHT_LAUNCH_ARGS",
    "PLAYWRIGHT_LOCALE",
    "PLAYWRIGHT_TIMEZONE_ID",
    "PLAYWRIGHT_COLOR_SCHEME",
    "PLUGINTHEME_BROWSER_PROFILES_DIR",
    "PANEL_HOST",
    "PANEL_PORT",
    "PANEL_AUTO_OPEN_BROWSER",
    "STATE_POLL_INTERVAL_MS",
    "STATE_MAX_LOGS_IN_MEMORY",
    "STATE_SNAPSHOT_LOGS_LIMIT",
    # run modes
    "RUN_MODE_FULL",
    "RUN_MODE_CATEGORIES_ONLY",
    "RUN_MODE_LINKS_ONLY",
    "RUN_MODE_EXISTING_REVIEW",
    "RUN_MODE_PRIMARY",
    "RUN_MODES",
    "RUN_MODES_WITH_DETAIL",
    "RUN_MODE_LABELS",
    # registries
    "ItemTypeDefinition",
    "SiteDefinition",
    "AccountSiteCredentials",
    "AccountDefinition",
    "ITEM_TYPES",
    "SITES",
    "ACCOUNTS",
    # helpers
    "normalize_registry_key",
    "normalize_slot_name",
    "normalize_site_key",
    "normalize_item_type_key",
    "normalize_account_key",
    "has_site",
    "has_item_type",
    "has_account",
    "get_site",
    "get_item_type",
    "get_account",
    "list_sites",
    "list_item_types",
    "list_accounts",
    "list_site_keys",
    "list_item_type_keys",
    "list_account_keys",
    "site_supports_item_type",
    "ensure_supported_item_type",
    "account_supports_site",
    "account_supports_item_type",
    "ensure_account_supported",
    "build_site_base_url",
    "build_catalog_url",
    "build_login_urls",
    "get_grouped_category_hints",
    "get_account_site_credentials",
    "resolve_account_credentials",
    "is_account_configured",
    "build_default_context",
    "build_default_run_options",
    "get_run_mode_label",
    "build_structural_public_settings",
]
