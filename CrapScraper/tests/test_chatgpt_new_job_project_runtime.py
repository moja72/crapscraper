from __future__ import annotations

from app.additions import chatgpt_new_job_project_runtime as runtime
from app.additions import chatgpt_playwright as legacy
from app.additions import chatgpt_background_route_recovery as route_recovery
from app.additions import strict_job_identity_runtime as strict


class FakePage:
    def __init__(self):
        self.url = "https://chatgpt.com/"
        self.visited = []

    def goto(self, url, **_kwargs):
        self.url = url
        self.visited.append(url)
        return None

    def wait_for_timeout(self, _ms):
        return None


def test_new_job_uses_canonical_project_landing_before_old_saved_conversation(monkeypatch):
    page = FakePage()
    saved = "https://chatgpt.com/g/g-p-project123/c/old-chat"
    written = {}

    monkeypatch.setattr(runtime.project_recovery, "saved_project_url", lambda *_args, **_kwargs: saved)

    def old_route_must_not_run(_page):
        raise AssertionError("old saved conversation route must not gate a new product")

    monkeypatch.setattr(route_recovery, "open_project", old_route_must_not_run)

    def direct(current_page, project_root):
        assert project_root == "https://chatgpt.com/g/g-p-project123/project"
        current_page.url = project_root
        return True

    monkeypatch.setattr(runtime, "_direct_blank_project", direct)
    monkeypatch.setattr(runtime, "_recover_blank_project", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(strict, "strict_job_conversation_fingerprint", lambda job_id: f"fp:{job_id}")

    def update(job_id, **values):
        written["job_id"] = job_id
        written.update(values)
        return values

    monkeypatch.setattr(legacy, "_update_job_state", update)

    runtime.create_project_local_chat(page, "job-new-product")

    assert written["job_id"] == "job-new-product"
    assert written["conversation_url"] == "https://chatgpt.com/g/g-p-project123/project"
    assert written["content_ready"] is False
    assert written["image_ready"] is False


def test_project_route_candidates_prefer_project_suffix():
    saved = "https://chatgpt.com/g/g-p-project123/c/old-chat"
    assert runtime._project_landing_url("g-p-project123") == (
        "https://chatgpt.com/g/g-p-project123/project"
    )
    assert runtime._project_route_candidates(saved) == [
        "https://chatgpt.com/g/g-p-project123/project",
        "https://chatgpt.com/g/g-p-project123",
    ]


def test_direct_blank_project_falls_back_to_legacy_root(monkeypatch):
    page = FakePage()
    project = "https://chatgpt.com/g/g-p-project123/project"

    monkeypatch.setattr(route_recovery, "_wait_signed_in", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        runtime,
        "_wait_for_blank_project_chat",
        lambda current_page, *_args, **_kwargs: current_page.url.endswith("g-p-project123"),
    )
    monkeypatch.setattr(runtime, "_click_project_local_new", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(route_recovery, "_try_project_new_button", lambda *_args, **_kwargs: False)

    assert runtime._direct_blank_project(page, project) is True
    assert page.visited[:2] == [
        "https://chatgpt.com/g/g-p-project123/project",
        "https://chatgpt.com/g/g-p-project123",
    ]


def test_failed_direct_root_recovers_by_project_token_without_legacy_open(monkeypatch):
    page = FakePage()
    saved = "https://chatgpt.com/g/g-p-project123/c/stale-chat"
    calls = {"recover": 0}
    written = {}

    monkeypatch.setattr(runtime.project_recovery, "saved_project_url", lambda *_args, **_kwargs: saved)
    monkeypatch.setattr(runtime, "_direct_blank_project", lambda *_args, **_kwargs: False)

    def recover(current_page, saved_url, project_root):
        calls["recover"] += 1
        assert saved_url == saved
        assert project_root == "https://chatgpt.com/g/g-p-project123/project"
        current_page.url = project_root
        return True

    monkeypatch.setattr(runtime, "_recover_blank_project", recover)
    monkeypatch.setattr(route_recovery, "open_project", lambda _page: (_ for _ in ()).throw(AssertionError("legacy open not expected")))
    monkeypatch.setattr(strict, "strict_job_conversation_fingerprint", lambda job_id: f"fp:{job_id}")
    monkeypatch.setattr(legacy, "_update_job_state", lambda _job_id, **values: written.update(values) or values)

    runtime.create_project_local_chat(page, "job-recovery")

    assert calls["recover"] == 1
    assert written["conversation_url"] == "https://chatgpt.com/g/g-p-project123/project"


def test_content_contract_version_is_v4():
    assert runtime._CONTENT_CONTRACT_VERSION == 4
