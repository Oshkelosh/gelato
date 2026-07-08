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

    async def get_order(self, order_id: str) -> dict[str, Any]:
        data = await self._request("GET", GELATO_ORDER_BASE, f"/v4/orders/{order_id}")
        return data if isinstance(data, dict) else {"result": data}
