"""Unit tests for Gelato catalog normalization."""

from app.addons.suppliers.gelato.addon import GelatoAddon
from app.addons.suppliers.gelato.catalog import normalize_gelato_catalog


def test_gelato_normalizes_product_uid():
    items = normalize_gelato_catalog([{"productUid": "uid-1", "name": "Tee", "price": "19.99"}])
    assert len(items) == 1
    assert items[0].external_key == "gelato:uid-1"
    assert items[0].price_cents == 1999


def test_gelato_addon_identity():
    assert GelatoAddon.addon_id == "gelato"
    assert GelatoAddon().supports_catalog_sync() is True
