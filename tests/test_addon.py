"""Unit tests for the Gelato supplier addon shipping quotes."""

from unittest.mock import AsyncMock

import pytest

from app.addons.suppliers.gelato.addon import GelatoAddon


def test_supports_shipping_quotes():
    assert GelatoAddon().supports_shipping_quotes() is True


@pytest.mark.asyncio
async def test_quote_shipping_returns_cents():
    addon = GelatoAddon()
    addon._config = {"default_currency": "USD"}
    addon._client = AsyncMock()
    addon._client.quote_order = AsyncMock(
        return_value={
            "quotes": [
                {
                    "shipmentMethods": [
                        {"type": "express", "name": "Express", "price": 25.0},
                        {"type": "normal", "name": "Standard", "price": 9.99},
                    ]
                }
            ]
        }
    )
    cents = await addon.quote_shipping(
        [{"supplier_product_id": "uid-1", "quantity": 1}],
        {"country": "US", "city": "Austin"},
    )
    assert cents == 999


@pytest.mark.asyncio
async def test_quote_shipping_returns_none_on_api_error():
    from app.addons.suppliers.gelato.client import GelatoAPIError

    addon = GelatoAddon()
    addon._config = {"default_currency": "USD"}
    addon._client = AsyncMock()
    addon._client.quote_order = AsyncMock(
        side_effect=GelatoAPIError("bad request", status_code=400)
    )
    cents = await addon.quote_shipping(
        [{"supplier_product_id": "uid-1", "quantity": 1}],
        {"country": "US"},
    )
    assert cents is None


@pytest.mark.asyncio
async def test_quote_shipping_details_honors_selected_method():
    addon = GelatoAddon()
    addon._config = {"default_currency": "USD"}
    addon._client = AsyncMock()
    addon._client.quote_order = AsyncMock(
        return_value={
            "quotes": [
                {
                    "shipmentMethods": [
                        {"type": "express", "name": "Express", "price": 25.0},
                        {"type": "normal", "name": "Standard", "price": 9.99},
                    ]
                }
            ]
        }
    )
    details = await addon.quote_shipping_details(
        [{"supplier_product_id": "uid-1", "quantity": 1}],
        {"country": "US"},
        selected_id="express",
    )
    assert details is not None
    assert details["cents"] == 2500
    assert details["selected_id"] == "express"


@pytest.mark.asyncio
async def test_create_order_sends_shipment_method_uid():
    addon = GelatoAddon()
    addon._config = {"default_currency": "USD", "auto_submit": True}
    addon._client = AsyncMock()
    addon._client.create_order = AsyncMock(
        return_value={"order": {"id": "ord-1", "status": "created"}}
    )
    result = await addon.create_order(
        [{"supplier_product_id": "uid-1", "quantity": 1}],
        {"line1": "1 Main", "city": "Austin", "postal_code": "78701", "country": "US"},
        shipping_method="express",
    )
    assert result["success"] is True
    payload = addon._client.create_order.await_args.args[0]
    assert payload["shipmentMethodUid"] == "express"
