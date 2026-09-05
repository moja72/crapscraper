from __future__ import annotations

from app.plugintheme_access_fallback import (
    _is_missing_product,
    _missing_product_failure,
)
from app.updates.models import UpdateError
from app.updates.sources import SourceFailure


def test_missing_product_is_detected_from_payload_error():
    error = SourceFailure(UpdateError(
        message="PluginTheme recusou o download ou retornou um artefato inválido.",
        technical_message="Produto não encontrado no payload público do PluginTheme.",
        code="source_download_failed",
        stage="validating",
        source="PluginTheme",
        requested_url="https://plugintheme.net/product/elementor-free-wordpress-page-builder",
        recoverable=True,
    ))
    assert _is_missing_product(error) is True
    normalized = _missing_product_failure(error, {"source_url": "https://plugintheme.net/product/elementor-free-wordpress-page-builder"})
    assert normalized.error.code == "source_product_missing"
    assert normalized.error.recoverable is False
    assert "não encontrado" in normalized.error.message.lower()


def test_missing_product_is_detected_from_404():
    error = SourceFailure(UpdateError(
        message="Falha HTTP.",
        code="source_download_failed",
        stage="validating",
        source="PluginTheme",
        http_status=404,
        recoverable=True,
    ))
    assert _is_missing_product(error) is True
