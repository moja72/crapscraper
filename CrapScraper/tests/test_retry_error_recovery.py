from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path

from app.legacy_permission_recovery import _is_legacy_permission_failure
from app.updates.models import UpdateError
from app.updates.sources import SourceFailure
from app.updates.ultrapack_source_recovery import _error_requires_session_refresh


def test_ultrapack_http_2xx_non_zip_is_treated_as_expired_one_shot_link():
    error = SourceFailure(UpdateError(
        message="UltraPackV2 recusou o download ou retornou um artefato inválido.",
        technical_message=(
            "A resposta HTTP 2xx foi recebida, mas o conteúdo não é um ZIP válido. "
            "Content-Type informado: application/octet-stream."
        ),
        code="source_download_failed",
        stage="downloading",
        source="UltraPackV2",
        http_status=200,
        content_type="application/octet-stream",
        recoverable=True,
    ))
    assert _error_requires_session_refresh(error) is True


def test_ultrapack_credit_failure_is_not_retried_as_expired_link():
    error = SourceFailure(UpdateError(
        message="Créditos insuficientes.",
        technical_message="credits: 0",
        code="insufficient_credits",
        stage="downloading",
        source="UltraPackV2",
        http_status=200,
        recoverable=True,
    ))
    assert _error_requires_session_refresh(error) is False


def test_legacy_permission_failure_matches_real_backup_error():
    message = (
        'Helper remoto recusou a operacao: {"error": "[Errno 13] Permission denied: '
        "'/home/plugintema.com/downloads/301-redirects-pro.zip'\", \"ok\": false, "
        '"operation": "backup"}'
    )
    assert _is_legacy_permission_failure(RuntimeError(message)) is True
    assert _is_legacy_permission_failure(RuntimeError("Permission denied while downloading")) is False


def test_bootstrap_installs_current_retry_after_runtime_consistency():
    source = (Path(__file__).parents[1] / "app" / "bootstrap.py").read_text(encoding="utf-8")
    runtime = source.index("install_update_runtime_consistency()")
    current = source.index("install_current_app_recovery()")
    permissions = source.index("install_legacy_permission_recovery()")
    assert runtime < current < permissions


def _load_permission_helper():
    path = Path(__file__).parents[2] / "deploy" / "crapscraper_zip_permission_helper.py"
    spec = importlib.util.spec_from_file_location("crapscraper_zip_permission_helper", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_permission_helper_requires_exact_hash_before_metadata_repair(tmp_path, monkeypatch):
    helper = _load_permission_helper()
    target = tmp_path / "legacy-theme.zip"
    target.write_bytes(b"legacy zip bytes")
    expected = hashlib.sha256(target.read_bytes()).hexdigest()

    monkeypatch.setattr(helper, "DOWNLOAD_ROOT", tmp_path)
    monkeypatch.setattr(helper, "production_identity", lambda: (os.getuid(), os.getgid()))

    result = helper.repair(target.name, expected)
    assert result["ok"] is True
    assert result["sha256"] == expected
    assert hashlib.sha256(target.read_bytes()).hexdigest() == expected


def test_permission_helper_refuses_changed_file(tmp_path, monkeypatch):
    helper = _load_permission_helper()
    target = tmp_path / "legacy-theme.zip"
    target.write_bytes(b"changed")

    monkeypatch.setattr(helper, "DOWNLOAD_ROOT", tmp_path)
    monkeypatch.setattr(helper, "production_identity", lambda: (os.getuid(), os.getgid()))

    try:
        helper.repair(target.name, "0" * 64)
    except helper.HelperError as error:
        assert "SHA-256 mismatch" in str(error)
    else:
        raise AssertionError("permission repair must reject a different SHA-256")
