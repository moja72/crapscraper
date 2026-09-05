from __future__ import annotations

import pytest

from deploy.crapscraper_zip_helper import HelperError as ZipHelperError
from deploy.crapscraper_zip_helper import validate_file_name as validate_zip
from deploy.crapscraper_zip_permission_helper import HelperError as PermissionHelperError
from deploy.crapscraper_zip_permission_helper import validate_file_name as validate_permission


@pytest.mark.parametrize("name", [
    "Envira Gallery & Pagination + Addon [legacy].zip",
    "Foo's Plugin.zip",
    "Produto #123 @ 2.0.zip",
    "Plugin (Premium) - v2.zip",
])
def test_helpers_accept_safe_legacy_woocommerce_basenames(name):
    assert validate_zip(name) == name
    assert validate_permission(name) == name


@pytest.mark.parametrize("name", [
    "../x.zip",
    "a..b.zip",
    "/tmp/x.zip",
    "a/b.zip",
    "a\\b.zip",
    "bad\nname.zip",
    "not-a-zip.txt",
])
def test_helpers_keep_path_and_control_character_guards(name):
    with pytest.raises(ZipHelperError):
        validate_zip(name)
    with pytest.raises(PermissionHelperError):
        validate_permission(name)
