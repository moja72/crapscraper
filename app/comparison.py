from __future__ import annotations

import csv
import difflib
import hashlib
import re
import threading
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

from app import settings
from app.comparison_decisions import (
    get_decision_summary,
    get_decisions_map,
    get_relationships_map,
)


_CACHE_LOCK = threading.RLock()
_CACHE_KEY: tuple[Any, ...] | None = None
_CACHE_PAYLOAD: dict[str, Any] | None = None

_STATUS_ORDER = {
    "update_available": 0,
    "version_review": 1,
    "site_version_missing": 2,
    "source_version_missing": 3,
    "site_ahead": 4,
    "updated": 5,
    "site_only": 6,
    "new_source": 7,
}

_STATUS_LABELS = {
    "update_available": "Atualização disponível",
    "version_review": "Revisar versão",
    "site_version_missing": "Versão ausente no site",
    "source_version_missing": "Versão ausente no Ultrapack",
    "site_ahead": "Site aparentemente mais novo",
    "updated": "Atualizado",
    "site_only": "Somente no PluginTema",
    "new_source": "Novo no Ultrapack",
}


def _normalize_spaces(value: Any) -> str:
    if value in (None, ""):
        return ""
    return " ".join(str(value).split()).strip()


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def normalize_name_key(value: Any) -> str:
    text = _strip_accents(_normalize_spaces(value).lower())
    text = text.replace("&", " and ")
    text = re.sub(r"^\s*(themeforest|codecanyon)\s+", "", text)
    text = re.sub(r"\bwordpress\b", " ", text)
    text = re.sub(r"\bwoocommerce\b", " ", text)
    text = re.sub(r"\bthemes?\b", " ", text)
    text = re.sub(r"\bwp\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def normalize_url_key(value: Any) -> str:
    text = _normalize_spaces(value).lower()
    if not text:
        return ""

    if not re.match(r"^[a-z][a-z0-9+.-]*://", text):
        text = "https://" + text.lstrip("/")

    try:
        parsed = urlparse(text)
    except Exception:
        return ""

    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]

    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    path = path.rstrip("/")
    return f"{host}{path}"

def build_site_product_key(
    site_id: Any = "",
    site_name: Any = "",
    site_official_url: Any = "",
) -> str:
    normalized_id = _normalize_spaces(site_id)

    if normalized_id:
        return "site:id:" + normalized_id

    normalized_url = normalize_url_key(site_official_url)

    if normalized_url:
        return "site:url:" + normalized_url

    normalized_name = normalize_name_key(site_name)

    if normalized_name:
        return "site:name:" + normalized_name

    return ""


def build_source_product_key(
    source_name: Any = "",
    source_product_url: Any = "",
    source_official_url: Any = "",
) -> str:
    normalized_product_url = normalize_url_key(
        source_product_url
    )

    if normalized_product_url:
        return "source:product_url:" + normalized_product_url

    normalized_official_url = normalize_url_key(
        source_official_url
    )

    if normalized_official_url:
        return "source:official_url:" + normalized_official_url

    normalized_name = normalize_name_key(source_name)

    if normalized_name:
        return "source:name:" + normalized_name

    return ""

def extract_url_domain(value: Any) -> str:
    text = _normalize_spaces(value).lower()
    if not text:
        return ""

    if not re.match(r"^[a-z][a-z0-9+.-]*://", text):
        text = "https://" + text.lstrip("/")

    try:
        parsed = urlparse(text)
    except Exception:
        return ""

    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]

    return host


def extract_url_slug(value: Any) -> str:
    text = _normalize_spaces(value).lower()
    if not text:
        return ""

    if not re.match(r"^[a-z][a-z0-9+.-]*://", text):
        text = "https://" + text.lstrip("/")

    try:
        parsed = urlparse(text)
    except Exception:
        return ""

    path_parts = [
        part
        for part in (parsed.path or "").strip("/").split("/")
        if part
    ]

    if not path_parts:
        return ""

    slug = path_parts[-1]
    slug = re.sub(r"\.(html?|php)$", "", slug)
    slug = re.sub(r"[^a-z0-9]+", " ", slug)

    return " ".join(slug.split())


def name_tokens(value: Any) -> set[str]:
    normalized = normalize_name_key(value)
    if not normalized:
        return set()

    ignored_tokens = {
        "and",
        "for",
        "the",
        "plugin",
        "plugins",
        "theme",
        "themes",
        "wordpress",
        "woocommerce",
    }

    return {
        token
        for token in normalized.split()
        if len(token) >= 2 and token not in ignored_tokens
    }


def category_tokens(value: Any) -> set[str]:
    text = _strip_accents(_normalize_spaces(value).lower())
    text = re.sub(r"[^a-z0-9]+", " ", text)

    ignored_tokens = {
        "and",
        "de",
        "da",
        "do",
        "das",
        "dos",
        "para",
        "wordpress",
        "woocommerce",
    }

    return {
        token
        for token in text.split()
        if len(token) >= 2 and token not in ignored_tokens
    }

def calculate_match_score(
    site: Mapping[str, Any],
    source: Mapping[str, Any],
) -> dict[str, Any]:
    score = 0
    favorable_signals: list[str] = []
    conflicting_signals: list[str] = []

    site_url_key = _normalize_spaces(site.get("url_key"))
    source_url_key = _normalize_spaces(source.get("url_key"))

    site_domain = _normalize_spaces(site.get("url_domain"))
    source_domain = _normalize_spaces(source.get("url_domain"))

    site_slug = _normalize_spaces(site.get("url_slug"))
    source_slug = _normalize_spaces(source.get("url_slug"))

    site_name_key = _normalize_spaces(site.get("name_key"))
    source_name_key = _normalize_spaces(source.get("name_key"))

    site_name_tokens = set(site.get("name_tokens") or set())
    source_name_tokens = set(source.get("name_tokens") or set())

    site_category_tokens = set(
        site.get("category_tokens") or set()
    )
    source_category_tokens = set(
        source.get("category_tokens") or set()
    )

    if (
        site_url_key
        and source_url_key
        and site_url_key == source_url_key
    ):
        score += 100
        favorable_signals.append("URL oficial idêntica")

    if (
        site_slug
        and source_slug
        and site_slug == source_slug
    ):
        score += 45
        favorable_signals.append("Slug da URL idêntico")

    if (
        site_name_key
        and source_name_key
        and site_name_key == source_name_key
    ):
        score += 40
        favorable_signals.append("Nome normalizado idêntico")

    name_similarity = 0.0

    if site_name_key and source_name_key:
        name_similarity = difflib.SequenceMatcher(
            None,
            site_name_key,
            source_name_key,
        ).ratio()

        if name_similarity >= 0.90:
            score += 30
            favorable_signals.append(
                f"Nomes muito semelhantes ({name_similarity:.0%})"
            )
        elif name_similarity >= 0.75:
            score += 15
            favorable_signals.append(
                f"Nomes semelhantes ({name_similarity:.0%})"
            )
        elif name_similarity < 0.35:
            score -= 40
            conflicting_signals.append(
                f"Nomes muito diferentes ({name_similarity:.0%})"
            )

    shared_name_tokens = (
        site_name_tokens & source_name_tokens
    )

    all_name_tokens = (
        site_name_tokens | source_name_tokens
    )

    token_similarity = (
        len(shared_name_tokens) / len(all_name_tokens)
        if all_name_tokens
        else 0.0
    )

    if token_similarity >= 0.75:
        score += 25
        favorable_signals.append(
            "Maioria dos tokens importantes do nome coincide"
        )
    elif token_similarity >= 0.50:
        score += 15
        favorable_signals.append(
            "Parte relevante dos tokens do nome coincide"
        )
    elif (
        site_name_tokens
        and source_name_tokens
        and not shared_name_tokens
    ):
        score -= 25
        conflicting_signals.append(
            "Nenhum token importante do nome coincide"
        )

    if (
        site_domain
        and source_domain
        and site_domain == source_domain
    ):
        score += 10
        favorable_signals.append("Domínio oficial idêntico")

    shared_category_tokens = (
        site_category_tokens & source_category_tokens
    )

    if shared_category_tokens:
        score += 10
        favorable_signals.append(
            "Categorias possuem termos compatíveis"
        )
    elif site_category_tokens and source_category_tokens:
        score -= 15
        conflicting_signals.append(
            "Categorias aparentemente incompatíveis"
        )

    site_product_type = _normalize_spaces(
        site.get("site_product_type")
    ).lower()

    source_product_type = _normalize_spaces(
        source.get("source_product_type")
    ).lower()

    if (
        site_product_type
        and source_product_type
        and site_product_type == source_product_type
    ):
        score += 10
        favorable_signals.append("Tipo de produto compatível")

    score = max(0, min(score, 100))

    if score >= 90:
        level = "exact"
        level_label = "Correspondência exata"
    elif score >= 70:
        level = "probable"
        level_label = "Provável correspondência"
    elif score >= 45:
        level = "ambiguous"
        level_label = "Correspondência ambígua"
    else:
        level = "none"
        level_label = "Sem correspondência"

    return {
        "score": score,
        "level": level,
        "level_label": level_label,
        "name_similarity": round(name_similarity, 4),
        "token_similarity": round(token_similarity, 4),
        "favorable_signals": favorable_signals,
        "conflicting_signals": conflicting_signals,
    }


def build_match_candidates(
    site: Mapping[str, Any],
    source_rows: list[dict[str, Any]],
    *,
    excluded_source_indexes: set[int] | None = None,
    candidate_source_indexes: set[int] | None = None,
    limit: int = 3,
    minimum_score: int = 45,
) -> list[dict[str, Any]]:
    excluded_indexes = excluded_source_indexes or set()
    candidates: list[dict[str, Any]] = []

    if candidate_source_indexes is None:
        source_indexes = range(len(source_rows))
    else:
        source_indexes = sorted(candidate_source_indexes)

    site_name_key = _normalize_spaces(
        site.get("name_key")
    )

    site_name_tokens = set(
        site.get("name_tokens") or set()
    )

    site_domain = _normalize_spaces(
        site.get("url_domain")
    )

    site_slug = _normalize_spaces(
        site.get("url_slug")
    )

    for source_index in source_indexes:
        if source_index in excluded_indexes:
            continue

        if source_index < 0 or source_index >= len(source_rows):
            continue

        source = source_rows[source_index]

        source_name_key = _normalize_spaces(
            source.get("name_key")
        )

        source_name_tokens = set(
            source.get("name_tokens") or set()
        )

        source_domain = _normalize_spaces(
            source.get("url_domain")
        )

        source_slug = _normalize_spaces(
            source.get("url_slug")
        )

        shared_tokens = (
            site_name_tokens & source_name_tokens
        )

        same_domain = bool(
            site_domain
            and source_domain
            and site_domain == source_domain
        )

        same_slug = bool(
            site_slug
            and source_slug
            and site_slug == source_slug
        )

        similar_prefix = bool(
            len(site_name_key) >= 4
            and len(source_name_key) >= 4
            and site_name_key[:4] == source_name_key[:4]
        )

        if not (
            shared_tokens
            or same_domain
            or same_slug
            or similar_prefix
        ):
            continue

        match = calculate_match_score(
            site,
            source,
        )

        score = int(match.get("score", 0))

        if score < minimum_score:
            continue

        candidates.append(
            {
                "source_index": source_index,
                "source_product_key": source.get(
                    "source_product_key",
                    "",
                ),
                "source_name": source.get(
                    "source_name",
                    "",
                ),
                "source_version": source.get(
                    "source_version",
                    "",
                ),
                "source_product_url": source.get(
                    "source_product_url",
                    "",
                ),
                "source_official_url": source.get(
                    "source_official_url",
                    "",
                ),
                "source_category": source.get(
                    "source_category",
                    "",
                ),
                "match_score": score,
                "match_level": match.get(
                    "level",
                    "none",
                ),
                "match_level_label": match.get(
                    "level_label",
                    "Sem correspondência",
                ),
                "name_similarity": match.get(
                    "name_similarity",
                    0,
                ),
                "token_similarity": match.get(
                    "token_similarity",
                    0,
                ),
                "favorable_signals": list(
                    match.get(
                        "favorable_signals",
                        [],
                    )
                ),
                "conflicting_signals": list(
                    match.get(
                        "conflicting_signals",
                        [],
                    )
                ),
            }
        )

    candidates.sort(
        key=lambda candidate: (
            -int(candidate.get("match_score", 0)),
            -float(candidate.get("name_similarity", 0)),
            _normalize_spaces(
                candidate.get("source_name")
            ).lower(),
        )
    )

    resolved_limit = max(
        1,
        int(limit or 3),
    )

    return candidates[:resolved_limit]


def build_comparison_item_id(
    site: Mapping[str, Any] = None,
    source: Mapping[str, Any] = None,
) -> str:
    site = site or {}
    source = source or {}

    identity_parts = [
        "site_id=" + _normalize_spaces(site.get("site_id")),
        "site_name=" + normalize_name_key(site.get("site_name")),
        "site_url=" + normalize_url_key(site.get("site_official_url")),
        "source_name=" + normalize_name_key(source.get("source_name")),
        "source_official_url=" + normalize_url_key(
            source.get("source_official_url")
        ),
        "source_product_url=" + normalize_url_key(
            source.get("source_product_url")
        ),
    ]

    raw_identity = chr(124).join(identity_parts)
    digest = hashlib.sha256(
        raw_identity.encode("utf-8")
    ).hexdigest()[:24]

    return "comparison_" + digest


def clean_version(value: Any) -> str:
    text = _normalize_spaces(value)
    if not text:
        return ""

    formula = re.fullmatch(r'=\"(.*)\"', text)
    if formula:
        text = formula.group(1).replace('""', '"')

    if text.startswith("'"):
        text = text[1:]

    text = re.sub(r"^\s*(vers[aã]o|version|ver\.?)[\s:#-]*", "", text, flags=re.IGNORECASE)
    text = text.replace(",", ".")
    return re.sub(r"\s+", "", text).strip(" .-_")


def is_suspicious_spreadsheet_version(value: str) -> bool:
    """
    Identifica versões que provavelmente foram convertidas em datas
    pelo Excel, Google Sheets ou outro editor de planilhas.

    Exemplos suspeitos:
    - 1.6.2006
    - 2.2.2008
    - 2003-03-02
    - 2003-03-0200:00:00
    - 2026-07-09 00:00:00
    - 03/02/2003
    """
    text = clean_version(value)
    if not text:
        return False

    suspicious_patterns = (
        # Ex.: 1.6.2006 ou 2.2.2008
        r"\d+(?:\.\d+)+\.(?:19|20)\d{2}",

        # Ex.: 2003-03-02 ou 2003-03-0200:00:00
        r"(?:19|20)\d{2}[-/.]\d{1,2}[-/.]\d{1,2}(?:\d{1,2}:\d{2}:\d{2})?",

        # Ex.: 03/02/2003, 03-02-2003 ou 03.02.2003
        r"\d{1,2}[-/.]\d{1,2}[-/.](?:19|20)\d{2}(?:\d{1,2}:\d{2}:\d{2})?",

        # Ex.: 20030302000000
        r"(?:19|20)\d{12}",
    )

    return any(
        re.fullmatch(pattern, text)
        for pattern in suspicious_patterns
    )

def describe_version_quality(value: Any) -> dict[str, Any]:
    version = clean_version(value)

    if not version:
        return {
            "version": "",
            "valid_for_comparison": False,
            "quality": "missing",
            "reason": "Versão não informada.",
        }

    if is_suspicious_spreadsheet_version(version):
        return {
            "version": version,
            "valid_for_comparison": False,
            "quality": "spreadsheet_date",
            "reason": (
                "O valor tem formato de data e provavelmente foi "
                "convertido automaticamente por uma planilha."
            ),
        }

    if not re.search(r"\d", version):
        return {
            "version": version,
            "valid_for_comparison": False,
            "quality": "no_numeric_component",
            "reason": "A versão não possui nenhum componente numérico.",
        }

    return {
        "version": version,
        "valid_for_comparison": True,
        "quality": "valid",
        "reason": "Versão disponível para comparação.",
    }


def _version_tokens(value: str) -> list[tuple[int, Any]]:
    tokens: list[tuple[int, Any]] = []
    for raw in re.findall(r"\d+|[a-zA-Z]+", value or ""):
        if raw.isdigit():
            tokens.append((1, int(raw)))
        else:
            tokens.append((0, raw.lower()))
    return tokens


def compare_versions(source_version: str, site_version: str) -> int | None:
    source = clean_version(source_version)
    site = clean_version(site_version)
    if not source or not site:
        return None

    if is_suspicious_spreadsheet_version(source) or is_suspicious_spreadsheet_version(site):
        return None

    left = _version_tokens(source)
    right = _version_tokens(site)
    if not left or not right:
        return None

    max_len = max(len(left), len(right))
    left += [(1, 0)] * (max_len - len(left))
    right += [(1, 0)] * (max_len - len(right))

    for l_token, r_token in zip(left, right):
        if l_token == r_token:
            continue

        # Um número é tratado como versão estável e uma palavra como qualificador.
        if l_token[0] != r_token[0]:
            return 1 if l_token[0] > r_token[0] else -1

        return 1 if l_token[1] > r_token[1] else -1

    return 0


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        rows: list[dict[str, str]] = []
        for raw_row in reader:
            row: dict[str, str] = {}
            for raw_key, raw_value in dict(raw_row or {}).items():
                key = str(raw_key or "").lstrip("\t\ufeff").strip()
                row[key] = "" if raw_value is None else str(raw_value)
            rows.append(row)
        return rows



def _normalize_source_rows(
    rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []

    for index, row in enumerate(rows):
        name = _normalize_spaces(
            row.get("nome_produto")
        )

        if not name:
            continue

        official_url = _normalize_spaces(
            row.get("pagina_oficial")
        )

        category = _normalize_spaces(
            row.get("categoria_nome")
        )

        source_product_url = _normalize_spaces(
            row.get("link_produto")
        )

        normalized.append(
            {
                "source_index": index,
                "source_product_key": build_source_product_key(
                    name,
                    source_product_url,
                    official_url,
                ),
                "source_name": name,
                "source_version": clean_version(
                    row.get("versao_produto")
                ),
                "source_product_url": source_product_url,
                "source_official_url": official_url,
                "source_category": category,

                "name_key": normalize_name_key(name),
                "name_tokens": name_tokens(name),

                "url_key": normalize_url_key(
                    official_url
                ),
                "url_domain": extract_url_domain(
                    official_url
                ),
                "url_slug": extract_url_slug(
                    official_url
                ),

                "category_tokens": category_tokens(
                    category
                ),
            }
        )

    return normalized

def _normalize_site_rows(
    rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []

    for index, row in enumerate(rows):
        is_woocommerce_export = (
            "Nome" in row
            or "Metadado: pt_versao" in row
        )

        if is_woocommerce_export:
            product_type = _normalize_spaces(
                row.get("Tipo")
            ).lower()

            # O export do WooCommerce possui uma linha principal
            # e linhas de variações. Compararemos apenas o produto principal.
            if "variation" in product_type:
                continue

            name = _normalize_spaces(row.get("Nome"))
            site_id = _normalize_spaces(row.get("ID"))
            site_version = clean_version(
                row.get("Metadado: pt_versao")
            )
            official_url = _normalize_spaces(
                row.get("Metadado: site_oficial")
            )
            product_url = _normalize_spaces(row.get("URL"))
            categories = _normalize_spaces(
                row.get("Categorias")
            )

        else:
            # Também aceita o formato padrão de catálogo do CrapScraper.
            product_type = _normalize_spaces(
                row.get("tipo")
            ).lower()

            name = _normalize_spaces(
                row.get("nome_produto")
            )
            site_id = ""
            site_version = clean_version(
                row.get("versao_produto")
            )
            official_url = _normalize_spaces(
                row.get("pagina_oficial")
            )
            product_url = _normalize_spaces(
                row.get("url_produto") or row.get("produto_url") or row.get("URL")
            )
            categories = _normalize_spaces(
                row.get("categoria_nome")
            )

        if not name:
            continue

        normalized.append(
            {
                "site_index": index,
                "site_product_key": build_site_product_key(
                    site_id,
                    name,
                    official_url,
                ),
                "site_id": site_id,
                "site_name": name,
                "site_version": site_version,
                "site_product_url": product_url,
                "site_official_url": official_url,
                "site_categories": categories,
                "site_product_type": product_type,

                "name_key": normalize_name_key(name),
                "name_tokens": name_tokens(name),

                "url_key": normalize_url_key(
                    official_url
                ),
                "url_domain": extract_url_domain(
                    official_url
                ),
                "url_slug": extract_url_slug(
                    official_url
                ),

                "category_tokens": category_tokens(
                    categories
                ),
            }
        )

    return normalized


def _build_unique_index(items: list[dict[str, Any]], field_name: str) -> dict[str, int]:
    buckets: dict[str, list[int]] = defaultdict(list)
    for index, item in enumerate(items):
        key = _normalize_spaces(item.get(field_name))
        if key:
            buckets[key].append(index)
    return {key: indexes[0] for key, indexes in buckets.items() if len(indexes) == 1}


def _build_status(
    source_version: str,
    site_version: str,
) -> tuple[str, str, int | None]:
    source_info = describe_version_quality(source_version)
    site_info = describe_version_quality(site_version)

    clean_source = source_info["version"]
    clean_site = site_info["version"]

    if not clean_source and not clean_site:
        return (
            "version_review",
            "Ultrapack e PluginTema estão sem versão informada.",
            None,
        )

    if not clean_site:
        return (
            "site_version_missing",
            "O produto existe no site, mas não possui versão cadastrada.",
            None,
        )

    if not clean_source:
        return (
            "source_version_missing",
            "O produto existe no Ultrapack, mas a versão não foi informada.",
            None,
        )

    if not site_info["valid_for_comparison"]:
        return (
            "version_review",
            f"Versão do site não confiável: {site_info['reason']}",
            None,
        )

    if not source_info["valid_for_comparison"]:
        return (
            "version_review",
            f"Versão do Ultrapack não confiável: {source_info['reason']}",
            None,
        )

    if clean_source == clean_site:
        return (
            "updated",
            "As versões do Ultrapack e do site são iguais.",
            0,
        )

    comparison = compare_versions(
        clean_source,
        clean_site,
    )

    if comparison is None:
        return (
            "version_review",
            "Não foi possível comparar as versões com segurança.",
            None,
        )

    if comparison > 0:
        return (
            "update_available",
            (
                f"O Ultrapack possui a versão {clean_source}, "
                f"mais recente que a versão {clean_site} do site."
            ),
            comparison,
        )

    if comparison < 0:
        return (
            "site_ahead",
            (
                f"O site possui a versão {clean_site}, aparentemente "
                f"mais recente que a versão {clean_source} do Ultrapack."
            ),
            comparison,
        )

    return (
        "updated",
        "As versões são equivalentes após normalização.",
        0,
    )

def _recommended_action_for_status(status: str) -> tuple[str, str]:
    recommendations = {
        "update_available": (
            "review_and_approve_update",
            "Revisar e aprovar atualização.",
        ),
        "updated": (
            "no_action",
            "Nenhuma ação necessária.",
        ),
        "site_version_missing": (
            "register_site_version",
            "Conferir o produto e cadastrar a versão no site.",
        ),
        "source_version_missing": (
            "manual_review",
            "Revisar manualmente a versão no Ultrapack.",
        ),
        "version_review": (
            "fix_version_before_decision",
            "Corrigir ou confirmar a versão antes de decidir.",
        ),
        "site_ahead": (
            "do_not_update_automatically",
            "Não atualizar automaticamente; revisar a divergência.",
        ),
        "new_source": (
            "search_approximate_match",
            "Procurar uma correspondência aproximada antes de cadastrar.",
        ),
        "site_only": (
            "check_removed_or_renamed",
            "Verificar se o Ultrapack removeu ou renomeou o produto.",
        ),
    }

    return recommendations.get(
        status,
        (
            "manual_review",
            "Revisar manualmente antes de executar qualquer ação.",
        ),
    )


def _matched_row(
    site: dict[str, Any],
    source: dict[str, Any],
    method: str,
) -> dict[str, Any]:
    status, status_reason, version_comparison = _build_status(
        source["source_version"],
        site["site_version"],
    )

    recommended_action, recommended_action_label = (
        _recommended_action_for_status(status)
    )

    match_details = calculate_match_score(
        site,
        source,
    )

    match_labels = {
        "official_url": "URL oficial idêntica",
        "normalized_name": "Nome normalizado idêntico",
        "manual_confirmed": "Confirmada manualmente",
    }

    source_version_quality = describe_version_quality(
        source["source_version"]
    )
    site_version_quality = describe_version_quality(
        site["site_version"]
    )

    return {
        "status": status,
        "status_label": _STATUS_LABELS[status],
        "status_reason": status_reason,
        "version_comparison": version_comparison,
        "recommended_action": recommended_action,
        "recommended_action_label": recommended_action_label,

        "match_method": method,
        "match_method_label": match_labels.get(
            method,
            "Correspondência não identificada",
        ),

                "relationship_state": (
            "manual_confirmed"
            if method == "manual_confirmed"
            else "safe_auto"
        ),

        "match_confidence": (
            "high"
            if method in {
                "official_url",
                "manual_confirmed",
            }
            else "medium"
        ),

        "match_score": int(
            match_details.get("score", 0)
        ),
        "match_level": match_details.get(
            "level",
            "none",
        ),
        "match_level_label": match_details.get(
            "level_label",
            "Sem correspondência",
        ),
        "match_name_similarity": match_details.get(
            "name_similarity",
            0,
        ),
        "match_token_similarity": match_details.get(
            "token_similarity",
            0,
        ),
        "match_favorable_signals": list(
            match_details.get(
                "favorable_signals",
                [],
            )
        ),
        "match_conflicting_signals": list(
            match_details.get(
                "conflicting_signals",
                [],
            )
        ),
     "match_candidates": [],
    "match_candidate_count": 0,

    "site_product_key": site.get(
        "site_product_key",
        "",
    ),
    "source_product_key": source.get(
        "source_product_key",
        "",
    ),

    "site_id": site["site_id"],
        "site_name": site["site_name"],
        "site_version": site["site_version"],
        "site_version_quality": site_version_quality["quality"],
        "site_version_reason": site_version_quality["reason"],
        "site_product_url": site.get("site_product_url", ""),
        "site_official_url": site["site_official_url"],
        "site_categories": site["site_categories"],
        "site_product_type": site.get(
            "site_product_type",
            "",
        ),

        "source_name": source["source_name"],
        "source_version": source["source_version"],
        "source_version_quality": source_version_quality["quality"],
        "source_version_reason": source_version_quality["reason"],
        "source_product_url": source["source_product_url"],
        "source_official_url": source["source_official_url"],
        "source_category": source["source_category"],
    }


def _build_full_comparison(
    source_path: Path,
    site_path: Path,
) -> dict[str, Any]:
    source_rows = _normalize_source_rows(
        _read_csv_rows(source_path)
    )
    site_rows = _normalize_site_rows(
        _read_csv_rows(site_path)
    )

    source_by_url = _build_unique_index(
        source_rows,
        "url_key",
    )
    source_by_name = _build_unique_index(
        source_rows,
        "name_key",
    )

    source_by_product_key = {
        str(
            source.get(
                "source_product_key",
                "",
            )
        ).strip(): source_index
        for source_index, source in enumerate(
            source_rows
        )
        if str(
            source.get(
                "source_product_key",
                "",
            )
        ).strip()
    }

    relationships_map = get_relationships_map()

    source_indexes_by_token: dict[
        str,
        set[int],
    ] = defaultdict(set)

    source_indexes_by_domain: dict[
        str,
        set[int],
    ] = defaultdict(set)

    source_indexes_by_slug: dict[
        str,
        set[int],
    ] = defaultdict(set)

    source_indexes_by_prefix: dict[
        str,
        set[int],
    ] = defaultdict(set)

    for source_index, source in enumerate(
        source_rows
    ):
        for token in set(
            source.get(
                "name_tokens"
            )
            or set()
        ):
            source_indexes_by_token[
                str(token)
            ].add(
                source_index
            )

        source_domain = _normalize_spaces(
            source.get(
                "url_domain"
            )
        )

        if source_domain:
            source_indexes_by_domain[
                source_domain
            ].add(
                source_index
            )

        source_slug = _normalize_spaces(
            source.get(
                "url_slug"
            )
        )

        if source_slug:
            source_indexes_by_slug[
                source_slug
            ].add(
                source_index
            )

        source_name_key = _normalize_spaces(
            source.get(
                "name_key"
            )
        )

        if len(source_name_key) >= 4:
            source_indexes_by_prefix[
                source_name_key[:4]
            ].add(
                source_index
            )

    matched_source_indexes: set[int] = set()

    result_rows: list[
        dict[str, Any]
    ] = []

    for site in site_rows:
        source_index: int | None = None
        method = ""

        site_product_key = str(
            site.get(
                "site_product_key",
                "",
            )
        ).strip()

        saved_relationships = (
            relationships_map.get(
                site_product_key,
                [],
            )
        )

        manual_confirmed_relationship = next(
            (
                relationship
                for relationship
                in saved_relationships
                if relationship.get(
                    "relationship_state"
                )
                == "manual_confirmed"
            ),
            None,
        )

        confirmed_not_in_source = any(
            relationship.get(
                "relationship_state"
            )
            == "confirmed_not_in_source"
            for relationship
            in saved_relationships
        )

        rejected_source_keys = {
            str(
                relationship.get(
                    "source_product_key",
                    "",
                )
            ).strip()
            for relationship
            in saved_relationships
            if (
                relationship.get(
                    "relationship_state"
                )
                == "manual_rejected"
                and str(
                    relationship.get(
                        "source_product_key",
                        "",
                    )
                ).strip()
            )
        }

        url_key = _normalize_spaces(
            site.get(
                "url_key"
            )
        )

        name_key = _normalize_spaces(
            site.get(
                "name_key"
            )
        )

        #
        # 1. Vínculo manual confirmado
        #
        if manual_confirmed_relationship:
            confirmed_source_key = str(
                manual_confirmed_relationship.get(
                    "source_product_key",
                    "",
                )
            ).strip()

            confirmed_source_index = (
                source_by_product_key.get(
                    confirmed_source_key
                )
            )

            if (
                confirmed_source_index
                is not None
                and confirmed_source_index
                not in matched_source_indexes
            ):
                source_index = (
                    confirmed_source_index
                )
                method = (
                    "manual_confirmed"
                )

        #
        # 2. Matching automático
        #
        if not confirmed_not_in_source:

            if (
                source_index is None
                and url_key
                and url_key
                in source_by_url
            ):
                candidate_index = (
                    source_by_url[
                        url_key
                    ]
                )

                candidate_source_key = str(
                    source_rows[
                        candidate_index
                    ].get(
                        "source_product_key",
                        "",
                    )
                ).strip()

                if (
                    candidate_index
                    not in matched_source_indexes
                    and candidate_source_key
                    not in rejected_source_keys
                ):
                    source_index = (
                        candidate_index
                    )
                    method = (
                        "official_url"
                    )

            if (
                source_index is None
                and name_key
                and name_key
                in source_by_name
            ):
                candidate_index = (
                    source_by_name[
                        name_key
                    ]
                )

                candidate_source_key = str(
                    source_rows[
                        candidate_index
                    ].get(
                        "source_product_key",
                        "",
                    )
                ).strip()

                if (
                    candidate_index
                    not in matched_source_indexes
                    and candidate_source_key
                    not in rejected_source_keys
                ):
                    source_index = (
                        candidate_index
                    )
                    method = (
                        "normalized_name"
                    )

        #
        # 3. Candidatos aproximados
        #
        match_candidates: list[
            dict[str, Any]
        ] = []

        best_candidate: (
            dict[str, Any] | None
        ) = None

        if (
            source_index is None
            and not confirmed_not_in_source
        ):
            candidate_source_indexes: (
                set[int]
            ) = set()

            for token in set(
                site.get(
                    "name_tokens"
                )
                or set()
            ):
                candidate_source_indexes.update(
                    source_indexes_by_token.get(
                        str(token),
                        set(),
                    )
                )

            site_domain = _normalize_spaces(
                site.get(
                    "url_domain"
                )
            )

            if site_domain:
                candidate_source_indexes.update(
                    source_indexes_by_domain.get(
                        site_domain,
                        set(),
                    )
                )

            site_slug = _normalize_spaces(
                site.get(
                    "url_slug"
                )
            )

            if site_slug:
                candidate_source_indexes.update(
                    source_indexes_by_slug.get(
                        site_slug,
                        set(),
                    )
                )

            site_name_key = _normalize_spaces(
                site.get(
                    "name_key"
                )
            )

            if len(site_name_key) >= 4:
                candidate_source_indexes.update(
                    source_indexes_by_prefix.get(
                        site_name_key[:4],
                        set(),
                    )
                )

            match_candidates = (
                build_match_candidates(
                    site,
                    source_rows,
                    excluded_source_indexes=(
                        matched_source_indexes
                    ),
                    candidate_source_indexes=(
                        candidate_source_indexes
                    ),
                    limit=3,
                    minimum_score=45,
                )
            )

            #
            # Não mostrar novamente
            # candidatos rejeitados
            #
            match_candidates = [
                candidate
                for candidate
                in match_candidates
                if str(
                    candidate.get(
                        "source_product_key",
                        "",
                    )
                ).strip()
                not in rejected_source_keys
            ]

            if match_candidates:
                best_candidate = (
                    match_candidates[0]
                )

        #
        # 4. Continua sem correspondência
        #
        if source_index is None:
            (
                recommended_action,
                recommended_action_label,
            ) = (
                _recommended_action_for_status(
                    "site_only"
                )
            )

            if confirmed_not_in_source:
                recommended_action = (
                    "confirmed_not_in_source"
                )

                recommended_action_label = (
                    "Ausência no Ultrapack "
                    "confirmada manualmente."
                )

            elif best_candidate:
                recommended_action = (
                    "review_approximate_candidate"
                )

                recommended_action_label = (
                    "Revisar o candidato "
                    "aproximado antes de decidir."
                )

            site_version_quality = (
                describe_version_quality(
                    site[
                        "site_version"
                    ]
                )
            )

            result_rows.append(
                {
                    "status": (
                        "site_only"
                    ),
                    "status_label": (
                        _STATUS_LABELS[
                            "site_only"
                        ]
                    ),
                    "status_reason": (
                        (
                            "Foi confirmado "
                            "manualmente que este "
                            "produto não está "
                            "presente no catálogo "
                            "do Ultrapack."
                        )
                        if confirmed_not_in_source
                        else (
                            (
                                "Nenhuma "
                                "correspondência "
                                "segura foi "
                                "confirmada, mas "
                                "foi localizado um "
                                "candidato "
                                "aproximado para "
                                "revisão."
                            )
                            if best_candidate
                            else (
                                "O produto foi "
                                "encontrado na "
                                "PluginTema, mas "
                                "nenhuma "
                                "correspondência "
                                "segura foi "
                                "localizada no "
                                "Ultrapack."
                            )
                        )
                    ),
                    "recommended_action": (
                        recommended_action
                    ),
                    "recommended_action_label": (
                        recommended_action_label
                    ),
                    "relationship_state": (
                        "confirmed_not_in_source"
                        if confirmed_not_in_source
                        else (
                            "candidate"
                            if best_candidate
                            else "pending_review"
                        )
                    ),
                    "match_method": (
                        "unmatched"
                    ),
                    "match_method_label": (
                        "Sem correspondência"
                    ),
                    "match_confidence": (
                        "none"
                    ),
                    "match_score": (
                        int(
                            best_candidate.get(
                                "match_score",
                                0,
                            )
                        )
                        if best_candidate
                        else 0
                    ),
                    "match_level": (
                        best_candidate.get(
                            "match_level",
                            "none",
                        )
                        if best_candidate
                        else "none"
                    ),
                    "match_level_label": (
                        best_candidate.get(
                            "match_level_label",
                            "Sem correspondência",
                        )
                        if best_candidate
                        else "Sem correspondência"
                    ),
                    "match_name_similarity": (
                        best_candidate.get(
                            "name_similarity",
                            0,
                        )
                        if best_candidate
                        else 0
                    ),
                    "match_token_similarity": (
                        best_candidate.get(
                            "token_similarity",
                            0,
                        )
                        if best_candidate
                        else 0
                    ),
                    "match_favorable_signals": (
                        list(
                            best_candidate.get(
                                "favorable_signals",
                                [],
                            )
                        )
                        if best_candidate
                        else []
                    ),
                    "match_conflicting_signals": (
                        list(
                            best_candidate.get(
                                "conflicting_signals",
                                [],
                            )
                        )
                        if best_candidate
                        else []
                    ),
                    "match_candidates": (
                        []
                        if confirmed_not_in_source
                        else match_candidates
                    ),
                    "match_candidate_count": (
                        0
                        if confirmed_not_in_source
                        else len(
                            match_candidates
                        )
                    ),
                    "site_product_key": (
                        site_product_key
                    ),
                    "source_product_key": "",
                    "site_id": (
                        site["site_id"]
                    ),
                    "site_name": (
                        site["site_name"]
                    ),
                    "site_version": (
                        site[
                            "site_version"
                        ]
                    ),
                    "site_version_quality": (
                        site_version_quality[
                            "quality"
                        ]
                    ),
                    "site_version_reason": (
                        site_version_quality[
                            "reason"
                        ]
                    ),
                    "site_official_url": (
                        site[
                            "site_official_url"
                        ]
                    ),
                    "site_product_url": site.get("site_product_url", ""),
                    "site_categories": (
                        site[
                            "site_categories"
                        ]
                    ),
                    "site_product_type": (
                        site.get(
                            "site_product_type",
                            "",
                        )
                    ),
                    "source_name": "",
                    "source_version": "",
                    "source_version_quality": (
                        "missing"
                    ),
                    "source_version_reason": (
                        "Não existe produto do "
                        "Ultrapack associado "
                        "nesta comparação."
                    ),
                    "source_product_url": "",
                    "source_official_url": "",
                    "source_category": "",
                    "version_comparison": None,
                }
            )

            continue

        #
        # 5. Correspondência encontrada
        #
        matched_source_indexes.add(
            source_index
        )

        result_rows.append(
            _matched_row(
                site,
                source_rows[
                    source_index
                ],
                method,
            )
        )

    #
    # 6. Itens somente no Ultrapack
    #
    for source_index, source in enumerate(
        source_rows
    ):
        if (
            source_index
            in matched_source_indexes
        ):
            continue

        (
            recommended_action,
            recommended_action_label,
        ) = (
            _recommended_action_for_status(
                "new_source"
            )
        )

        source_version_quality = (
            describe_version_quality(
                source[
                    "source_version"
                ]
            )
        )

        result_rows.append(
            {
                "status": (
                    "new_source"
                ),
                "status_label": (
                    _STATUS_LABELS[
                        "new_source"
                    ]
                ),
                "status_reason": (
                    "O produto foi encontrado "
                    "no Ultrapack, mas nenhuma "
                    "correspondência segura foi "
                    "localizada na PluginTema."
                ),
                "recommended_action": (
                    recommended_action
                ),
                "recommended_action_label": (
                    recommended_action_label
                ),
                "relationship_state": (
                    "pending_review"
                ),
                "match_method": (
                    "unmatched"
                ),
                "match_method_label": (
                    "Sem correspondência"
                ),
                "match_confidence": (
                    "none"
                ),
                "match_score": 0,
                "match_level": "none",
                "match_level_label": (
                    "Sem correspondência"
                ),
                "match_name_similarity": 0,
                "match_token_similarity": 0,
                "match_favorable_signals": [],
                "match_conflicting_signals": [],
                "match_candidates": [],
                "match_candidate_count": 0,
                "site_product_key": "",
                "source_product_key": (
                    source.get(
                        "source_product_key",
                        "",
                    )
                ),
                "site_id": "",
                "site_name": "",
                "site_version": "",
                "site_version_quality": (
                    "missing"
                ),
                "site_version_reason": (
                    "Não existe produto da "
                    "PluginTema associado "
                    "nesta comparação."
                ),
                "site_official_url": "",
                "site_product_url": "",
                "site_categories": "",
                "site_product_type": "",
                "source_name": (
                    source[
                        "source_name"
                    ]
                ),
                "source_version": (
                    source[
                        "source_version"
                    ]
                ),
                "source_version_quality": (
                    source_version_quality[
                        "quality"
                    ]
                ),
                "source_version_reason": (
                    source_version_quality[
                        "reason"
                    ]
                ),
                "source_product_url": (
                    source[
                        "source_product_url"
                    ]
                ),
                "source_official_url": (
                    source[
                        "source_official_url"
                    ]
                ),
                "source_category": (
                    source[
                        "source_category"
                    ]
                ),
                "version_comparison": None,
            }
        )

    #
    # 7. IDs de comparação
    #
    for row in result_rows:
        row[
            "comparison_item_id"
        ] = build_comparison_item_id(
            row,
            row,
        )

    #
    # 8. Decisões salvas
    #
    decisions_map = get_decisions_map(
        [
            row.get(
                "comparison_item_id",
                "",
            )
            for row in result_rows
        ]
    )

    for row in result_rows:
        item_id = str(
            row.get(
                "comparison_item_id",
                "",
            )
        )

        saved_decision = (
            decisions_map.get(
                item_id,
                {},
            )
        )

        row["decision"] = (
            saved_decision.get(
                "decision",
                "pending",
            )
        )

        row["decision_label"] = (
            saved_decision.get(
                "decision_label",
                "Pendente",
            )
        )

        row["decision_note"] = (
            saved_decision.get(
                "note",
                "",
            )
        )

        row["decision_operator"] = (
            saved_decision.get(
                "operator",
                "",
            )
        )

        row["decision_queue_type"] = (
            saved_decision.get(
                "queue_type",
                "",
            )
        )

        row["decision_updated_at"] = (
            saved_decision.get(
                "updated_at",
                "",
            )
        )

        row["has_saved_decision"] = bool(
            saved_decision
        )

    #
    # 9. Ordenação
    #
    result_rows.sort(
        key=lambda row: (
            _STATUS_ORDER.get(
                str(
                    row.get(
                        "status",
                        "",
                    )
                ),
                99,
            ),
            _normalize_spaces(
                row.get(
                    "site_name"
                )
                or row.get(
                    "source_name"
                )
            ).lower(),
        )
    )

    #
    # 10. Contagens
    #
    counts: dict[str, int] = {
        status: 0
        for status
        in _STATUS_LABELS
    }

    for row in result_rows:
        row_status = str(
            row.get(
                "status",
                "",
            )
        )

        counts[row_status] = (
            counts.get(
                row_status,
                0,
            )
            + 1
        )

    matched_count = len(
        matched_source_indexes
    )

    matched_status_total = sum(
        counts.get(
            status,
            0,
        )
        for status in (
            "update_available",
            "updated",
            "version_review",
            "site_version_missing",
            "source_version_missing",
            "site_ahead",
        )
    )

    source_reconciled_total = (
        matched_count
        + counts.get(
            "new_source",
            0,
        )
    )

    site_reconciled_total = (
        matched_count
        + counts.get(
            "site_only",
            0,
        )
    )

    match_method_total = sum(
        1
        for row in result_rows
        if row.get(
            "match_method"
        )
        in {
            "official_url",
            "normalized_name",
            "manual_confirmed",
        }
    )

    reconciliation = {
        "matched_status_total": (
            matched_status_total
        ),
        "matched_total": (
            matched_count
        ),
        "matched_ok": (
            matched_status_total
            == matched_count
        ),
        "source_reconciled_total": (
            source_reconciled_total
        ),
        "source_total": (
            len(source_rows)
        ),
        "source_ok": (
            source_reconciled_total
            == len(source_rows)
        ),
        "site_reconciled_total": (
            site_reconciled_total
        ),
        "site_total": (
            len(site_rows)
        ),
        "site_ok": (
            site_reconciled_total
            == len(site_rows)
        ),
        "match_method_total": (
            match_method_total
        ),
        "match_method_ok": (
            match_method_total
            == matched_count
        ),
    }

    #
    # 11. Diagnóstico de versões
    #
    suspicious_site_versions = sum(
        1
        for item in site_rows
        if is_suspicious_spreadsheet_version(
            item.get(
                "site_version",
                "",
            )
        )
    )

    suspicious_source_versions = sum(
        1
        for item in source_rows
        if is_suspicious_spreadsheet_version(
            item.get(
                "source_version",
                "",
            )
        )
    )

    missing_site_versions = sum(
        1
        for item in site_rows
        if not clean_version(
            item.get(
                "site_version",
                "",
            )
        )
    )

    missing_source_versions = sum(
        1
        for item in source_rows
        if not clean_version(
            item.get(
                "source_version",
                "",
            )
        )
    )

    matched_rows = [
        row
        for row in result_rows
        if row.get(
            "status"
        )
        not in {
            "site_only",
            "new_source",
        }
    ]

    site_only_rows = [
        row
        for row in result_rows
        if row.get(
            "status"
        )
        == "site_only"
    ]

    new_source_rows = [
        row
        for row in result_rows
        if row.get(
            "status"
        )
        == "new_source"
    ]

    version_quality_breakdown = {
        "matched_site_suspicious": sum(
            1
            for row in matched_rows
            if row.get(
                "site_version_quality"
            )
            == "spreadsheet_date"
        ),
        "matched_source_suspicious": sum(
            1
            for row in matched_rows
            if row.get(
                "source_version_quality"
            )
            == "spreadsheet_date"
        ),
        "site_only_suspicious": sum(
            1
            for row in site_only_rows
            if row.get(
                "site_version_quality"
            )
            == "spreadsheet_date"
        ),
        "new_source_suspicious": sum(
            1
            for row in new_source_rows
            if row.get(
                "source_version_quality"
            )
            == "spreadsheet_date"
        ),
        "matched_site_missing": sum(
            1
            for row in matched_rows
            if row.get(
                "site_version_quality"
            )
            == "missing"
        ),
        "matched_source_missing": sum(
            1
            for row in matched_rows
            if row.get(
                "source_version_quality"
            )
            == "missing"
        ),
        "site_only_missing": sum(
            1
            for row in site_only_rows
            if row.get(
                "site_version_quality"
            )
            == "missing"
        ),
        "new_source_missing": sum(
            1
            for row in new_source_rows
            if row.get(
                "source_version_quality"
            )
            == "missing"
        ),
    }

    #
    # 12. Candidatos disputados
    #
    candidate_usage: dict[
        int,
        list[dict[str, Any]],
    ] = defaultdict(list)

    for row in site_only_rows:
        for candidate in row.get(
            "match_candidates",
            [],
        ):
            candidate_source_index = (
                candidate.get(
                    "source_index"
                )
            )

            if (
                candidate_source_index
                is None
            ):
                continue

            candidate_usage[
                int(
                    candidate_source_index
                )
            ].append(
                row
            )

    disputed_source_indexes = {
        source_index
        for (
            source_index,
            linked_rows,
        )
        in candidate_usage.items()
        if len(
            linked_rows
        )
        > 1
    }

    for row in site_only_rows:
        disputed_count = 0

        for candidate in row.get(
            "match_candidates",
            [],
        ):
            candidate_source_index = (
                candidate.get(
                    "source_index"
                )
            )

            is_disputed = (
                candidate_source_index
                is not None
                and int(
                    candidate_source_index
                )
                in disputed_source_indexes
            )

            candidate[
                "is_disputed"
            ] = is_disputed

            candidate[
                "disputed_count"
            ] = (
                len(
                    candidate_usage.get(
                        int(
                            candidate_source_index
                        ),
                        [],
                    )
                )
                if candidate_source_index
                is not None
                else 0
            )

            if is_disputed:
                disputed_count += 1

        row[
            "has_disputed_candidate"
        ] = (
            disputed_count > 0
        )

        row[
            "disputed_candidate_count"
        ] = disputed_count

        if disputed_count:
            signals = list(
                row.get(
                    "match_conflicting_signals",
                    [],
                )
            )

            warning = (
                "O mesmo candidato do "
                "Ultrapack também foi "
                "sugerido para outro "
                "produto da PluginTema."
            )

            if warning not in signals:
                signals.append(
                    warning
                )

            row[
                "match_conflicting_signals"
            ] = signals

    #
    # 13. Métricas de candidatos
    #
    candidate_metrics = {
        "site_only_total": (
            len(
                site_only_rows
            )
        ),
        "rows_with_disputed_candidates": sum(
            1
            for row in site_only_rows
            if row.get(
                "has_disputed_candidate"
            )
        ),
        "disputed_candidate_references": sum(
            int(
                row.get(
                    "disputed_candidate_count",
                    0,
                )
                or 0
            )
            for row
            in site_only_rows
        ),
        "rows_with_candidates": sum(
            1
            for row
            in site_only_rows
            if int(
                row.get(
                    "match_candidate_count",
                    0,
                )
                or 0
            )
            > 0
        ),
        "rows_without_candidates": sum(
            1
            for row
            in site_only_rows
            if int(
                row.get(
                    "match_candidate_count",
                    0,
                )
                or 0
            )
            == 0
        ),
        "exact_suggestions": sum(
            1
            for row
            in site_only_rows
            if row.get(
                "match_level"
            )
            == "exact"
        ),
        "probable_suggestions": sum(
            1
            for row
            in site_only_rows
            if row.get(
                "match_level"
            )
            == "probable"
        ),
        "ambiguous_suggestions": sum(
            1
            for row
            in site_only_rows
            if row.get(
                "match_level"
            )
            == "ambiguous"
        ),
        "total_candidates": sum(
            int(
                row.get(
                    "match_candidate_count",
                    0,
                )
                or 0
            )
            for row
            in site_only_rows
        ),
    }

    #
    # 14. Métodos de correspondência
    #
    match_method_counts = {
        "official_url": 0,
        "normalized_name": 0,
        "manual_confirmed": 0,
    }

    for row in result_rows:
        row_method = str(
            row.get(
                "match_method",
                "",
            )
        )

        if (
            row_method
            in match_method_counts
        ):
            match_method_counts[
                row_method
            ] += 1

    return {
        "source_file": (
            str(
                source_path
            )
        ),
        "site_file": (
            str(
                site_path
            )
        ),
        "source_total": (
            len(
                source_rows
            )
        ),
        "site_total": (
            len(
                site_rows
            )
        ),
        "matched_total": (
            matched_count
        ),
        "unmatched_site_total": (
            counts.get(
                "site_only",
                0,
            )
        ),
        "unmatched_source_total": (
            counts.get(
                "new_source",
                0,
            )
        ),
        "suspicious_site_versions": (
            suspicious_site_versions
        ),
        "suspicious_source_versions": (
            suspicious_source_versions
        ),
        "missing_site_versions": (
            missing_site_versions
        ),
        "missing_source_versions": (
            missing_source_versions
        ),
        "version_quality_breakdown": (
            version_quality_breakdown
        ),
        "candidate_metrics": (
            candidate_metrics
        ),
        "match_method_counts": (
            match_method_counts
        ),
        "reconciliation": (
            reconciliation
        ),
        "counts": (
            counts
        ),
        "status_labels": dict(
            _STATUS_LABELS
        ),
        "rows": (
            result_rows
        ),
    }


def _file_signature(
    path: Path,
) -> tuple[str, int, int]:
    stat = path.stat()

    return (
        str(path.resolve()),
        int(stat.st_mtime_ns),
        int(stat.st_size),
    )


def _get_cached_comparison(
    source_path: Path,
    site_path: Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    global _CACHE_KEY, _CACHE_PAYLOAD

    cache_key = (_file_signature(source_path), _file_signature(site_path))
    with _CACHE_LOCK:
        if not force and _CACHE_KEY == cache_key and isinstance(_CACHE_PAYLOAD, dict):
            return _CACHE_PAYLOAD

        payload = _build_full_comparison(source_path, site_path)
        _CACHE_KEY = cache_key
        _CACHE_PAYLOAD = payload
        return payload


def build_comparison_payload(
    *,
    source_path: str | Path | None = None,
    site_path: str | Path | None = None,
    status: str = "",
    query: str = "",

    decision: str = "",
    candidate_filter: str = "",
    candidate_count_min: int | None = None,
    candidate_count_max: int | None = None,
    score_min: int | None = None,
    score_max: int | None = None,
    page: int = 1,

    page_size: int | None = None,
    force: bool = False,
) -> dict[str, Any]:

    source_path = Path(
        source_path or settings.COMPARISON_ULTRAPACK_CSV_PATH
    )

    site_path = Path(
        site_path or settings.COMPARISON_PLUGINTEMA_CSV_PATH
    )

    full = _get_cached_comparison(source_path, site_path, force=force)

    normalized_status = _normalize_spaces(status).lower()
    normalized_query = _strip_accents(_normalize_spaces(query).lower())
    normalized_decision = _normalize_spaces(decision).lower()
    normalized_candidate_filter = _normalize_spaces(
        candidate_filter
    ).lower()

    rows = list(full.get("rows", []))

    if normalized_status and normalized_status != "all":
        rows = [row for row in rows if str(row.get("status", "")).lower() == normalized_status]

    if normalized_decision and normalized_decision != "all":
        if normalized_decision == "approved":
            approved_decisions = {
                "approve_update",
                "approve_new_product",
                "same_product",
            }
            rows = [
                row
                for row in rows
                if row.get("decision") in approved_decisions
            ]
        else:
            rows = [
                row
                for row in rows
                if str(row.get("decision", "pending")).lower()
                == normalized_decision
            ]

    if (
        normalized_candidate_filter
        and normalized_candidate_filter != "all"
    ):
        if normalized_candidate_filter == "with_candidates":
            rows = [
                row
                for row in rows
                if int(
                    row.get("match_candidate_count", 0) or 0
                ) > 0
            ]

        elif normalized_candidate_filter == "without_candidates":
            rows = [
                row
                for row in rows
                if (
                    str(row.get("status", "")).lower()
                    == "site_only"
                    and int(
                        row.get(
                            "match_candidate_count",
                            0,
                        )
                        or 0
                    )
                    == 0
                )
            ]

        elif normalized_candidate_filter == "exact":
            rows = [
                row
                for row in rows
                if (
                    str(
                        row.get("match_level", "")
                    ).lower()
                    == "exact"
                    and int(
                        row.get(
                            "match_candidate_count",
                            0,
                        )
                        or 0
                    )
                    > 0
                )
            ]

        elif normalized_candidate_filter == "probable":
            rows = [
                row
                for row in rows
                if (
                    str(
                        row.get("match_level", "")
                    ).lower()
                    == "probable"
                    and int(
                        row.get(
                            "match_candidate_count",
                            0,
                        )
                        or 0
                    )
                    > 0
                )
            ]

        elif normalized_candidate_filter == "ambiguous":
            rows = [
                row
                for row in rows
                if (
                    str(
                        row.get("match_level", "")
                    ).lower()
                    == "ambiguous"
                    and int(
                        row.get(
                            "match_candidate_count",
                            0,
                        )
                        or 0
                    )
                    > 0
                )
            ]

        elif normalized_candidate_filter == "disputed":
            rows = [
                row
                for row in rows
                if bool(
                    row.get("has_disputed_candidate")
                )
            ]

        elif normalized_candidate_filter == "safe_url":
            rows = [
                row
                for row in rows
                if str(
                    row.get("match_method", "")
                ).lower()
                == "official_url"
            ]

        elif normalized_candidate_filter == "safe_name":
            rows = [
                row
                for row in rows
                if str(
                    row.get("match_method", "")
                ).lower()
                == "normalized_name"
            ]

    if normalized_query:
        rows = [
            row
            for row in rows
            if normalized_query
            in _strip_accents(
                " ".join(
                    [
                        _normalize_spaces(row.get("site_id")),
                        _normalize_spaces(row.get("site_name")),
                        _normalize_spaces(row.get("source_name")),
                        _normalize_spaces(row.get("site_version")),
                        _normalize_spaces(row.get("source_version")),
                        _normalize_spaces(row.get("source_category")),
                    ]
                ).lower()
            )
        ]

    resolved_candidate_count_min = (
        max(0, int(candidate_count_min))
        if candidate_count_min is not None
        else None
    )

    resolved_candidate_count_max = (
        max(0, int(candidate_count_max))
        if candidate_count_max is not None
        else None
    )

    if (
        resolved_candidate_count_min is not None
        and resolved_candidate_count_max is not None
        and resolved_candidate_count_min
        > resolved_candidate_count_max
    ):
        (
            resolved_candidate_count_min,
            resolved_candidate_count_max,
        ) = (
            resolved_candidate_count_max,
            resolved_candidate_count_min,
        )

    if resolved_candidate_count_min is not None:
        rows = [
            row
            for row in rows
            if int(
                row.get("match_candidate_count", 0) or 0
            )
            >= resolved_candidate_count_min
        ]

    if resolved_candidate_count_max is not None:
        rows = [
            row
            for row in rows
            if int(
                row.get("match_candidate_count", 0) or 0
            )
            <= resolved_candidate_count_max
        ]

    resolved_score_min = (
        max(0, min(100, int(score_min)))
        if score_min is not None
        else None
    )

    resolved_score_max = (
        max(0, min(100, int(score_max)))
        if score_max is not None
        else None
    )

    if (
        resolved_score_min is not None
        and resolved_score_max is not None
        and resolved_score_min > resolved_score_max
    ):
        resolved_score_min, resolved_score_max = (
            resolved_score_max,
            resolved_score_min,
        )

    if resolved_score_min is not None:
        rows = [
            row
            for row in rows
            if int(row.get("match_score", 0) or 0)
            >= resolved_score_min
        ]

    if resolved_score_max is not None:
        rows = [
            row
            for row in rows
            if int(row.get("match_score", 0) or 0)
            <= resolved_score_max
        ]

    resolved_page_size = max(
        1,
        min(
            int(page_size or settings.COMPARISON_DEFAULT_PAGE_SIZE),
            int(settings.COMPARISON_MAX_PAGE_SIZE),
        ),
    )

    total_filtered = len(rows)
    total_pages = max(
        1,
        (total_filtered + resolved_page_size - 1)
        // resolved_page_size,
    )
    resolved_page = max(
        1,
        min(int(page or 1), total_pages),
    )
    start = (resolved_page - 1) * resolved_page_size
    end = start + resolved_page_size
    

    saved_decision_summary = get_decision_summary()

    decision_counts = {
        "pending": 0,
        "approve_update": 0,
        "ignore": 0,
        "review_later": 0,
        "same_product": 0,
        "different_products": 0,
        "approve_new_product": 0,
    }

    for comparison_row in full.get("rows", []):
        decision_key = str(
            comparison_row.get("decision", "pending")
        ).strip().lower()

        if decision_key not in decision_counts:
            decision_key = "pending"

        decision_counts[decision_key] += 1

    decision_summary = {
        "counts": decision_counts,
        "total": sum(decision_counts.values()),
        "approved_total": (
            decision_counts["approve_update"]
            + decision_counts["approve_new_product"]
            + decision_counts["same_product"]
        ),
        "pending_total": decision_counts["pending"],
        "ignored_total": decision_counts["ignore"],
        "review_total": decision_counts["review_later"],
    }

    return {
        "ok": True,
        "summary": {
            **{key: value for key, value in full.items() if key != "rows"},
            "decision_summary": decision_summary,
            "saved_decision_summary": saved_decision_summary,
        },
        
        "filters": {
            "status": normalized_status or "all",
            "query": query,
            "decision": normalized_decision or "all",
            "candidate_filter": (
                normalized_candidate_filter or "all"
            ),
            "candidate_count_min": (
                resolved_candidate_count_min
            ),
            "candidate_count_max": (
                resolved_candidate_count_max
            ),
            "score_min": resolved_score_min,
            "score_max": resolved_score_max,
        },

        "pagination": {
            "page": resolved_page,
            "page_size": resolved_page_size,
            "total_rows": total_filtered,
            "total_pages": total_pages,
        },
        "rows": rows[start:end],
    }

def search_comparison_catalog_products(
    catalog_path: str | Path,
    *,
    role: str,
    query: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = Path(catalog_path)

    if not path.exists() or not path.is_file():
        return []

    normalized_role = _normalize_spaces(role).lower()

    if normalized_role == "source":
        rows = _normalize_source_rows(
            _read_csv_rows(path)
        )

        products = [
            {
                "role": "source",
                "product_key": row.get(
                    "source_product_key",
                    "",
                ),
                "site_id": "",
                "name": row.get(
                    "source_name",
                    "",
                ),
                "version": row.get(
                    "source_version",
                    "",
                ),
                "category": row.get(
                    "source_category",
                    "",
                ),
                "product_url": row.get(
                    "source_product_url",
                    "",
                ),
                "official_url": row.get(
                    "source_official_url",
                    "",
                ),
            }
            for row in rows
        ]

    elif normalized_role == "site":
        rows = _normalize_site_rows(
            _read_csv_rows(path)
        )

        products = [
            {
                "role": "site",
                "product_key": row.get(
                    "site_product_key",
                    "",
                ),
                "site_id": row.get(
                    "site_id",
                    "",
                ),
                "name": row.get(
                    "site_name",
                    "",
                ),
                "version": row.get(
                    "site_version",
                    "",
                ),
                "category": row.get(
                    "site_categories",
                    "",
                ),
                "product_url": "",
                "official_url": row.get(
                    "site_official_url",
                    "",
                ),
            }
            for row in rows
        ]

    else:
        raise ValueError(
            "role deve ser 'source' ou 'site'."
        )

    search_text = _strip_accents(
        _normalize_spaces(query).lower()
    )

    if search_text:
        filtered = []

        for product in products:
            haystack = _strip_accents(
                " ".join(
                    [
                        _normalize_spaces(
                            product.get("name")
                        ),
                        _normalize_spaces(
                            product.get("site_id")
                        ),
                        _normalize_spaces(
                            product.get("version")
                        ),
                        _normalize_spaces(
                            product.get("category")
                        ),
                        _normalize_spaces(
                            product.get("official_url")
                        ),
                    ]
                ).lower()
            )

            if search_text in haystack:
                filtered.append(product)

        products = filtered

    products.sort(
        key=lambda item: (
            _normalize_spaces(
                item.get("name")
            ).lower(),
            _normalize_spaces(
                item.get("version")
            ).lower(),
        )
    )

    resolved_limit = max(
        1,
        min(
            int(limit or 50),
            100,
        ),
    )

    return products[:resolved_limit]


def comparison_catalog_has_product(
    catalog_path: str | Path,
    *,
    role: str,
    product_key: str,
) -> bool:
    path = Path(catalog_path)
    key = _normalize_spaces(product_key)
    normalized_role = _normalize_spaces(role).lower()
    if not key or not path.is_file():
        return False
    if normalized_role == "source":
        rows = _normalize_source_rows(_read_csv_rows(path))
        field = "source_product_key"
    elif normalized_role == "site":
        rows = _normalize_site_rows(_read_csv_rows(path))
        field = "site_product_key"
    else:
        raise ValueError("role deve ser 'source' ou 'site'.")
    return any(_normalize_spaces(row.get(field)) == key for row in rows)

__all__ = [
    "build_comparison_payload",
    "comparison_catalog_has_product",
    "search_comparison_catalog_products",
    "clean_version",
    "compare_versions",
    "describe_version_quality",
    "is_suspicious_spreadsheet_version",
    "normalize_name_key",
    "normalize_url_key",
]
