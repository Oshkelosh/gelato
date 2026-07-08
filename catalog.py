"""Gelato catalog normalization."""

from __future__ import annotations

from typing import Any

from app.addons.suppliers.catalog_utils import decimal_price_to_cents, flat_catalog_item_to_product
from schemas.supplier import POD_INVENTORY_PLACEHOLDER, SupplierCatalogItem, SupplierCatalogProduct


def normalize_gelato_catalog(raw: Any) -> list[SupplierCatalogItem]:
    items: list[SupplierCatalogItem] = []
    rows: list[dict[str, Any]] = []
    if isinstance(raw, list):
        rows = [r for r in raw if isinstance(r, dict)]
    elif isinstance(raw, dict):
        for key in ("products", "data", "items", "result"):
            val = raw.get(key)
            if isinstance(val, list):
                rows = [r for r in val if isinstance(r, dict)]
                break

    for row in rows:
        product_uid = str(
            row.get("productUid")
            or row.get("uid")
            or row.get("id")
            or ""
        ).strip()
        if not product_uid:
            continue
        name = str(row.get("name") or row.get("title") or product_uid)
        price = row.get("price") or row.get("retailPrice") or row.get("recommendedPrice")
        items.append(
            SupplierCatalogItem(
                external_key=f"gelato:{product_uid}",
                name=name,
                description=row.get("description"),
                price_cents=decimal_price_to_cents(price),
                sku=str(row.get("sku") or f"gelato-{product_uid[:32]}"),
                image_url=row.get("imageUrl") or row.get("thumbnailUrl"),
                supplier_value="gelato",
                supplier_product_id=product_uid,
                supplier_variant_id="",
                inventory_quantity=POD_INVENTORY_PLACEHOLDER,
            )
        )
    return items


def normalize_gelato_catalog_products(raw: Any) -> list[SupplierCatalogProduct]:
    """Map Gelato catalog rows to single-variant catalog products."""
    return [flat_catalog_item_to_product(item) for item in normalize_gelato_catalog(raw)]
