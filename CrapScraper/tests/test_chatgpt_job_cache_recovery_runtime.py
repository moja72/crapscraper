import time
from types import SimpleNamespace
import pytest
from app.additions import chatgpt_job_cache_recovery_runtime as runtime
from app.additions.repository import AdditionRepository
from app.additions.executor import AdditionExecutor
from tests.addition_fakes import approval


class FakePage:
    def __init__(self, result):
        self.result = result
    def evaluate(self, script):
        return self.result


@pytest.mark.parametrize(("result", "expected"), [
    ({"ok": True, "users": 0}, 0), ({"ok": True, "users": 2}, 2),
    ({"ok": False, "users": -1}, -1), (None, -1)])
def test_safe_user_turn_count(result, expected):
    assert runtime._safe_user_turn_count(FakePage(result)) == expected


def bind(job):
    runtime.strict.bind_job_identity(job)
    return runtime.legacy._update_job_state(job["job_id"],
        conversation_url="https://chatgpt.com/g/g-p-project/c/chat-" + job["job_id"],
        isolated_chat_version=runtime.strict._ISOLATION_VERSION,
        isolated_chat_fingerprint=runtime.strict.strict_job_conversation_fingerprint(job["job_id"]),
        cache_until=int(time.time()) + 600)


@pytest.fixture
def jobs(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRAPER_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SCRAPER_CHATGPT_AUTOMATION_MODE", "playwright")
    repo = AdditionRepository(tmp_path)
    repo.materialize([approval("A"), approval("B")])
    return repo, [repo.get(repo.job_id(key)) for key in ("A", "B")]


def test_sqlite_restart_restores_same_job_proof(jobs):
    repo, (a, b) = jobs
    proof = bind(a)
    executor = AdditionExecutor(repo)
    persisted = executor._persist_chatgpt_cache(a["job_id"])
    assert persisted["chatgpt_provenance"]["product_identity_fingerprint"] == proof["product_identity_fingerprint"]
    runtime.legacy._write_state({})
    restarted = AdditionRepository(repo.path.parent).get(a["job_id"])
    assert runtime._restore_exact_job_chat(restarted)
    assert runtime.legacy._job_state(a["job_id"])["conversation_url"] == proof["conversation_url"]
    assert runtime.legacy._job_state(b["job_id"]) == {}


def test_b_cannot_restore_a_proof_even_when_runtime_state_was_lost(jobs):
    repo, (a, b) = jobs
    proof = bind(a)
    runtime.legacy._write_state({})
    stolen = {**b, "chatgpt_conversation_url": proof["conversation_url"], "chatgpt_provenance": proof}
    assert not runtime._restore_exact_job_chat(stolen)
    assert not runtime.legacy._job_state(b["job_id"]).get("conversation_url")


def test_url_without_provenance_is_not_promoted(jobs):
    repo, (a, _) = jobs
    a["chatgpt_conversation_url"] = "https://chatgpt.com/g/g-p-project/c/unknown"
    assert not runtime._restore_exact_job_chat(a)


def test_expired_and_changed_identity_fail_closed(jobs):
    repo, (a, _) = jobs
    proof = bind(a)
    proof["cache_until"] = int(time.time()) - 1
    assert not runtime._restore_exact_job_chat({**a, "chatgpt_provenance": proof})
    assert not runtime._restore_exact_job_chat({**a, "product_name": "Changed"})
    assert not runtime.legacy._job_state(a["job_id"]).get("conversation_url")


def test_image_restores_provenance_before_browser(monkeypatch):
    calls = []
    monkeypatch.setattr(runtime, "_restore_exact_job_chat", lambda job: calls.append("restore"))
    monkeypatch.setattr(runtime, "_ORIGINAL_IMAGE_GENERATE", lambda self, job: calls.append("image") or "image.webp")
    assert runtime._image_generate(SimpleNamespace(), {"job_id": "a"}) == "image.webp"
    assert calls == ["restore", "image"]
