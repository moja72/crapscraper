from pathlib import Path

from app.additions import chatgpt_playwright as legacy
from app.additions import chatgpt_playwright_compat as compat


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
