"""Gelato API client."""

from __future__ import annotations

from typing import Any

import httpx

GELATO_ORDER_BASE = "https://order.gelatoapis.com"
GELATO_PRODUCT_BASE = "https://product.gelatoapis.com"


class GelatoAPIError(Exception):
    def __init__(self, message: str, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class GelatoClient:
    def __init__(self, api_key: str, *, timeout: float = 60.0):
        self._api_key = api_key
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"X-API-KEY": self._api_key, "Content-Type": "application/json"}

    async def _request(
        self,
        method: str,
        base: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{base}{path}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.request(
                method, url, headers=self._headers(), params=params, json=json
            )
        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text}
        if resp.status_code >= 400:
            message = resp.text
            if isinstance(data, dict):
                message = data.get("message") or data.get("error") or resp.text
            raise GelatoAPIError(str(message), status_code=resp.status_code, body=data)
        return data

    async def list_catalog_products(self, *, offset: int = 0, limit: int = 100) -> Any:
        return await self._request(
            "GET",
            GELATO_PRODUCT_BASE,
            "/v3/catalogs/products",
            params={"offset": offset, "limit": limit},
        )

    async def create_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = await self._request("POST", GELATO_ORDER_BASE, "/v4/orders", json=payload)
        return data if isinstance(data, dict) else {"result": data}

    async def quote_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /v4/orders:quote — shipment methods and prices for a cart."""
        data = await self._request("POST", GELATO_ORDER_BASE, "/v4/orders:quote", json=payload)
        return data if isinstance(data, dict) else {"quotes": data}

    async def get_order(self, order_id: str) -> dict[str, Any]:
        data = await self._request("GET", GELATO_ORDER_BASE, f"/v4/orders/{order_id}")
        return data if isinstance(data, dict) else {"result": data}


def _facility_method_maps(
    quotes: list[dict[str, Any]],
) -> list[dict[str, dict[str, Any]]]:
    """Per-facility map of normalized method key → {id, name, cents}."""
    from app.addons.suppliers.shipping_quote import to_cents

    facilities: list[dict[str, dict[str, Any]]] = []
    for quote in quotes:
        if not isinstance(quote, dict):
            continue
        methods = quote.get("shipmentMethods")
        if not isinstance(methods, list):
            continue
        fmap: dict[str, dict[str, Any]] = {}
        for method in methods:
            if not isinstance(method, dict):
                continue
            cents = to_cents(method.get("price"))
            if cents is None:
                continue
            uid = str(method.get("shipmentMethodUid") or "").strip()
            kind = str(method.get("type") or "").strip()
            option_id = uid or kind or str(method.get("name") or "").strip()
            if not option_id:
                continue
            key = option_id.lower()
            name = str(method.get("name") or kind or option_id).strip()
            existing = fmap.get(key)
            if existing is None or cents < int(existing["cents"]):
                fmap[key] = {"id": option_id, "name": name, "cents": cents}
        if fmap:
            facilities.append(fmap)
    return facilities


def _facility_fallback(fmap: dict[str, dict[str, Any]]) -> dict[str, Any]:
    preferred = [
        row
        for row in fmap.values()
        if str(row.get("id") or "").lower() in ("normal", "standard")
        or "standard" in str(row.get("name") or "").lower()
        or "normal" in str(row.get("name") or "").lower()
    ]
    pool = preferred or list(fmap.values())
    return min(pool, key=lambda row: int(row["cents"]))


def parse_quote_shipping_options(quotes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate Gelato per-facility methods into cart-level checkout options.

    Prefer methods available on every facility (intersection). If none overlap,
    fall back to union and fill missing facilities with that facility's
    standard/cheapest rate so a selection still has a total.
    """
    if not isinstance(quotes, list) or not quotes:
        return []
    facilities = _facility_method_maps(quotes)
    if not facilities:
        return []

    common = set(facilities[0].keys())
    for fmap in facilities[1:]:
        common &= set(fmap.keys())
    keys = sorted(common) if common else sorted({k for fmap in facilities for k in fmap})

    options: list[dict[str, Any]] = []
    for key in keys:
        total = 0
        name = key
        option_id = key
        found = False
        for fmap in facilities:
            if key in fmap:
                row = fmap[key]
                if not found:
                    name = str(row["name"])
                    option_id = str(row["id"])
                    found = True
            else:
                row = _facility_fallback(fmap)
            total += int(row["cents"])
        options.append({"id": option_id, "name": name, "cents": total})
    return options


def pick_quote_shipping_cents(quotes: list[dict[str, Any]]) -> int | None:
    """Sum the chosen shipment method per quote (facility); prefer standard/normal.

    Gelato may split an order across fulfillment facilities, returning one quote
    per facility that ships separately, so the shipping total is the sum of the
    selected method for each quote. Within a quote, prefer a normal/standard
    method, else the cheapest. Returns ``None`` if nothing can be priced.
    """
    from app.addons.suppliers.shipping_quote import pick_shipping_option

    chosen = pick_shipping_option(
        parse_quote_shipping_options(quotes),
        preferred_ids=("normal", "standard"),
    )
    return int(chosen["cents"]) if chosen else None
