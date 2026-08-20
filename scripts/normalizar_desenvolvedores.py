from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.addition_custom_fields_policy as fields
import app.new_product_workflow_policy as additions
from app.integrations.woocommerce import metadata_value


def _meta_item(product: Mapping[str, Any], key: str) -> Mapping[str, Any] | None:
    for item in product.get("meta_data", []) or []:
        if isinstance(item, Mapping) and str(item.get("key") or "") == key:
            return item
    return None


def _update_product(woo: Any, product: Mapping[str, Any], normalized: str) -> None:
    product_id = int(product.get("id") or 0)
    current = _meta_item(product, "desenvolvedor")
    payload: dict[str, Any] = {"key": "desenvolvedor", "value": normalized}
    if current and current.get("id"):
        payload["id"] = int(current["id"])
    additions._wc_request(
        woo,
        "PUT",
        f"/wp-json/wc/v3/products/{product_id}",
        {"meta_data": [payload]},
    )
    fresh = woo.get_product_fresh(product_id)
    confirmed = str(metadata_value(fresh, "desenvolvedor") or "").strip()
    if confirmed != normalized:
        raise RuntimeError(
            f"Produto #{product_id}: WooCommerce não confirmou desenvolvedor={normalized!r}."
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Normaliza nomes técnicos do campo desenvolvedor, por exemplo "
            "template_path -> Template Path. Sem --apply funciona em modo simulação."
        )
    )
    parser.add_argument("--apply", action="store_true", help="Aplica as alterações no WooCommerce.")
    parser.add_argument("--product-id", type=int, default=0, help="Limita a um único produto WooCommerce.")
    parser.add_argument("--per-page", type=int, default=100, help="Quantidade por página na leitura.")
    args = parser.parse_args()

    woo = additions.web._build_store_woocommerce_client()
    changed = 0
    scanned = 0
    page = 1

    while True:
        filters: dict[str, Any] = {}
        if args.product_id:
            filters["include"] = [args.product_id]
        products = woo.list_products(page=page, per_page=max(1, min(100, args.per_page)), **filters)
        if not products:
            break

        for product in products:
            scanned += 1
            raw = str(metadata_value(product, "desenvolvedor") or "").strip()
            if not raw:
                continue
            normalized = fields._normalize_developer_display(raw)
            if not normalized or normalized == raw:
                continue
            if not fields._developer_ok(normalized):
                continue

            product_id = int(product.get("id") or 0)
            name = str(product.get("name") or "").strip()
            print(f"#{product_id} {name}: {raw!r} -> {normalized!r}")
            changed += 1
            if args.apply:
                _update_product(woo, product, normalized)
                print("  OK")

        if args.product_id or len(products) < max(1, min(100, args.per_page)):
            break
        page += 1

    mode = "APLICADO" if args.apply else "SIMULAÇÃO"
    print(f"\n{mode}: {scanned} produto(s) analisado(s); {changed} alteração(ões) encontrada(s).")
    if changed and not args.apply:
        print("Execute novamente com --apply para gravar as alterações.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
