from __future__ import annotations

import app.comparison as comparison
import app.decision_cache_policy as policy


def test_invalidate_comparison_cache_clears_cached_payload():
    comparison._CACHE_KEY = (("a", 1, 1), ("b", 1, 1))
    comparison._CACHE_PAYLOAD = {"rows": [{"decision": "pending"}]}

    policy._invalidate_comparison_cache()

    assert comparison._CACHE_KEY is None
    assert comparison._CACHE_PAYLOAD is None
