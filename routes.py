"""Gelato addon routes."""

from typing import Any

from app.addons.suppliers.shared_routes import build_supplier_routers


def _parse_form(form: Any) -> tuple[dict[str, Any], bool]:
    return {
        "api_key": form.get("api_key", ""),
        "is_active": form.get("is_active") == "on",
        "auto_submit": form.get("auto_submit") == "on",
        "default_currency": (form.get("default_currency") or "USD").upper()[:3],
        "shipment_method_uid": form.get("shipment_method_uid", ""),
    }, form.get("is_active") == "on"


admin_router, api_router, _env = build_supplier_routers(
    "gelato",
    template_name="config.html",
    page_title="Gelato",
    parse_config_form=_parse_form,
)
