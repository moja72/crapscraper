from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


WINDOWS_USER_ENVIRONMENT_KEYS = (
    "SCRAPER_WP_BASE_URL", "SCRAPER_WORDPRESS_MANUAL_SECRET", "SCRAPER_WOOCOMMERCE_URL",
    "SCRAPER_WC_CONSUMER_KEY", "SCRAPER_WC_CONSUMER_SECRET",
    "SCRAPER_WOOCOMMERCE_KEY", "SCRAPER_WOOCOMMERCE_SECRET",
    "SCRAPER_SSH_HOST", "SCRAPER_SSH_PORT", "SCRAPER_SSH_USERNAME",
    "SCRAPER_SSH_USER", "SCRAPER_SSH_PASSWORD", "SCRAPER_SSH_KEY_PATH",
    "SCRAPER_SSH_DOWNLOAD_ROOT", "SCRAPER_UPDATE_TARGET_DIR",
    "SCRAPER_UPDATE_EXECUTION_ENABLED", "SCRAPER_UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS",
    "SCRAPER_STORE_WRITE_ENABLED",
    "SCRAPER_ULTRAPACK_HEADERS_JSON", "SCRAPER_ULTRAPACK_COOKIES_JSON",
    "SCRAPER_PLUGINTHEME_HEADERS_JSON", "SCRAPER_PLUGINTHEME_COOKIES_JSON",
    "SCRAPER_ULTRAPACKV2_COPRODUCAOLANCAMENTOS_EMAIL", "SCRAPER_ULTRAPACKV2_COPRODUCAOLANCAMENTOS_PASSWORD",
    "SCRAPER_ULTRAPACKV2_BERNARDES1992_EMAIL", "SCRAPER_ULTRAPACKV2_BERNARDES1992_PASSWORD",
    "SCRAPER_PLUGINTHEME_COPRODUCAOLANCAMENTOS_EMAIL", "SCRAPER_PLUGINTHEME_COPRODUCAOLANCAMENTOS_PASSWORD",
    "SCRAPER_PLUGINTHEME_BERNARDES1992_EMAIL", "SCRAPER_PLUGINTHEME_BERNARDES1992_PASSWORD",
)


@dataclass(frozen=True)
class Settings:
    root: Path
    data_dir: Path
    host: str
    port: int


def load_settings() -> Settings:
    root = Path(__file__).resolve().parents[1]
    legacy_data = root.parent / "data"
    settings = Settings(
        root=root,
        data_dir=Path(os.getenv("SCRAPER_DATA_DIR", legacy_data)).resolve(),
        host=os.getenv("SCRAPER_HOST", "127.0.0.1"),
        port=int(os.getenv("SCRAPER_PORT", "8766")),
    )
    os.environ.setdefault("SCRAPER_DATA_DIR", str(settings.data_dir))
    return settings


def parse_update_execution_allowed_product_ids(value: str | None) -> frozenset[int]:
    result: set[int] = set()
    for item in str(value or "").split(","):
        text = item.strip()
        if text.isdigit() and int(text) > 0:
            result.add(int(text))
    return frozenset(result)
