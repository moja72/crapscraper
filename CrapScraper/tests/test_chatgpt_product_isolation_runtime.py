from __future__ import annotations

from app.additions import chatgpt_background_route_recovery as route_recovery
from app.additions import chatgpt_playwright as legacy
from app.additions import chatgpt_playwright_compat as compat
from app.additions import chatgpt_playwright_image as image_runtime
from app.additions import chatgpt_product_isolation_runtime as isolation


def test_old_shared_chat_is_not_reusable_for_a_job():
    item = {
        "conversation_url": "https://chatgpt.com/g/g-p-example/c/shared-chat",
        "cache_until": 9999999999,
    }
    assert isolation.conversation_reusable(item, "job-1") is False


def test_isolated_chat_requires_exact_job_fingerprint():
    item = {
        "conversation_url": "https://chatgpt.com/g/g-p-example/c/job-chat",
        "isolated_chat_version": 1,
        "isolated_chat_fingerprint": isolation.job_conversation_fingerprint("job-1"),
    }
    assert isolation.conversation_reusable(item, "job-1") is True
    assert isolation.conversation_reusable(item, "job-2") is False


def test_image_candidate_without_conversation_turn_locator_is_rejected():
    assert isolation.candidate_belongs_to_current_prompt_turn({}, "CSIMG-ABC") is False


def test_install_patches_both_dynamic_and_imported_image_conversation_openers(monkeypatch):
    monkeypatch.setattr(isolation, "_INSTALLED", False)
    original_legacy = legacy._open_job_conversation
    original_compat = compat.open_job_conversation
    original_route = route_recovery.open_job_conversation
    original_image = image_runtime._open_job_conversation
    original_binding = image_runtime._IMAGE_BINDING_VERSION
    original_after = image_runtime._candidate_is_after_marker
    try:
        isolation.install()
        assert legacy._open_job_conversation is isolation.open_job_conversation
        assert image_runtime._open_job_conversation is isolation.open_job_conversation
        assert image_runtime._IMAGE_BINDING_VERSION == 3
        assert image_runtime._candidate_is_after_marker is isolation.candidate_belongs_to_current_prompt_turn
    finally:
        legacy._open_job_conversation = original_legacy
        compat.open_job_conversation = original_compat
        route_recovery.open_job_conversation = original_route
        image_runtime._open_job_conversation = original_image
        image_runtime._IMAGE_BINDING_VERSION = original_binding
        image_runtime._candidate_is_after_marker = original_after
        isolation._INSTALLED = False
