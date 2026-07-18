"""Unit tests for Gelato shipping-quote helpers."""

from app.addons.suppliers.gelato.client import (
    parse_quote_shipping_options,
    pick_quote_shipping_cents,
)
from app.addons.suppliers.shipping_quote import pick_shipping_option


def test_pick_quote_prefers_standard_type():
    quotes = [
        {
            "shipmentMethods": [
                {"type": "express", "name": "Express", "price": 20.0},
                {"type": "normal", "name": "Standard", "price": 12.5},
            ]
        }
    ]
    assert pick_quote_shipping_cents(quotes) == 1250


def test_pick_quote_cheapest_when_no_standard():
    quotes = [
        {
            "shipmentMethods": [
                {"type": "express", "name": "Express", "price": 20.0},
                {"type": "express", "name": "Priority", "price": 15.0},
            ]
        }
    ]
    assert pick_quote_shipping_cents(quotes) == 1500


def test_pick_quote_sums_across_facilities():
    quotes = [
        {"shipmentMethods": [{"type": "normal", "name": "Standard", "price": 10.0}]},
        {"shipmentMethods": [{"type": "normal", "name": "Standard", "price": 7.25}]},
    ]
    assert pick_quote_shipping_cents(quotes) == 1725


def test_pick_quote_empty_or_unpriced_returns_none():
    assert pick_quote_shipping_cents([]) is None
    assert pick_quote_shipping_cents([{"shipmentMethods": []}]) is None
    assert pick_quote_shipping_cents("nope") is None


def test_parse_and_select_express_across_facilities():
    quotes = [
        {
            "shipmentMethods": [
                {"type": "normal", "name": "Standard", "price": 10.0},
                {"type": "express", "name": "Express", "price": 20.0},
            ]
        },
        {
            "shipmentMethods": [
                {"type": "normal", "name": "Standard", "price": 7.0},
                {"type": "express", "name": "Express", "price": 18.0},
            ]
        },
    ]
    options = parse_quote_shipping_options(quotes)
    chosen = pick_shipping_option(options, selected_id="express")
    assert chosen is not None
    assert chosen["cents"] == 3800
