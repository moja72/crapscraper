from __future__ import annotations

import re
import unicodedata
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

from app.integrations.woocommerce import pt_versao
from app.operations.preparation import UpdatePreparationService
from app.wordpress_manual_update import discover_catalog_candidates


_INSTALLED = False
_BASE_PREPARE: Callable[..., Any] | None = None
_SAFE_RELATIONSHIPS = {"safe_auto", "manual_confirmed"}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _name_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _clean(value)).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"\bwordpress\b", " ", text)
    text = re.sub(r"\bwoocommerce\b", " ", text)
    text = re.sub(r"\bplugins?\b", " ", text)
    text = re.sub(r"\bthemes?\b", " ", text)
    text = re.sub(r"\bwp\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _official_key(value: Any) -> str:
    raw = _clean(value)
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw.lstrip("/")
    try:
        parsed = urlparse(raw)
    except Exception:
        return ""
    host = (parsed.hostname or "").lower().removeprefix("www.")
    return host + (parsed.path or "").rstrip("/").lower()


def _source_name(value: Any) -> str:
    raw = _clean(value)
    try:
        host = (urlparse(raw).hostname or "").lower()
    except Exception:
        host = ""
    if "ultrapack" in host:
        return "UltraPackV2"
    if "plugintheme" in host:
        return "PluginTheme"
    return ""


def _version(value: Any) -> tuple[int, ...] | None:
    text = _clean(value)
    match = re.search(r"(?<!\d)(\d+(?:\.\d+){1,5})(?!\d)", text)
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def _is_newer(candidate: Any, current: Any) -> bool:
    left, right = _version(candidate), _version(current)
    if left is None or right is None:
        return False
    size = max(len(left), len(right))
    return left + (0,) * (size - len(left)) > right + (0,) * (size - len(right))


def _version_text(value: Any) -> str:
    parsed = _version(value)
    return ".".join(str(part) for part in parsed) if parsed else ""


def _current_candidate(job: Any) -> dict[str, Any]:
    return {
        "source_name": _clean(getattr(job, "name", "")),
        "source_version": _clean(
            getattr(job, "approved_source_version", "")
            or getattr(job, "ultrapack_version", "")
        ),
        "source_product_url": _clean(getattr(job, "ultrapack_url", "")),
        "source_official_url": _clean(getattr(job, "official_url", "")),
        "relationship_state": _clean(getattr(job, "relationship", "")),
    }


def _candidate_rows(job: Any, product: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = [dict(row) for row in discover_catalog_candidates(product)]
    rows.append(_current_candidate(job))

    job_name = _name_key(getattr(job, "name", "") or product.get("name"))
    job_official = _official_key(getattr(job, "official_url", ""))
    job_relationship = _clean(getattr(job, "relationship", ""))

    by_url: dict[str, dict[str, Any]] = {}
    for row in rows:
        url = _clean(row.get("source_product_url"))
        origin = _source_name(url)
        if not url or not origin:
            continue

        relationship = _clean(row.get("relationship_state"))
        row_name = _name_key(row.get("source_name"))
        row_official = _official_key(row.get("source_official_url"))
        official_conflict = bool(job_official and row_official and job_official != row_official)

        # discover_catalog_candidates já exige nome exato ou URL oficial exata.
        # Se o job atual possui vínculo seguro, o mesmo produto em outra das duas
        # fontes pode herdar o vínculo somente quando não há conflito oficial.
        if relationship not in _SAFE_RELATIONSHIPS:
            if (
                job_relationship in _SAFE_RELATIONSHIPS
                and job_name
                and row_name == job_name
                and not official_conflict
            ):
                relationship = job_relationship
                row["relationship_state"] = relationship

        if relationship not in _SAFE_RELATIONSHIPS:
            continue

        existing = by_url.get(url)
        if existing is None:
            by_url[url] = row
            continue
        current_version = _version(existing.get("source_version")) or ()
        candidate_version = _version(row.get("source_version")) or ()
        if candidate_version > current_version:
            by_url[url] = row

    # Evita revalidar várias cópias do mesmo produto em slots antigos. Mantém no
    # máximo as duas versões catalogadas mais altas por origem.
    grouped: dict[str, list[dict[str, Any]]] = {"PluginTheme": [], "UltraPackV2": []}
    for row in by_url.values():
        grouped[_source_name(row.get("source_product_url"))].append(row)

    selected: list[dict[str, Any]] = []
    for origin in ("PluginTheme", "UltraPackV2"):
        candidates = grouped[origin]
        candidates.sort(key=lambda row: _version(row.get("source_version")) or (), reverse=True)
        selected.extend(candidates[:2])
    return selected


def _inspect_candidate(self: UpdatePreparationService, job: Any, row: Mapping[str, Any]) -> str:
    url = _clean(row.get("source_product_url"))
    if not url:
        return ""

    original_url = _clean(getattr(job, "ultrapack_url", ""))
    original_session = getattr(self.downloader, "session", None)
    try:
        job.ultrapack_url = url
        if self.session_provider is not None:
            self.downloader.session = self.session_provider(job)
        _resolved_url, found_version = self.downloader.inspect_product(url)
        return _version_text(found_version)
    finally:
        job.ultrapack_url = original_url
        self.downloader.session = original_session


def _select_latest_source(self: UpdatePreparationService, job: Any) -> None:
    # Só arbitra jobs normais de atualização com vínculo seguro.
    if _clean(getattr(job, "queue_type", "")) != "update":
        return
    if _clean(getattr(job, "relationship", "")) not in _SAFE_RELATIONSHIPS:
        return

    get_product = getattr(self.woo, "get_product_fresh", None) or self.woo.get_product
    product = get_product(int(getattr(job, "woo_product_id", 0) or 0))
    current_version = _version_text(pt_versao(product))
    if not current_version:
        return

    rows = _candidate_rows(job, product)
    if not rows:
        return

    self.logger("🔎 Comparando versão atual entre PluginTheme e UltraPackV2")
    live: list[dict[str, Any]] = []
    for row in rows:
        origin = _source_name(row.get("source_product_url"))
        cached = _version_text(row.get("source_version"))
        try:
            found = _inspect_candidate(self, job, row)
        except Exception as error:
            self.logger(
                f"⚠ {origin}: não foi possível revalidar ao vivo ({type(error).__name__}); "
                f"catálogo local={cached or '-'}"
            )
            continue
        if not found:
            self.logger(f"⚠ {origin}: fonte não retornou uma versão comparável")
            continue
        current = dict(row)
        current["source_version"] = found
        current["live_validated"] = True
        current["origin"] = origin
        live.append(current)
        self.logger(f"✅ {origin}: versão ao vivo {found}")

    newer = [row for row in live if _is_newer(row.get("source_version"), current_version)]
    if not newer:
        if live:
            best_live = max(live, key=lambda row: _version(row.get("source_version")) or ())
            self.logger(
                f"ℹ Nenhuma fonte possui versão superior a {current_version}; "
                f"maior versão verificada: {best_live.get('source_version')} ({best_live.get('origin')})."
            )
        return

    # Maior versão ganha. Em empate, UltraPackV2 é preferido porque não depende
    # do entitlement especial de bundles/assinaturas do PluginTheme.
    newer.sort(
        key=lambda row: (
            _version(row.get("source_version")) or (),
            1 if row.get("origin") == "UltraPackV2" else 0,
        ),
        reverse=True,
    )
    best = newer[0]
    best_version = _version_text(best.get("source_version"))
    best_url = _clean(best.get("source_product_url"))
    best_origin = _clean(best.get("origin")) or _source_name(best_url)

    previous_url = _clean(getattr(job, "ultrapack_url", ""))
    previous_version = _clean(
        getattr(job, "approved_source_version", "")
        or getattr(job, "ultrapack_version", "")
    )

    job.ultrapack_url = best_url
    job.ultrapack_version = best_version
    job.approved_source_version = best_version
    job.effective_source_version = ""
    job.source_name = best_origin
    job.relationship = _clean(best.get("relationship_state")) or job.relationship
    if _clean(best.get("source_official_url")):
        job.official_url = _clean(best.get("source_official_url"))

    if best_url != previous_url or best_version != previous_version:
        self.logger(
            f"🚀 Fonte escolhida automaticamente: {best_origin} {best_version} "
            f"(alvo anterior {previous_version or '-'})."
        )
    else:
        self.logger(f"✅ Fonte atual já é a melhor: {best_origin} {best_version}.")


def _patched_prepare(self: UpdatePreparationService, job: Any) -> Any:
    if _BASE_PREPARE is None:
        raise RuntimeError("Preparação base indisponível")
    try:
        _select_latest_source(self, job)
    except Exception as error:
        # A arbitragem é melhoria de fonte, não um novo ponto de falha. Se os
        # catálogos estiverem indisponíveis, o fluxo original continua intacto.
        self.logger(f"⚠ Comparação cruzada de fontes indisponível: {type(error).__name__}: {error}")
    return _BASE_PREPARE(self, job)


def install_update_cross_source_latest_policy() -> None:
    global _INSTALLED, _BASE_PREPARE
    if _INSTALLED:
        return
    _BASE_PREPARE = UpdatePreparationService._prepare
    UpdatePreparationService._prepare = _patched_prepare
    _INSTALLED = True
