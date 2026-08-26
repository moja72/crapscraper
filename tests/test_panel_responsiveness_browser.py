from __future__ import annotations

import json
import re
import time
import unittest
from urllib.request import urlopen

from playwright.sync_api import sync_playwright


PANEL_URL = "http://127.0.0.1:8765/"


class PanelResponsivenessBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch(headless=True)
        except Exception as exc:  # pragma: no cover - local browser dependency
            cls.playwright.stop()
            raise unittest.SkipTest(f"Chromium indisponível: {exc}") from exc

    @classmethod
    def tearDownClass(cls) -> None:
        cls.browser.close()
        cls.playwright.stop()

    def test_panel_boot_and_tabs_remain_responsive_for_30_seconds(self) -> None:
        page = self.browser.new_page(viewport={"width": 1440, "height": 900})
        events: dict[str, list[str]] = {
            "console_error": [],
            "console_warn": [],
            "pageerror": [],
            "requestfailed": [],
        }
        page.on("console", lambda msg: events[f"console_{msg.type}"].append(msg.text) if f"console_{msg.type}" in events else None)
        page.on("pageerror", lambda error: events["pageerror"].append(str(error)))
        page.on("requestfailed", lambda request: events["requestfailed"].append(f"{request.method} {request.url}: {request.failure}"))
        page.add_init_script(
            """
            window.__csSmoke = {timeouts: 0, intervals: 0, frames: 0, longTasks: []};
            setTimeout(() => window.__csSmoke.timeouts++, 1000);
            setInterval(() => window.__csSmoke.intervals++, 250);
            const frame = () => { window.__csSmoke.frames++; requestAnimationFrame(frame); };
            requestAnimationFrame(frame);
            if (window.PerformanceObserver) {
              try {
                new PerformanceObserver(list => {
                  for (const item of list.getEntries()) window.__csSmoke.longTasks.push(Math.round(item.duration));
                }).observe({entryTypes: ["longtask"]});
              } catch (_error) {}
            }
            window.addEventListener("unhandledrejection", event => {
              window.__csSmoke.unhandled = String(event.reason || "unknown");
            });
            """
        )
        started = time.monotonic()
        page.goto(PANEL_URL, wait_until="domcontentloaded", timeout=30_000)

        snapshots = []
        for target in (0, 1, 3, 5):
            remaining = target - (time.monotonic() - started)
            if remaining > 0:
                page.wait_for_timeout(int(remaining * 1000))
            snapshots.append(page.evaluate("t => ({t, ready: document.readyState, smoke: {...window.__csSmoke}, active: document.querySelector('.tab-button.active')?.id || '', processes: !!document.querySelector('#cs_processes_button'), credits: document.querySelector('#cs_download_credits')?.innerText || ''})", target))

        tab_ids = [
            "tab_btn_comparacao",
            "tab_btn_atualizacoes",
            "tab_btn_adicoes",
            "tab_btn_loja",
            "tab_btn_principal",
        ]
        click_results = []
        for tab_id in tab_ids:
            locator = page.locator(f"#{tab_id}")
            locator.click(timeout=5_000)
            page.wait_for_timeout(150)
            click_results.append({"id": tab_id, "active": locator.get_attribute("aria-selected") == "true"})

        page.locator("#cs_processes_button").click(timeout=5_000)
        self.assertFalse(page.locator("#cs_processes_overlay").evaluate("node => node.classList.contains('hidden')"))
        page.locator("#cs_processes_close").click(timeout=5_000)

        remaining = 30 - (time.monotonic() - started)
        if remaining > 0:
            page.wait_for_timeout(int(remaining * 1000))
        final = page.evaluate("({ready: document.readyState, smoke: {...window.__csSmoke}, active: document.querySelector('.tab-btn.is-active')?.id || '', processes: !!document.querySelector('#cs_processes_button'), processGroup: !!document.querySelector('#cs_processes_header_group'), credits: document.querySelector('#cs_download_credits')?.innerText || '', updateModern: !!document.querySelector('#cs_canonical_update_execute'), additionModern: !!document.querySelector('#cs_canonical_addition_execute')})")
        diagnostic = {"events": events, "snapshots": snapshots, "clicks": click_results, "final": final}
        print("PANEL_SMOKE=" + json.dumps(diagnostic, ensure_ascii=True))

        self.assertFalse(events["pageerror"], diagnostic)
        self.assertGreaterEqual(final["smoke"]["timeouts"], 1, diagnostic)
        self.assertGreaterEqual(final["smoke"]["intervals"], 20, diagnostic)
        self.assertGreaterEqual(final["smoke"]["frames"], 30, diagnostic)
        self.assertTrue(all(item["active"] for item in click_results), diagnostic)
        self.assertTrue(final["updateModern"], diagnostic)
        self.assertTrue(final["additionModern"], diagnostic)
        self.assertTrue(final["processes"], diagnostic)
        self.assertTrue(final["processGroup"], diagnostic)
        page.close()

    def diagnose_first_blocking_script(self) -> None:
        html = urlopen(PANEL_URL, timeout=15).read().decode("utf-8")
        script_re = re.compile(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", re.I | re.S)
        blocks = list(script_re.finditer(html))
        results = []

        for cutoff in (16, 24, 28, 29, 32, 40, 48, 56, 59, 60, 61, 62, 63):
            index = 0

            def suppress_after_cutoff(match: re.Match[str]) -> str:
                nonlocal index
                index += 1
                if index <= cutoff:
                    return match.group(0)
                return f"<script type=\"application/x-suppressed\" data-original-index=\"{index}\"></script>"

            reduced = script_re.sub(suppress_after_cutoff, html)
            page = self.browser.new_page()
            page.route(PANEL_URL, lambda route, _request, body=reduced: route.fulfill(status=200, content_type="text/html; charset=utf-8", body=body))
            started = time.monotonic()
            try:
                page.goto(PANEL_URL, wait_until="domcontentloaded", timeout=4_000)
                state = "alive"
            except Exception as exc:
                state = type(exc).__name__
            elapsed = round(time.monotonic() - started, 2)
            results.append({"cutoff": cutoff, "state": state, "elapsed": elapsed})
            page.close()

        labels = []
        for index, block in enumerate(blocks, 1):
            attrs = block.group("attrs")
            marker = re.search(r"\b(data-[\w-]+)", attrs)
            src = re.search(r"\bsrc=[\"']([^\"']+)", attrs)
            labels.append({"index": index, "src": src.group(1) if src else "", "marker": marker.group(1) if marker else "", "bytes": len(block.group("body"))})
        print("SCRIPT_CUTOFFS=" + json.dumps(results))
        print("SCRIPT_LABELS=" + json.dumps(labels))

    def diagnose_simple_flow_conflict(self) -> None:
        html = urlopen(PANEL_URL, timeout=15).read().decode("utf-8")
        script_re = re.compile(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", re.I | re.S)
        results = []
        for suppressed_index in range(28, 62):
            index = 0

            def suppress_one(match: re.Match[str]) -> str:
                nonlocal index
                index += 1
                if index == suppressed_index or index > 62:
                    return f"<script type=\"application/x-suppressed\" data-original-index=\"{index}\"></script>"
                return match.group(0)

            reduced = script_re.sub(suppress_one, html)
            page = self.browser.new_page()
            page.route(PANEL_URL, lambda route, _request, body=reduced: route.fulfill(status=200, content_type="text/html; charset=utf-8", body=body))
            try:
                page.goto(PANEL_URL, wait_until="domcontentloaded", timeout=2_500)
                state = "alive"
            except Exception as exc:
                state = type(exc).__name__
            results.append({"suppressed": suppressed_index, "state": state})
            page.close()
        print("SIMPLE_FLOW_CONFLICTS=" + json.dumps(results))

    def test_final_html_has_one_canonical_script_and_no_legacy_addition_renderers(self) -> None:
        html = urlopen(PANEL_URL, timeout=15).read().decode("utf-8")
        scripts = list(re.finditer(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", html, re.I | re.S))
        bodies = [match.group("body").strip() for match in scripts if match.group("body").strip()]
        attributes = "\n".join(match.group("attrs") for match in scripts)
        self.assertEqual(len(bodies), len(set(bodies)))
        self.assertEqual(html.count("data-operational-history-shared-v12"), 1)
        self.assertEqual(html.count("data-operational-simple-flow-v3"), 1)
        self.assertNotIn("data-new-product-workflow-script", attributes)
        self.assertNotIn("data-addition-one-click", attributes)
        self.assertNotIn("data-addition-chatgpt-assist", attributes)
        self.assertLess(html.index("data-update-technical-log-fix"), html.index("data-operational-simple-flow-v3"))


if __name__ == "__main__":
    unittest.main()
