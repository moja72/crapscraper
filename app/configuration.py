"""Inventario central da configuracao persistida do CrapScraper.

Este modulo contem somente nomes e metadados; nunca valores de credenciais.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final, Iterable


DEFAULT_UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS: Final[frozenset[int]] = frozenset({94567})


def parse_update_execution_allowed_product_ids(raw: str | None) -> frozenset[int]:
    """Parseia IDs decimais positivos; configuracao ausente usa o fallback seguro."""
    if raw is None:
        return DEFAULT_UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS
    parsed: set[int] = set()
    for token in str(raw).split(","):
        candidate = token.strip()
        if candidate.isdecimal():
            value = int(candidate)
            if value > 0:
                parsed.add(value)
    # Uma configuração explicitamente vazia (por exemplo ``*`` sem IDs)
    # representa todos; o bloqueio global e as confirmações continuam obrigatórios.
    return frozenset(parsed)


@dataclass(frozen=True, slots=True)
class EnvironmentVariable:
    name: str
    group: str
    required_for: frozenset[str] = frozenset()
    secret: bool = False


ENVIRONMENT_VARIABLES: Final[tuple[EnvironmentVariable, ...]] = (
    EnvironmentVariable("SCRAPER_WP_BASE_URL", "wordpress", frozenset({"prepare", "execute"})),
    EnvironmentVariable("SCRAPER_WP_USERNAME", "wordpress", frozenset({"execute"})),
    EnvironmentVariable("SCRAPER_WP_APPLICATION_PASSWORD", "wordpress", frozenset({"execute"}), True),
    EnvironmentVariable("SCRAPER_WC_CONSUMER_KEY", "woocommerce", frozenset({"prepare", "execute"}), True),
    EnvironmentVariable("SCRAPER_WC_CONSUMER_SECRET", "woocommerce", frozenset({"prepare", "execute"}), True),
    EnvironmentVariable("SCRAPER_ULTRAPACKV2_COPRODUCAOLANCAMENTOS_EMAIL", "ultrapack", frozenset({"prepare", "execute"})),
    EnvironmentVariable("SCRAPER_ULTRAPACKV2_COPRODUCAOLANCAMENTOS_PASSWORD", "ultrapack", frozenset({"prepare", "execute"}), True),
    EnvironmentVariable("SCRAPER_ULTRAPACKV2_BERNARDES1992_EMAIL", "ultrapack"),
    EnvironmentVariable("SCRAPER_ULTRAPACKV2_BERNARDES1992_PASSWORD", "ultrapack", secret=True),
    EnvironmentVariable("SCRAPER_PLUGINTHEME_COPRODUCAOLANCAMENTOS_EMAIL", "plugintheme", frozenset({"collection"})),
    EnvironmentVariable("SCRAPER_PLUGINTHEME_COPRODUCAOLANCAMENTOS_PASSWORD", "plugintheme", frozenset({"collection"}), True),
    EnvironmentVariable("SCRAPER_PLUGINTHEME_BERNARDES1992_EMAIL", "plugintheme", frozenset({"collection"})),
    EnvironmentVariable("SCRAPER_PLUGINTHEME_BERNARDES1992_PASSWORD", "plugintheme", frozenset({"collection"}), True),
    EnvironmentVariable("SCRAPER_SSH_HOST", "ssh", frozenset({"prepare", "execute"})),
    EnvironmentVariable("SCRAPER_SSH_PORT", "ssh", frozenset({"prepare", "execute"})),
    EnvironmentVariable("SCRAPER_SSH_USERNAME", "ssh", frozenset({"prepare", "execute"})),
    EnvironmentVariable("SCRAPER_SSH_PASSWORD", "ssh", frozenset({"prepare", "execute"}), True),
    EnvironmentVariable("SCRAPER_UPDATE_EXECUTION_ENABLED", "update_execution"),
    EnvironmentVariable("SCRAPER_UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS", "update_execution"),
    EnvironmentVariable("SCRAPER_COMPARISON_ULTRAPACK_CSV", "other"),
    EnvironmentVariable("SCRAPER_COMPARISON_PLUGINTEMA_CSV", "other"),
)

WINDOWS_USER_ENVIRONMENT_KEYS: Final[tuple[str, ...]] = tuple(
    item.name for item in ENVIRONMENT_VARIABLES
)
SECRET_ENVIRONMENT_KEYS: Final[frozenset[str]] = frozenset(
    item.name for item in ENVIRONMENT_VARIABLES if item.secret
)


def names_for(*, group: str | None = None, stage: str | None = None) -> tuple[str, ...]:
    return tuple(
        item.name for item in ENVIRONMENT_VARIABLES
        if (group is None or item.group == group)
        and (stage is None or stage in item.required_for)
    )


def presence(names: Iterable[str] | None = None) -> dict[str, bool]:
    selected = tuple(names) if names is not None else WINDOWS_USER_ENVIRONMENT_KEYS
    return {name: bool(os.getenv(name, "").strip()) for name in selected}


def missing_for(stage: str) -> tuple[str, ...]:
    state = presence(names_for(stage=stage))
    return tuple(name for name, configured in state.items() if not configured)


def prerequisite_status() -> dict[str, object]:
    groups = {
        "woocommerce": names_for(group="wordpress", stage="prepare")
        + names_for(group="woocommerce", stage="prepare"),
        "ultrapack": names_for(group="ultrapack", stage="prepare"),
        "ssh_read": names_for(group="ssh", stage="prepare"),
    }
    result: dict[str, object] = {}
    for key, names in groups.items():
        configured = presence(names)
        result[key] = {
            "ok": all(configured.values()),
            "status": "OK" if all(configured.values()) else "FALTA CONFIGURAÇÃO",
            "variables": {name: "PRESENTE" if value else "AUSENTE" for name, value in configured.items()},
        }
    raw_execution = os.getenv("SCRAPER_UPDATE_EXECUTION_ENABLED", "")
    execution_enabled = raw_execution.strip().lower() in {"1", "true", "yes", "on"}
    allowed_ids = parse_update_execution_allowed_product_ids(
        os.getenv("SCRAPER_UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS")
    )
    result["update_execution"] = {
        "configured": bool(raw_execution.strip()),
        "enabled": execution_enabled,
        "status": "HABILITADA" if execution_enabled else "BLOQUEADA",
        "allowed_product_ids": sorted(allowed_ids),
        "allow_all_products": not bool(allowed_ids) and os.getenv(
            "SCRAPER_UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS", ""
        ).strip() == "*",
    }
    result["remote_execution"] = {"ok": execution_enabled, "status": "HABILITADA" if execution_enabled else "BLOQUEADA"}
    result["woocommerce_write"] = {"ok": False, "status": "BLOQUEADA"}
    return result
