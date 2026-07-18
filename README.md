# Gelato (`gelato`)

Global print-on-demand via Gelato API.

## Overview

| | |
|---|---|
| Addon ID | `gelato` |
| Category | supplier |
| Version | 1.0.0 |
| Category guide | [../README.md](../README.md) |
| Fulfillment key | `gelato` |

Multiple suppliers can be enabled at the same time. Fulfillment runs when an order becomes **paid**.

## Enable and configure

1. Install this package under `app/addons/suppliers/gelato/`
2. Open **Admin → Suppliers → Gelato** at `/admin/suppliers/gelato`
3. Enter API credentials and enable the addon

## Configuration schema

| Field | Type | Description |
|-------|------|-------------|
| `api_key` | secret | Gelato API key |
| `is_active` | bool | Whether the addon is active |
| `auto_submit` | bool | Submit orders vs save as draft |
| `default_currency` | string | Default currency (3-letter code, default USD) |
| `shipment_method_uid` | string | Optional default shipping method UID |

## Routes

### Public API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/suppliers/gelato/products` | List catalog products |

### Admin

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/suppliers/gelato` | Config form |
| POST | `/admin/suppliers/gelato/save` | Save config |
| POST | `/admin/suppliers/gelato/sync` | Trigger catalog sync |

## Core integration

- **Variant supplier fields:** paid-order fulfillment reads Gelato IDs from each **ProductVariant** row
- **Fulfillment:** creates Gelato order; respects `auto_submit` for draft vs submitted
- **Checkout shipping:** core calls `quote_shipping()` → `POST /v4/orders:quote` for Gelato line items (prefers a normal/standard method, else cheapest; sums per fulfillment facility). Unquoted or failed quotes fall back to Site Settings like any other supplier.
- **Grouping:** line items grouped by fulfillment key `gelato`

## Variant supplier fields

| Field | Description |
|-------|-------------|
| `supplier_addon_id` | `gelato` |
| `supplier_product_id` | Gelato `productUid` |

Catalog sync sets these on each imported variant.

## Catalog sync

Supported. Admin sync at `/admin/suppliers/gelato` or `POST /api/v1/admin/suppliers/gelato/sync`.

**Import model:** grouped products with one variant per Gelato SKU/uid.

| Key | Format |
|-----|--------|
| Variant dedup key | `gelato:{productUid}` |

**Prerequisites:**

- Catalog is paginated by offset from the Gelato product catalog API.

## Provider setup

- Obtain API key from Gelato Dashboard.

## Package layout

```
gelato/
├── README.md
├── addon.py
├── catalog.py
├── client.py
├── routes.py
└── templates/
```

## See also

- [Supplier addon development](../README.md)
- [Oshkelosh addon guide](../../README.md)
