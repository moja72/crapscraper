from __future__ import annotations

import unittest

from app import settings


class SiteItemTypeSupportTests(unittest.TestCase):
    def test_ultrapack_does_not_offer_combined_plugin_theme_type(self) -> None:
        self.assertEqual(
            settings.get_site("ultrapackv2").supported_item_types,
            ("plugin", "theme", "template"),
        )
        self.assertFalse(settings.site_supports_item_type("ultrapackv2", "plugin_theme"))

    def test_plugintheme_keeps_combined_type_as_its_only_option(self) -> None:
        self.assertEqual(
            settings.get_site("plugintheme").supported_item_types,
            ("plugin_theme",),
        )


if __name__ == "__main__":
    unittest.main()
