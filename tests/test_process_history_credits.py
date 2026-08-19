from app.process_history_credits_policy import _extract_credit_numbers


def test_extracts_remaining_and_limit_from_mapping():
    result = _extract_credit_numbers({"data": {"remainingDownloads": 17, "downloadLimit": 50}})
    assert result == {"remaining": 17, "limit": 50, "used": 33}


def test_derives_remaining_from_used_downloads():
    result = _extract_credit_numbers({"downloads": {"used": 9, "limit": 25}})
    assert result == {"used": 9, "limit": 25, "remaining": 16}


def test_extracts_compact_credit_pair_from_html():
    result = _extract_credit_numbers("<div>Downloads restantes: <strong>17/50</strong></div>")
    assert result == {"remaining": 17, "limit": 50, "used": 33}


def test_used_pair_is_converted_to_remaining():
    result = _extract_credit_numbers("<div>Downloads usados hoje: 12/50</div>")
    assert result == {"remaining": 38, "limit": 50, "used": 12}
