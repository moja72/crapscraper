from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.collection.legacy_core import settings
from app.collection.legacy_core.models import ScraperContext, build_context, build_runtime_context_dict

try:
    from app.core.exceptions import AdapterError, UnsupportedAdapterError
except Exception:  # pragma: no cover
    class AdapterError(RuntimeError):
        pass

    class UnsupportedAdapterError(AdapterError):
        pass


# ============================================================
# HELPERS BÁSICOS
# ============================================================


def _normalize_spaces(value: Any) -> str:
    if value in (None, ""):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _ensure_trailing_slash(url: Any) -> str:
    text = _normalize_spaces(url)
    if not text:
        return ""

    parsed = urlparse(text)
    path = parsed.path or "/"
    if not path.endswith("/"):
        path += "/"

    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


def _set_query_param(url: str, **params: Any) -> str:
    parsed = urlparse(str(url or ""))
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))

    for key, value in params.items():
        if value in (None, ""):
            continue
        query[str(key)] = str(value)

    new_query = urlencode(query, doseq=True)
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        )
    )


def remove_count_from_name(text: Any) -> str:
    return _normalize_spaces(re.sub(r"\s*\(\d+\)\s*$", "", str(text or "")))


def clean_final_name(value: Any) -> str:
    return _normalize_spaces(str(value or "").replace("–", "-"))


def clean_version(value: Any) -> str:
    version = _normalize_spaces(value)

    if not version:
        return ""

    # Aceita células vindas de CSV como ="1.5.9" ou com apóstrofo inicial.
    spreadsheet_formula = re.fullmatch(r'=\"(.+)\"', version)
    if spreadsheet_formula:
        version = _normalize_spaces(spreadsheet_formula.group(1))
    if version.startswith("'"):
        version = _normalize_spaces(version[1:])

    raw_version = version
    version = re.sub(r"^\s*vers[aã]o\s*[:#-]?\s*", "", version, flags=re.IGNORECASE).strip()
    version = version.replace(",", ".")
    version = re.sub(r"\s+", "", version)
    version = version.strip(" .-_")

    if not version:
        return ""

    # Não deixa datas ou contadores entrarem como versão.
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


def build_observation(classes: Any, text: Any) -> str:
    _ = _normalize_spaces(classes)
    text_value = _normalize_spaces(text)
    return text_value


def is_invalid_name(name: Any) -> bool:
    value = _normalize_spaces(name).lower()
    invalid_values = {
        "",
        "www.ultrapackv2.com",
        "ultrapackv2.com",
        "https://www.ultrapackv2.com",
        "http://www.ultrapackv2.com",
    }

    if value in invalid_values:
        return True

    if value.startswith("http://") or value.startswith("https://") or value.startswith("www."):
        return True

    return len(value) < 3


def slug_to_name(url: Any) -> str:
    try:
        path = urlparse(str(url or "")).path.strip("/")
        slug = path.split("/")[-1]
        return _normalize_spaces(slug.replace("-", " "))
    except Exception:
        return ""


# ============================================================
# MODELOS DECLARATIVOS
# ============================================================


@dataclass(frozen=True, slots=True)
class AdapterIdentity:
    site_key: str
    item_type_key: str
    label: str = ""

    @property
    def registry_key(self) -> str:
        return f"{self.site_key}:{self.item_type_key}"

    def to_dict(self) -> dict[str, str]:
        return {
            "site_key": self.site_key,
            "item_type_key": self.item_type_key,
            "label": self.label or self.registry_key,
            "registry_key": self.registry_key,
        }


@dataclass(frozen=True, slots=True)
class ListingSelectors:
    category_link_selector: str
    item_path_fragment: str
    item_card_selector: str
    item_cover_link_selector: str
    item_title_link_selector: str
    item_any_link_selector: str
    item_version_selector: str
    category_total_selector: str

    def to_dict(self) -> dict[str, str]:
        return {
            "category_link_selector": self.category_link_selector,
            "item_path_fragment": self.item_path_fragment,
            "item_card_selector": self.item_card_selector,
            "item_cover_link_selector": self.item_cover_link_selector,
            "item_title_link_selector": self.item_title_link_selector,
            "item_any_link_selector": self.item_any_link_selector,
            "item_version_selector": self.item_version_selector,
            "category_total_selector": self.category_total_selector,
        }


@dataclass(frozen=True, slots=True)
class PaginationRules:
    page_size_param: str = "ppg"
    page_size_value: int = 128
    page_number_query_param: str = "paged"
    page_path_prefix: str = "page"

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_size_param": self.page_size_param,
            "page_size_value": self.page_size_value,
            "page_number_query_param": self.page_number_query_param,
            "page_path_prefix": self.page_path_prefix,
        }


@dataclass(frozen=True, slots=True)
class DetailSelectors:
    name_selectors: tuple[str, ...]
    version_tag_selector: str
    version_value_selector: str
    image_alt_selector: str
    og_title_selector: str
    official_page_button_labels: tuple[str, ...] = ()
    observation_scope_selectors: tuple[str, ...] = ()
    skip_observation_container_selector: str = ""
    skip_observation_class: str = ""
    observation_min_length: int = 15
    detail_attempts: int = 3

    def to_dict(self) -> dict[str, Any]:
        return {
            "name_selectors": list(self.name_selectors),
            "version_tag_selector": self.version_tag_selector,
            "version_value_selector": self.version_value_selector,
            "image_alt_selector": self.image_alt_selector,
            "og_title_selector": self.og_title_selector,
            "official_page_button_labels": list(self.official_page_button_labels),
            "observation_scope_selectors": list(self.observation_scope_selectors),
            "skip_observation_container_selector": self.skip_observation_container_selector,
            "skip_observation_class": self.skip_observation_class,
            "observation_min_length": self.observation_min_length,
            "detail_attempts": self.detail_attempts,
        }


@dataclass(frozen=True, slots=True)
class AdapterDefinition:
    identity: AdapterIdentity
    listing: ListingSelectors
    pagination: PaginationRules
    detail: DetailSelectors
    grouped_category_hints: tuple[str, ...] = ()
    runtime_overrides: dict[str, Any] = field(default_factory=dict)

    @property
    def site_key(self) -> str:
        return self.identity.site_key

    @property
    def item_type_key(self) -> str:
        return self.identity.item_type_key

    @property
    def registry_key(self) -> str:
        return self.identity.registry_key

    def matches(
        self,
        context: ScraperContext | dict[str, Any] | None = None,
        *,
        site_key: str | None = None,
        item_type_key: str | None = None,
    ) -> bool:
        resolved_site_key = site_key
        resolved_item_type_key = item_type_key

        if context is not None:
            try:
                resolved = build_context(context)
                resolved_site_key = resolved.site_key
                resolved_item_type_key = resolved.item_type_key
            except Exception:
                if isinstance(context, dict):
                    resolved_site_key = resolved_site_key or str(context.get("site_key", "") or "")
                    resolved_item_type_key = resolved_item_type_key or str(context.get("item_type_key", "") or "")

        return (
            settings.normalize_site_key(resolved_site_key) == self.site_key
            and settings.normalize_item_type_key(resolved_item_type_key) == self.item_type_key
        )

    def build_runtime_context(
        self,
        context: ScraperContext | dict[str, Any] | None = None,
        *,
        site_key: str | None = None,
        item_type_key: str | None = None,
        account_key: str | None = None,
        slot_name: str | None = None,
        runtime_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_context = build_context(
            context,
            site_key=site_key or self.site_key,
            item_type_key=item_type_key or self.item_type_key,
            account_key=account_key,
            slot_name=slot_name,
        )
        data = build_runtime_context_dict(resolved_context)

        if isinstance(runtime_context, dict):
            data.update(dict(runtime_context))

        if not data.get("catalog_url"):
            data["catalog_url"] = settings.build_catalog_url(
                site_key=resolved_context.site_key,
                item_type_key=resolved_context.item_type_key,
            )

        merged_hints: list[str] = []
        seen_hints: set[str] = set()

        raw_hints = list(data.get("grouped_category_hints", []) or []) + list(self.grouped_category_hints)
        for hint in raw_hints:
            normalized = _ensure_trailing_slash(hint)
            if not normalized or normalized in seen_hints:
                continue
            seen_hints.add(normalized)
            merged_hints.append(normalized)

        data["grouped_category_hints"] = merged_hints
        data["adapter_key"] = self.registry_key
        data["adapter_label"] = self.identity.label or self.registry_key

        if self.runtime_overrides:
            data.update(dict(self.runtime_overrides))

        return data

    def grouped_hints_set(self, runtime_context: dict[str, Any] | None = None) -> set[str]:
        raw = list((runtime_context or {}).get("grouped_category_hints", []) or []) + list(self.grouped_category_hints)
        return {
            _ensure_trailing_slash(value).lower()
            for value in raw
            if _normalize_spaces(value)
        }

    def normalize_category(self, category: dict[str, Any] | None) -> dict[str, Any]:
        data = dict(category or {})
        return {
            "categoria_nome": _normalize_spaces(
                data.get("categoria_nome")
                or data.get("name")
                or data.get("nome")
                or ""
            ),
            "categoria_url": _ensure_trailing_slash(
                data.get("categoria_url")
                or data.get("url")
                or ""
            ),
            "total_esperado": max(
                0,
                _to_int(
                    data.get("total_esperado", data.get("expected_total", data.get("total", 0))),
                    0,
                ),
            ),
            "tipo": _normalize_spaces(
                data.get("tipo")
                or data.get("item_type_key")
                or self.item_type_key
            ) or self.item_type_key,
        }

    def normalize_list_item(
        self,
        item: dict[str, Any] | None,
        *,
        category_name: str = "",
        category_url: str = "",
    ) -> dict[str, str]:
        data = dict(item or {})
        return {
            "tipo": _normalize_spaces(
                data.get("tipo")
                or data.get("item_type_key")
                or self.item_type_key
            ) or self.item_type_key,
            "categoria_nome": _normalize_spaces(
                data.get("categoria_nome")
                or data.get("category_name")
                or category_name
            ) or category_name,
            "categoria_url": _ensure_trailing_slash(
                data.get("categoria_url")
                or data.get("category_url")
                or category_url
            ) or category_url,
            "link_produto": _normalize_spaces(
                data.get("link_produto")
                or data.get("product_url")
                or ""
            ),
            "nome_lista": _normalize_spaces(
                data.get("nome_lista")
                or data.get("product_name")
                or data.get("nome_produto")
                or ""
            ),
            "versao_lista": _normalize_spaces(
                data.get("versao_lista")
                or data.get("product_version")
                or data.get("versao_produto")
                or ""
            ),
        }

    def normalize_catalog_item(
        self,
        item: dict[str, Any] | None,
        *,
        category_name: str = "",
        category_url: str = "",
    ) -> dict[str, str]:
        data = self.normalize_list_item(
            item,
            category_name=category_name,
            category_url=category_url,
        )
        return {
            "tipo": data["tipo"],
            "categoria_nome": data["categoria_nome"],
            "categoria_url": _ensure_trailing_slash(data["categoria_url"]),
            "link_produto": data["link_produto"],
            "nome_produto": _normalize_spaces(
                dict(item or {}).get("nome_produto")
                or data.get("nome_lista", "")
            ),
            "versao_produto": clean_version(
                dict(item or {}).get("versao_produto")
                or data.get("versao_lista", "")
            ),
            "observacao": _normalize_spaces(dict(item or {}).get("observacao", "")),
        }

    def clean_category_name(self, value: Any) -> str:
        return remove_count_from_name(value)

    def clean_final_name(self, value: Any) -> str:
        return clean_final_name(value)

    def clean_version(self, value: Any) -> str:
        return clean_version(value)

    def build_observation(self, classes: Any, text: Any) -> str:
        return build_observation(classes, text)

    def is_invalid_name(self, value: Any) -> bool:
        return is_invalid_name(value)

    def slug_to_name(self, url: Any) -> str:
        return slug_to_name(url)

    def choose_final_name(
        self,
        product_url: str,
        *,
        list_name: str = "",
        raw_name: str = "",
        image_alt: str = "",
        og_title: str = "",
    ) -> str:
        candidates = [
            raw_name,
            image_alt,
            og_title,
            list_name,
            self.slug_to_name(product_url),
        ]

        for candidate in candidates:
            cleaned = self.clean_final_name(candidate)
            if self.is_invalid_name(cleaned):
                continue
            return cleaned

        return ""

    def build_page_candidates(self, category_url: str, page_number: int) -> list[str]:
        base = _ensure_trailing_slash(category_url)
        if not base:
            return []

        page_number_int = max(1, int(page_number))

        if self.site_key == "plugintheme":
            if page_number_int <= 1:
                return [base]

            return [
                _set_query_param(base, page=page_number_int),
            ]

        if page_number_int <= 1:
            return [
                _set_query_param(
                    base,
                    **{self.pagination.page_size_param: self.pagination.page_size_value},
                ),
                base,
            ]

        return [
            _set_query_param(
                f"{base}{self.pagination.page_path_prefix}/{page_number_int}/",
                **{self.pagination.page_size_param: self.pagination.page_size_value},
            ),
            _set_query_param(
                base,
                **{
                    self.pagination.page_size_param: self.pagination.page_size_value,
                    self.pagination.page_number_query_param: page_number_int,
                },
            ),
            _set_query_param(
                base,
                **{
                    self.pagination.page_number_query_param: page_number_int,
                    self.pagination.page_size_param: self.pagination.page_size_value,
                },
            ),
        ]

    def build_listing_config(self) -> dict[str, Any]:
        return {
            **self.listing.to_dict(),
            **self.pagination.to_dict(),
        }

    def build_detail_config(self) -> dict[str, Any]:
        return self.detail.to_dict()

    def to_public_dict(self) -> dict[str, Any]:
        return {
            **self.identity.to_dict(),
            "listing": self.listing.to_dict(),
            "pagination": self.pagination.to_dict(),
            "detail": self.detail.to_dict(),
            "grouped_category_hints": list(self.grouped_category_hints),
            "runtime_overrides": dict(self.runtime_overrides),
        }


# ============================================================
# REGISTRY
# ============================================================

_ADAPTERS: dict[tuple[str, str], AdapterDefinition] = {}


def register_adapter(adapter: AdapterDefinition) -> AdapterDefinition:
    key = (adapter.site_key, adapter.item_type_key)

    if key in _ADAPTERS:
        raise AdapterError(
            f"Adapter já registrado para {adapter.site_key}:{adapter.item_type_key}."
        )

    _ADAPTERS[key] = adapter
    return adapter


def get_registered_adapters() -> dict[tuple[str, str], AdapterDefinition]:
    return dict(_ADAPTERS)


def list_adapters(
    *,
    site_key: str | None = None,
    item_type_key: str | None = None,
) -> list[AdapterDefinition]:
    normalized_site_key = settings.normalize_site_key(site_key) if site_key not in (None, "") else None
    normalized_item_type_key = settings.normalize_item_type_key(item_type_key) if item_type_key not in (None, "") else None

    result: list[AdapterDefinition] = []
    for adapter in _ADAPTERS.values():
        if normalized_site_key and adapter.site_key != normalized_site_key:
            continue
        if normalized_item_type_key and adapter.item_type_key != normalized_item_type_key:
            continue
        result.append(adapter)

    return sorted(result, key=lambda item: item.registry_key)


def has_adapter(
    context: ScraperContext | dict[str, Any] | None = None,
    *,
    site_key: str | None = None,
    item_type_key: str | None = None,
) -> bool:
    try:
        get_adapter(
            context,
            site_key=site_key,
            item_type_key=item_type_key,
        )
        return True
    except UnsupportedAdapterError:
        return False


def get_adapter(
    context: ScraperContext | dict[str, Any] | None = None,
    *,
    site_key: str | None = None,
    item_type_key: str | None = None,
    account_key: str | None = None,
    slot_name: str | None = None,
) -> AdapterDefinition:
    resolved_context = build_context(
        context,
        site_key=site_key,
        item_type_key=item_type_key,
        account_key=account_key,
        slot_name=slot_name,
    )

    key = (resolved_context.site_key, resolved_context.item_type_key)
    adapter = _ADAPTERS.get(key)

    if adapter is None:
        raise UnsupportedAdapterError(
            f"Nenhum adapter foi registrado para {resolved_context.site_key}:{resolved_context.item_type_key}.",
            details={
                "site_key": resolved_context.site_key,
                "item_type_key": resolved_context.item_type_key,
                "account_key": resolved_context.account_key,
                "slot_name": resolved_context.slot_name,
            },
        )

    return adapter


def build_adapters_public_list() -> list[dict[str, Any]]:
    return [adapter.to_public_dict() for adapter in list_adapters()]


# ============================================================
# ULTRAPACKV2
# ============================================================

_ULTRAPACK_LISTING = ListingSelectors(
    category_link_selector="a.dev-link, a.themeforest-cat-links",
    item_path_fragment="/item/",
    item_card_selector=".new-post-display.new-posts2",
    item_cover_link_selector="a.link-cover[href*='/item/']",
    item_title_link_selector="h2 a[href*='/item/']",
    item_any_link_selector="a.link-cover[href*='/item/'], h2 a[href*='/item/']",
    item_version_selector=".version",
    category_total_selector=".itens-total",
)

_ULTRAPACK_PAGINATION = PaginationRules(
    page_size_param="ppg",
    page_size_value=128,
    page_number_query_param="paged",
    page_path_prefix="page",
)

_ULTRAPACK_DETAIL = DetailSelectors(
    name_selectors=(
        ".single-post-item-detail h1",
        "article.post h1",
        "#content article h1",
        "h1",
    ),
    version_tag_selector=".inline-block-tag",
    version_value_selector=".item-desc-value",
    image_alt_selector=".single-post-item-img img",
    og_title_selector="meta[property='og:title']",
    official_page_button_labels=(
        "página do item",
        "pagina do item",
        "item page",
    ),
    observation_scope_selectors=(
        "article.post .item-desbloqueado",
        "article.post .item-descontinuado",
        "article.post div[class*='item-desbloqueado']",
        "article.post div[class*='item-descontinuado']",
        "article.post div[class*='item-']",
        "article .item-desbloqueado",
        "article .item-descontinuado",
        "article div[class*='item-desbloqueado']",
        "article div[class*='item-descontinuado']",
        "article div[class*='item-']",
    ),
    skip_observation_container_selector=".modal, #myModal, .post-content, #up-version-box",
    skip_observation_class=(
        "item-descricao item-versao item-version item-page "
        "item-categoria-desenvolvedor item-tags item-desbl"
    ),
    observation_min_length=15,
    detail_attempts=3,
)


def _make_ultrapack_adapter(item_type_key: str) -> AdapterDefinition:
    site = settings.get_site("ultrapackv2")
    item_type = settings.get_item_type(item_type_key)

    return AdapterDefinition(
        identity=AdapterIdentity(
            site_key=site.key,
            item_type_key=item_type.key,
            label=f"{site.label} · {item_type.label_plural}",
        ),
        listing=_ULTRAPACK_LISTING,
        pagination=_ULTRAPACK_PAGINATION,
        detail=_ULTRAPACK_DETAIL,
        grouped_category_hints=settings.get_grouped_category_hints(
            site_key=site.key,
            item_type_key=item_type.key,
        ),
        runtime_overrides={
            "site_label": site.label,
            "item_type_label_singular": item_type.label_singular,
            "item_type_label_plural": item_type.label_plural,
        },
    )


# ============================================================
# PLUGINTHEME
# ============================================================

_PLUGINTHEME_LISTING = ListingSelectors(
    category_link_selector="main a[href*='/product-category/'], section a[href*='/product-category/']",
    item_path_fragment="/product/",
    item_card_selector="main article, section article, main div[class*='product'], section div[class*='product'], main div[class*='card'], section div[class*='card']",
    item_cover_link_selector="a[href*='/product/']",
    item_title_link_selector="h1, h2, h3, h4, .product-title, .wd-entities-title",
    item_any_link_selector="main a[href*='/product/'], section a[href*='/product/']",
    item_version_selector=".__pt_no_version__",
    category_total_selector=".woocommerce-result-count, .result-count, main, body",
)

_PLUGINTHEME_PAGINATION = PaginationRules(
    page_size_param="page",
    page_size_value=24,
    page_number_query_param="page",
    page_path_prefix="page",
)

_PLUGINTHEME_DETAIL = DetailSelectors(
    name_selectors=(
        ".single-bt-item-detail h1",
        ".single-bt-right h1",
        "main h1",
        "article h1",
        "h1.product_title.entry-title",
        "h1.product_title",
        ".entry-summary h1",
        "h1",
    ),
    version_tag_selector=".single-bt-item-version, .single-bt-right .text-muted-foreground, .summary .elementor-icon-list-item, .entry-summary .elementor-icon-list-item, [class*='version'], [class*='calendar'], .text-muted-foreground",
    version_value_selector=".single-bt-item-version, .single-bt-right .text-muted-foreground, .summary .elementor-icon-list-item .elementor-icon-list-text, .entry-summary .elementor-icon-list-item .elementor-icon-list-text, .summary .product-version, .entry-summary .product-version, [class*='version'] span, .text-muted-foreground span, [class*='version']",
    image_alt_selector="main img, article img, .woocommerce-product-gallery img, .product-images img, .wp-post-image, img",
    og_title_selector="meta[property='og:title']",
    official_page_button_labels=(
        "demo ao vivo",
        "live demo",
        "view demo",
        "página oficial",
        "pagina oficial",
        "site oficial",
        "official site",
    ),
    observation_scope_selectors=(
        "main div",
        "article div",
        "section div",
        ".woocommerce-Tabs-panel div",
        ".entry-content div",
        ".product-details div",
    ),
    skip_observation_container_selector="header, nav, footer, .summary, .entry-summary",
    skip_observation_class="product_meta",
    observation_min_length=15,
    detail_attempts=3,
)


def _make_plugintheme_adapter(item_type_key: str) -> AdapterDefinition:
    site = settings.get_site("plugintheme")
    item_type = settings.get_item_type(item_type_key)

    return AdapterDefinition(
        identity=AdapterIdentity(
            site_key=site.key,
            item_type_key=item_type.key,
            label=f"{site.label} · {item_type.label_plural}",
        ),
        listing=_PLUGINTHEME_LISTING,
        pagination=_PLUGINTHEME_PAGINATION,
        detail=_PLUGINTHEME_DETAIL,
        grouped_category_hints=settings.get_grouped_category_hints(
            site_key=site.key,
            item_type_key=item_type.key,
        ),
        runtime_overrides={
            "site_label": site.label,
            "item_type_label_singular": item_type.label_singular,
            "item_type_label_plural": item_type.label_plural,
        },
    )


def register_builtin_adapters() -> None:
    if _ADAPTERS:
        return

    for item_type_key in ("plugin", "theme", "template"):
        if settings.site_supports_item_type("ultrapackv2", item_type_key):
            register_adapter(_make_ultrapack_adapter(item_type_key))

    for item_type_key in ("plugin_theme",):
        if settings.site_supports_item_type("plugintheme", item_type_key):
            register_adapter(_make_plugintheme_adapter(item_type_key))


register_builtin_adapters()


# ============================================================
# ALIASES PT-BR
# ============================================================

IdentidadeAdapter = AdapterIdentity
SeletoresListagem = ListingSelectors
RegrasPaginacao = PaginationRules
SeletoresDetalhe = DetailSelectors
DefinicaoAdapter = AdapterDefinition

registrar_adapter = register_adapter
obter_adapter = get_adapter
listar_adapters = list_adapters
possui_adapter = has_adapter
montar_lista_publica_adapters = build_adapters_public_list

normalizar_espacos = _normalize_spaces
garantir_barra_final = _ensure_trailing_slash
remover_contagem_do_nome = remove_count_from_name
limpar_nome_final = clean_final_name
limpar_versao = clean_version
montar_observacao = build_observation
nome_parece_invalido = is_invalid_name
slug_para_nome = slug_to_name


__all__ = [
    "AdapterError",
    "UnsupportedAdapterError",
    "AdapterIdentity",
    "ListingSelectors",
    "PaginationRules",
    "DetailSelectors",
    "AdapterDefinition",
    "register_adapter",
    "get_registered_adapters",
    "list_adapters",
    "has_adapter",
    "get_adapter",
    "build_adapters_public_list",
    "remove_count_from_name",
    "clean_final_name",
    "clean_version",
    "build_observation",
    "is_invalid_name",
    "slug_to_name",
    "register_builtin_adapters",
    "IdentidadeAdapter",
    "SeletoresListagem",
    "RegrasPaginacao",
    "SeletoresDetalhe",
    "DefinicaoAdapter",
    "registrar_adapter",
    "obter_adapter",
    "listar_adapters",
    "possui_adapter",
    "montar_lista_publica_adapters",
    "normalizar_espacos",
    "garantir_barra_final",
    "remover_contagem_do_nome",
    "limpar_nome_final",
    "limpar_versao",
    "montar_observacao",
    "nome_parece_invalido",
    "slug_para_nome",
]