"""Gelato print-on-demand supplier integration."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter
from pydantic import BaseModel, Field, SecretStr

from app.addons.suppliers.base import SupplierAddon
from app.addons.suppliers.gelato.catalog import normalize_gelato_catalog_products
from app.addons.suppliers.gelato.client import (
    GelatoAPIError,
    GelatoClient,
    parse_quote_shipping_options,
)
from schemas.supplier import SupplierCatalogProduct
from app.addons.log import exception, info, warning
from app.addons.config_serialization import dump_addon_config


class GelatoConfig(BaseModel):
    api_key: SecretStr = Field(default=..., description="Gelato API key")
    is_active: bool = Field(default=False)
    auto_submit: bool = Field(default=True, description="Submit orders (vs draft)")
    default_currency: str = Field(default="USD", min_length=3, max_length=3)
    shipment_method_uid: str = Field(default="", description="Optional default shipping method")

    @classmethod
    def config_model(cls):
        return cls


def _map_shipping(address: Dict[str, Any]) -> Dict[str, Any]:
    from app.addons.suppliers.address import canonical_address

    addr = canonical_address(address)
    payload = {
        "firstName": addr["first_name"],
        "lastName": addr["last_name"],
        "addressLine1": addr["line1"],
        "city": addr["city"],
        "postCode": addr["zip"],
        "country": addr["country_code"],
        "email": addr["email"],
        "phone": addr["phone"],
    }
    if addr["state"]:
        payload["state"] = addr["state"]
    if addr["line2"]:
        payload["addressLine2"] = addr["line2"]
    return payload


class GelatoAddon(SupplierAddon):
    addon_id: str = "gelato"
    addon_name: str = "Gelato"
    addon_description: str = "Global print-on-demand via Gelato API."
    addon_category: str = "supplier"
    version: str = "1.0.0"

    _config: Dict[str, Any] | None = None
    _client: GelatoClient | None = None

    @classmethod
    def config_schema(cls):
        return GelatoConfig

    async def initialize(self, config: dict) -> None:
        validated = GelatoConfig(**config)
        self._config = dump_addon_config(validated)
        self._client = GelatoClient(validated.api_key.get_secret_value())
        self.is_enabled = validated.is_active
        info("Gelato", "Initialized auto_submit={}", validated.auto_submit)

    async def validate_config(self, config: dict) -> None:
        from app.core.exceptions import ValidationError

        validated = GelatoConfig(**config)
        api_key = validated.api_key.get_secret_value()
        if not api_key:
            return
        client = GelatoClient(api_key)
        try:
            await client.list_catalog_products(limit=1)
        except GelatoAPIError as exc:
            if exc.status_code == 401:
                raise ValidationError(message="Invalid API key — check your credentials") from exc
            if exc.status_code == 403:
                raise ValidationError(
                    message="API key is valid but missing required permissions: catalog:read"
                ) from exc
            raise ValidationError(message=f"Gelato API error: {exc}") from exc

    async def shutdown(self) -> None:
        self._client = None
        self._config = None
        self.is_enabled = False

    def admin_form_hints(self) -> dict[str, str | bool]:
        return {
            "requires_variant_id": False,
            "product_id_help": "Required. Gelato productUid from your catalog.",
            "variant_id_help": "",
        }

    def _require_client(self) -> GelatoClient:
        if self._client is None:
            raise GelatoAPIError("Gelato addon is not initialized")
        return self._client

    async def _fetch_all_catalog_rows(self) -> list[dict[str, Any]]:
        client = self._require_client()
        rows: list[dict[str, Any]] = []
        offset = 0
        limit = 100
        while True:
            data = await client.list_catalog_products(offset=offset, limit=limit)
            batch: list[dict[str, Any]] = []
            if isinstance(data, list):
                batch = [r for r in data if isinstance(r, dict)]
            elif isinstance(data, dict):
                for key in ("products", "data", "items", "result"):
                    val = data.get(key)
                    if isinstance(val, list):
                        batch = [r for r in val if isinstance(r, dict)]
                        break
            rows.extend(batch)
            if len(batch) < limit:
                break
            offset += limit
            if offset > 10000:
                break
        return rows

    async def list_products(self, **kwargs: Any) -> List[Dict[str, Any]]:
        return await self._fetch_all_catalog_rows()

    async def fetch_catalog_for_import(self, **kwargs: Any) -> List[SupplierCatalogProduct]:
        return normalize_gelato_catalog_products(await self._fetch_all_catalog_rows())

    async def get_product(self, product_id: str) -> Dict[str, Any]:
        for row in await self.list_products():
            uid = str(row.get("productUid") or row.get("uid") or row.get("id") or "")
            if uid == product_id:
                return row
        return {"error": f"Gelato product '{product_id}' not found"}

    def supports_shipping_quotes(self) -> bool:
        return True

    async def quote_shipping(
        self,
        items: List[Dict[str, Any]],
        shipping_address: Dict[str, Any],
        *,
        currency: str | None = None,
    ) -> int | None:
        """Live Gelato rates; prefer standard, else cheapest per quote. None → Site Settings."""
        details = await self.quote_shipping_details(
            items, shipping_address, currency=currency
        )
        if details is None:
            return None
        return int(details["cents"])

    async def quote_shipping_details(
        self,
        items: List[Dict[str, Any]],
        shipping_address: Dict[str, Any],
        *,
        selected_id: str | None = None,
        currency: str | None = None,
    ) -> Dict[str, Any] | None:
        """Live Gelato methods (aggregated across facilities); selected_id overrides default."""
        from app.addons.suppliers.shipping_quote import pick_shipping_option

        client = self._require_client()
        cfg = self._config or {}
        try:
            products = []
            for idx, item in enumerate(items):
                product_uid = str(item.get("supplier_product_id") or "").strip()
                if not product_uid:
                    continue
                products.append(
                    {
                        "itemReferenceId": f"quote-{idx}",
                        "productUid": product_uid,
                        "quantity": int(item.get("quantity") or 1),
                    }
                )
            if not products:
                return None
            payload = {
                "orderReferenceId": "shipping-quote",
                "customerReferenceId": "shipping-quote",
                "currency": str(currency or cfg.get("default_currency") or "USD").upper(),
                "recipient": _map_shipping(shipping_address or {}),
                "products": products,
            }
            data = await client.quote_order(payload)
            quotes = data.get("quotes") if isinstance(data, dict) else None
            options = parse_quote_shipping_options(
                quotes if isinstance(quotes, list) else []
            )
            chosen = pick_shipping_option(
                options,
                selected_id=selected_id,
                preferred_ids=("normal", "standard"),
            )
            if chosen is None:
                return None
            return {
                "cents": int(chosen["cents"]),
                "selected_id": str(chosen["id"]),
                "options": options,
            }
        except GelatoAPIError as exc:
            warning("Gelato", "quote_shipping error: {}", exc)
            return None
        except Exception:
            exception("Gelato", "quote_shipping unexpected error")
            return None

    async def create_order(
        self,
        items: List[Dict[str, Any]],
        shipping_address: Dict[str, Any],
        *,
        external_id: str | None = None,
        supplier_ref: str | None = None,
        shipping_method: str | None = None,
        currency: str | None = None,
    ) -> Dict[str, Any]:
        del supplier_ref
        client = self._require_client()
        cfg = self._config or {}
        try:
            order_items = []
            for idx, item in enumerate(items):
                product_uid = str(item.get("supplier_product_id") or "").strip()
                if not product_uid:
                    continue
                order_items.append(
                    {
                        "itemReferenceId": f"{external_id or 'osh'}-{idx}",
                        "productUid": product_uid,
                        "quantity": int(item.get("quantity") or 1),
                    }
                )
            if not order_items:
                return {"success": False, "error": "No valid Gelato line items"}

            auto_submit = bool(cfg.get("auto_submit", True))
            payload: Dict[str, Any] = {
                "orderType": "order" if auto_submit else "draft",
                "orderReferenceId": external_id or "oshkelosh",
                "customerReferenceId": external_id or "oshkelosh",
                "currency": str(currency or cfg.get("default_currency") or "USD").upper(),
                "items": order_items,
                "shippingAddress": _map_shipping(shipping_address),
            }
            ship_method = (shipping_method or cfg.get("shipment_method_uid") or "").strip()
            if ship_method:
                payload["shipmentMethodUid"] = ship_method

            data = await client.create_order(payload)
            order = data.get("order") if isinstance(data.get("order"), dict) else data
            order_id = str(order.get("id") or order.get("orderId") or "")
            return {
                "success": True,
                "order_id": order_id,
                "status": order.get("status", "created"),
                "gelato_order_id": order_id,
            }
        except GelatoAPIError as exc:
            warning("Gelato", "create_order error: {}", exc)
            return {"success": False, "error": str(exc)}

    async def get_order_status(self, order_id: str) -> Dict[str, Any]:
        try:
            data = await self._require_client().get_order(order_id)
            order = data.get("order") if isinstance(data.get("order"), dict) else data
            return {"order_id": order_id, "status": order.get("status", "unknown")}
        except GelatoAPIError as exc:
            return {"order_id": order_id, "status": "error", "detail": str(exc)}

    async def sync_inventory(self) -> None:
        rows = await self.list_products()
        info("Gelato", "Catalog has {} products", len(rows))

    def get_routers(self) -> List[APIRouter]:
        from app.addons.suppliers.gelato.routes import api_router

        return [api_router]

    def get_admin_routes(self) -> List[APIRouter]:
        from app.addons.suppliers.gelato.routes import admin_router

        return [admin_router]

    def get_admin_templates(self) -> str:
        from pathlib import Path

        return str(Path(__file__).resolve().parent / "templates")

    def get_admin_static(self) -> str:
        from pathlib import Path

        return str(Path(__file__).resolve().parent / "static")
