"""Keep modular tests off real state and restore runtime installers between tests.

Several integration tests install class adapters process-wide without undoing
them. A test of the base gateway must not inherit a prior test's catalog policy.
The production bootstrap contract is exercised explicitly by integration tests.
"""
import sys
import types
import copy

import pytest


@pytest.fixture(autouse=True)
def isolated_modular_state(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRAPER_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SCRAPER_COMPARISON_DECISIONS_DB_PATH", str(tmp_path / "decisions.sqlite3"))
    monkeypatch.setenv("SCRAPER_UPDATE_IMPORT_LEGACY", "0")
    monkeypatch.setenv("SCRAPER_ADDITION_IMPORT_LEGACY", "0")
    modules = {name: module for name, module in list(sys.modules.items())
               if name.startswith("app.") and isinstance(module, types.ModuleType)}
    snapshots = {module: dict(vars(module)) for module in modules.values()}
    for snapshot in snapshots.values():
        for key, value in list(snapshot.items()):
            if not key.startswith("__") and isinstance(value, (dict, list, set)):
                try:
                    snapshot[key] = copy.deepcopy(value)
                except (TypeError, ValueError):
                    snapshot[key] = copy.copy(value)
    classes = {value for module in modules.values() for value in vars(module).values()
               if isinstance(value, type) and value.__module__.startswith("app.")}
    class_snapshots = {cls: dict(vars(cls)) for cls in classes}
    yield
    for cls, snapshot in class_snapshots.items():
        for key in set(vars(cls)) - snapshot.keys():
            if key not in {"__dict__", "__weakref__"}:
                delattr(cls, key)
        for key, value in snapshot.items():
            if key not in {"__dict__", "__weakref__"} and vars(cls).get(key) is not value:
                setattr(cls, key, value)
    for module, snapshot in snapshots.items():
        for key in set(vars(module)) - snapshot.keys():
            if not key.startswith("__"):
                delattr(module, key)
        for key, value in snapshot.items():
            if not key.startswith("__"):
                setattr(module, key, value)
    for name, module in list(sys.modules.items()):
        if name.startswith("app.") and name not in modules and hasattr(module, "_INSTALLED"):
            module._INSTALLED = False
