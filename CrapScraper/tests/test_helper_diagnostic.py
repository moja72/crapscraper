from __future__ import annotations

from app.helper_diagnostic import (
    is_legacy_helper_capabilities_failure,
    normalize_helper_check,
)


def test_legacy_helper_capabilities_failure_is_classified():
    message = """{"error": "argument operation: invalid choice: 'capabilities' (choose from 'inspect', 'probe-setgid', 'prepare', 'backup', 'install', 'rollback', 'cleanup')", "ok": false, "operation": "parse"}"""

    assert is_legacy_helper_capabilities_failure(message) is True
    result = normalize_helper_check({"ok": False, "message": message})

    assert result["ok"] is False
    assert result["helper_version"] == 1
    assert result["required_helper_version"] == 2
    assert result["missing_operations"] == ["install-missing", "rollback-missing"]
    assert "v1 detectado" in result["message"]
    assert "versão 2" in result["message"]
    assert "invalid choice" not in result["message"]


def test_unrelated_helper_failure_is_preserved():
    original = {"ok": False, "message": "Falha de permissão SSH"}
    assert normalize_helper_check(original) == original


def test_successful_helper_check_is_preserved():
    original = {"ok": True, "message": "helper v2 validado", "helper_version": 2}
    assert normalize_helper_check(original) == original
