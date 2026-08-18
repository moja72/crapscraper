from __future__ import annotations

from typing import Any, Callable

import app.comparison as comparison
import app.web as web

_INSTALLED = False
_BASE_SAVE_DECISION: Callable[..., Any] | None = None
_BASE_SAVE_DECISIONS_BULK: Callable[..., Any] | None = None
_BASE_RESET_DECISION: Callable[..., Any] | None = None


def _invalidate_comparison_cache() -> None:
    with comparison._CACHE_LOCK:
        comparison._CACHE_KEY = None
        comparison._CACHE_PAYLOAD = None


def _save_decision(*args: Any, **kwargs: Any) -> Any:
    result = _BASE_SAVE_DECISION(*args, **kwargs)
    _invalidate_comparison_cache()
    return result


def _save_decisions_bulk(*args: Any, **kwargs: Any) -> Any:
    result = _BASE_SAVE_DECISIONS_BULK(*args, **kwargs)
    _invalidate_comparison_cache()
    return result


def _reset_decision(*args: Any, **kwargs: Any) -> Any:
    result = _BASE_RESET_DECISION(*args, **kwargs)
    _invalidate_comparison_cache()
    return result


def install_decision_cache_policy() -> None:
    global _INSTALLED, _BASE_SAVE_DECISION, _BASE_SAVE_DECISIONS_BULK, _BASE_RESET_DECISION
    if _INSTALLED:
        return

    # app.web importou as funções diretamente; as rotas HTTP usam estas referências.
    _BASE_SAVE_DECISION = web.save_decision
    _BASE_SAVE_DECISIONS_BULK = web.save_decisions_bulk
    _BASE_RESET_DECISION = web.reset_decision

    web.save_decision = _save_decision
    web.save_decisions_bulk = _save_decisions_bulk
    web.reset_decision = _reset_decision
    _INSTALLED = True
