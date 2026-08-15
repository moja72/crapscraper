import unittest

from app.browser import AuthenticationState, determine_authentication_state, get_plugintheme_profile_dir
from app.integrations.plugintheme_download import PluginThemeDownloader


class _Page:
    def __init__(self, url="https://plugintheme.net/"):
        self.url = url

    async def query_selector(self, selector):
        if "logout" in selector:
            return object()
        return None


class PluginThemeHybridTests(unittest.IsolatedAsyncioTestCase):
    def test_access_parser_accepts_explicit_current_api_variants_only(self):
        self.assertTrue(PluginThemeDownloader.access_allowed({"data": {"can_download": True}}))
        self.assertTrue(PluginThemeDownloader.access_allowed({"result": {"hasAccess": 1}}))
        self.assertFalse(PluginThemeDownloader.access_allowed({"success": True}))
        self.assertFalse(PluginThemeDownloader.access_allowed({"allowed": False}))

    def test_profile_is_dedicated_and_sanitized(self):
        path = get_plugintheme_profile_dir("../Conta Principal")
        self.assertEqual(path.name, "conta-principal")
        self.assertEqual(path.parent.name, "plugintheme")

    async def test_authenticated_signal_wins_without_url_assumption(self):
        state = await determine_authentication_state(_Page())
        self.assertEqual(state, AuthenticationState.AUTHENTICATED)

    async def test_login_url_without_form_is_not_authenticated(self):
        page = _Page("https://plugintheme.net/pt-BR/auth/login")
        page.query_selector = lambda _selector: _async_none()
        state = await determine_authentication_state(page)
        self.assertEqual(state, AuthenticationState.NOT_AUTHENTICATED)


async def _async_none():
    return None
