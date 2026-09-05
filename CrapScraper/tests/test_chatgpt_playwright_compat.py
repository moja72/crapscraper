from pathlib import Path

from app.additions import chatgpt_playwright as legacy
from app.additions import chatgpt_playwright_compat as compat
from app.additions import chatgpt_project_url_recovery as project_recovery
from app.additions import chatgpt_background_project_runtime as background_runtime


def _touch(path: Path, content: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_profile_dir_reuses_authenticated_legacy_profile(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SCRAPER_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SCRAPER_CHATGPT_PROFILE_DIR", raising=False)
    legacy_profile = tmp_path / "browser_profiles" / "chatgpt"
    automation_profile = tmp_path / "browser_profiles" / "chatgpt_automation"
    _touch(legacy_profile / "Default" / "Network" / "Cookies", b"legacy-session")
    automation_profile.mkdir(parents=True, exist_ok=True)

    assert compat.profile_dir() == legacy_profile.resolve()


def test_profile_dir_uses_new_profile_when_only_new_has_state(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SCRAPER_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SCRAPER_CHATGPT_PROFILE_DIR", raising=False)
    automation_profile = tmp_path / "browser_profiles" / "chatgpt_automation"
    _touch(automation_profile / "Default" / "Network" / "Cookies", b"current-session")

    assert compat.profile_dir() == automation_profile.resolve()


def test_explicit_profile_always_wins(monkeypatch, tmp_path: Path):
    explicit = tmp_path / "explicit"
    monkeypatch.setenv("SCRAPER_CHATGPT_PROFILE_DIR", str(explicit))
    assert compat.profile_dir() == explicit.resolve()


def test_modern_chatgpt_composer_selectors_are_supported():
    selectors = set(compat._COMPOSER_SELECTORS)
    assert "#prompt-textarea" in selectors
    assert "div.ProseMirror[contenteditable='true']" in selectors
    assert "div[data-lexical-editor='true'][contenteditable='true']" in selectors
    assert "main form textarea" in selectors


def test_compat_install_patches_runtime_globals(monkeypatch):
    monkeypatch.setattr(compat, "_INSTALLED", False)
    original_browser = legacy._browser
    original_composer = legacy._composer
    try:
        compat.install()
        assert legacy._browser is compat.browser
        assert legacy._composer is compat.composer
        assert legacy._open_project is compat.open_project
        assert legacy._open_job_conversation is compat.open_job_conversation
    finally:
        legacy._browser = original_browser
        legacy._composer = original_composer
        compat._INSTALLED = False


def test_project_url_recovery_rejects_chatgpt_root():
    assert project_recovery.is_project_candidate_url("https://chatgpt.com/") is False
    assert project_recovery.is_project_candidate_url("https://chatgpt.com") is False
    assert project_recovery.is_project_candidate_url("https://chatgpt.com/?temporary=1") is False


def test_project_url_recovery_accepts_concrete_chatgpt_pages():
    assert project_recovery.is_project_candidate_url("https://chatgpt.com/c/abc123") is True
    assert project_recovery.is_project_candidate_url("https://chatgpt.com/g/g-p-example/project") is True


def test_project_url_recovery_install_patches_compat_and_legacy(monkeypatch):
    monkeypatch.setattr(project_recovery, "_INSTALLED", False)
    original_compat_open_project = compat.open_project
    original_compat_bootstrap = compat.bootstrap
    original_compat_doctor = compat.doctor
    original_legacy_open_project = legacy._open_project
    original_legacy_bootstrap = legacy.bootstrap
    try:
        project_recovery.install()
        assert compat.open_project is project_recovery.open_project
        assert compat.bootstrap is project_recovery.bootstrap
        assert compat.doctor is project_recovery.doctor
        assert legacy._open_project is project_recovery.open_project
        assert legacy.bootstrap is project_recovery.bootstrap
    finally:
        compat.open_project = original_compat_open_project
        compat.bootstrap = original_compat_bootstrap
        compat.doctor = original_compat_doctor
        legacy._open_project = original_legacy_open_project
        legacy.bootstrap = original_legacy_bootstrap
        project_recovery._INSTALLED = False


def test_background_mode_is_default_on_windows(monkeypatch):
    monkeypatch.delenv("SCRAPER_CHATGPT_BROWSER_MODE", raising=False)
    monkeypatch.setattr(background_runtime.sys, "platform", "win32")
    assert background_runtime.browser_mode(True) == "background"
    assert background_runtime.browser_mode(None) == "background"


def test_background_mode_can_be_forced_to_headless(monkeypatch):
    monkeypatch.setenv("SCRAPER_CHATGPT_BROWSER_MODE", "headless")
    monkeypatch.setattr(background_runtime.sys, "platform", "win32")
    assert background_runtime.browser_mode(True) == "headless"


def test_bootstrap_requests_visible_browser_even_on_windows(monkeypatch):
    monkeypatch.delenv("SCRAPER_CHATGPT_BROWSER_MODE", raising=False)
    monkeypatch.setattr(background_runtime.sys, "platform", "win32")
    assert background_runtime.browser_mode(False) == "visible"


def test_project_route_matching_accepts_same_project_chat():
    saved = "https://chatgpt.com/g/g-p-abc123/c/old-chat"
    current = "https://chatgpt.com/g/g-p-abc123/c/new-chat"
    assert background_runtime._same_project_route(saved, current) is True
    assert background_runtime._same_project_route(saved, "https://chatgpt.com/") is False
    assert background_runtime._same_project_route(saved, "https://chatgpt.com/g/g-p-other/c/new-chat") is False