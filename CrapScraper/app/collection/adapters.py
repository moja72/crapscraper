from __future__ import annotations


def registry_payload() -> dict:
    from app.collection.legacy_core import settings

    return {
        "sites": [{"key": item.key, "label": item.label, "item_types": list(item.supported_item_types)} for item in settings.list_sites()],
        "item_types": [{"key": item.key, "label": item.label_plural} for item in settings.list_item_types()],
        "accounts": [{"key": item.key, "label": item.label, "item_types": list(item.supported_item_types), "sites": list(item.site_credentials)} for item in settings.list_accounts()],
        "modes": [{"key": key, "label": settings.get_run_mode_label(key)} for key in (settings.RUN_MODE_FULL, settings.RUN_MODE_CATEGORIES_ONLY, settings.RUN_MODE_LINKS_ONLY, settings.RUN_MODE_EXISTING_REVIEW)],
        "scope_modes": ["all", "range", "match", "selected"],
    }
