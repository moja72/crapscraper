from app.additions import chatgpt_background_route_recovery as recovery
from app.additions import chatgpt_playwright as legacy
from app.additions import chatgpt_playwright_compat as compat
from app.additions import chatgpt_project_url_recovery as project_recovery


class _Anchor:
    def __init__(self, href):
        self.href = href

    def get_attribute(self, name):
        assert name == "href"
        return self.href


class _Nodes:
    def __init__(self, hrefs):
        self.hrefs = list(hrefs)

    def count(self):
        return len(self.hrefs)

    def nth(self, index):
        return _Anchor(self.hrefs[index])


class _Page:
    def __init__(self, hrefs=None):
        self.url = "https://chatgpt.com/"
        self.hrefs = list(hrefs or [])
        self.visited = []

    def locator(self, _selector):
        return _Nodes(self.hrefs)

    def goto(self, url, **_kwargs):
        self.url = url
        self.visited.append(url)

    def wait_for_timeout(self, _ms):
        return None


def test_project_chat_hrefs_keep_only_saved_project_and_deduplicate():
    page = _Page(
        [
            "/g/g-p-abc/c/one",
            "/g/g-p-abc/c/one",
            "https://chatgpt.com/g/g-p-abc/c/two",
            "/g/g-p-other/c/wrong",
            "/c/global-chat",
        ]
    )
    assert recovery._project_chat_hrefs(page, "g-p-abc") == [
        "https://chatgpt.com/g/g-p-abc/c/one",
        "https://chatgpt.com/g/g-p-abc/c/two",
    ]


def test_project_landing_candidates_prefer_project_suffix():
    assert recovery._project_landing_candidates("G-P-ABC") == [
        "https://chatgpt.com/g/g-p-abc/project",
        "https://chatgpt.com/g/g-p-abc",
    ]


def test_project_token_recovery_prefers_canonical_project_landing(monkeypatch):
    saved = "https://chatgpt.com/g/g-p-abc/c/stale-chat"
    page = _Page()
    monkeypatch.setattr(recovery, "_wait_signed_in", lambda _page, _timeout=0: True)
    monkeypatch.setattr(recovery, "_project_ready", lambda _page, expected, _timeout=0: expected.endswith("g-p-abc"))

    assert recovery._recover_from_project_token(page, saved) is True
    assert page.visited[0] == "https://chatgpt.com/g/g-p-abc/project"


def test_stale_job_conversation_falls_back_to_project_recovery(monkeypatch):
    page = _Page()
    page.url = "https://chatgpt.com/g/g-p-abc/c/recovered"
    writes = []

    monkeypatch.setattr(
        legacy,
        "_job_state",
        lambda _job_id: {"conversation_url": "https://chatgpt.com/g/g-p-abc/c/stale"},
    )
    monkeypatch.setattr(
        project_recovery,
        "saved_project_url",
        lambda *_args, **_kwargs: "https://chatgpt.com/g/g-p-abc/c/bootstrap",
    )
    monkeypatch.setattr(recovery, "_goto_project_candidate", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(recovery, "open_project", lambda _page: None)
    monkeypatch.setattr(legacy, "_update_job_state", lambda job_id, **values: writes.append((job_id, values)))

    recovery.open_job_conversation(page, "job-77")

    assert writes
    assert writes[0][0] == "job-77"
    assert writes[0][1]["conversation_url"].endswith("/recovered")


def test_install_patches_project_and_job_openers(monkeypatch):
    monkeypatch.setattr(recovery, "_INSTALLED", False)
    old = (
        compat.open_project,
        legacy._open_project,
        project_recovery.open_project,
        recovery.background.open_project,
        compat.open_job_conversation,
        legacy._open_job_conversation,
    )
    try:
        recovery.install()
        assert compat.open_project is recovery.open_project
        assert legacy._open_project is recovery.open_project
        assert project_recovery.open_project is recovery.open_project
        assert recovery.background.open_project is recovery.open_project
        assert compat.open_job_conversation is recovery.open_job_conversation
        assert legacy._open_job_conversation is recovery.open_job_conversation
    finally:
        (
            compat.open_project,
            legacy._open_project,
            project_recovery.open_project,
            recovery.background.open_project,
            compat.open_job_conversation,
            legacy._open_job_conversation,
        ) = old
        recovery._INSTALLED = False
