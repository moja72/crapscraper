from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from app.integrations.ultrapack_download import UltrapackDownloadError, UltrapackDownloader


class _Cookies(list):
    pass


class UltrapackDownloadDiagnosticsTests(unittest.TestCase):
    def response(self, status: int, url: str):
        return SimpleNamespace(
            status_code=status,
            url=url,
            history=[],
            headers={"Content-Type": "application/zip"},
        )

    def test_401_is_not_retried_with_the_same_one_time_url(self) -> None:
        session = SimpleNamespace(
            get=Mock(return_value=self.response(401, "https://files.example.test/download?token=secret")),
            headers={"Referer": "https://www.ultrapackv2.com/item/example/", "User-Agent": "test"},
            cookies=_Cookies(),
        )
        downloader = UltrapackDownloader(session, retries=3)
        with self.assertRaisesRegex(UltrapackDownloadError, "HTTP 401 em final_download"):
            downloader._get(
                "https://files.example.test/download?token=secret",
                stream=True,
                stage="final_download",
            )
        self.assertEqual(session.get.call_count, 1)

    def test_trace_redacts_query_values_and_cookie_values(self) -> None:
        cookie = SimpleNamespace(name="wordpress_logged_in", value="never-log", domain=".example.test", path="/")
        session = SimpleNamespace(
            get=Mock(return_value=self.response(200, "https://files.example.test/file.zip?nonce=private")),
            headers={"Referer": "https://www.ultrapackv2.com/item/example/?f=secret", "User-Agent": "test"},
            cookies=_Cookies([cookie]),
        )
        downloader = UltrapackDownloader(session)
        downloader._get("https://files.example.test/file.zip?nonce=private", stage="final_download")
        trace = downloader.request_trace[-1]
        rendered = repr(trace)
        self.assertNotIn("private", rendered)
        self.assertNotIn("never-log", rendered)
        self.assertIn("nonce=%5Bredacted%5D", trace["final_url"])
        self.assertEqual(trace["cookie_scope"], [{"name": "wordpress_logged_in", "domain": ".example.test", "path": "/"}])


if __name__ == "__main__":
    unittest.main()
