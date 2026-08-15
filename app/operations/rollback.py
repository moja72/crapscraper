from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.integrations.woocommerce import pt_versao, variation_downloads


@dataclass(frozen=True)
class DownloadSnapshot:
    id: str
    name: str
    file: str


@dataclass(frozen=True)
class VariationSnapshot:
    id: int
    status: str
    virtual: bool
    downloadable: bool
    regular_price: str
    sale_price: str
    attributes: list[Mapping[str, Any]]
    downloads: list[DownloadSnapshot]


@dataclass(frozen=True)
class RollbackSnapshot:
    product_id: int
    product_status: str
    product_modified: str
    pt_versao: str
    pt_versao_meta_id: int | None
    variations: list[VariationSnapshot]
    file_hash: str | None = None
    captured_at: str = ""


def build_snapshot(
    product: Mapping[str, Any], variations: list[Mapping[str, Any]], *, captured_at: str
) -> RollbackSnapshot:
    version_meta = next(
        (item for item in product.get("meta_data", []) or [] if item.get("key") == "pt_versao"),
        {},
    )
    variation_snapshots = []
    for variation in variations:
        variation_snapshots.append(
            VariationSnapshot(
                id=int(variation.get("id") or 0),
                status=str(variation.get("status") or ""),
                virtual=bool(variation.get("virtual")),
                downloadable=bool(variation.get("downloadable")),
                regular_price=str(variation.get("regular_price") or ""),
                sale_price=str(variation.get("sale_price") or ""),
                attributes=list(variation.get("attributes", []) or []),
                downloads=[DownloadSnapshot(**entry) for entry in variation_downloads(variation)],
            )
        )
    return RollbackSnapshot(
        product_id=int(product.get("id") or 0),
        product_status=str(product.get("status") or ""),
        product_modified=str(product.get("date_modified_gmt") or product.get("date_modified") or ""),
        pt_versao=pt_versao(product),
        pt_versao_meta_id=(int(version_meta["id"]) if version_meta.get("id") is not None else None),
        variations=variation_snapshots,
        captured_at=captured_at,
    )
