from __future__ import annotations

from app.additions import chatgpt_writable_composer_runtime as runtime
from app.additions import chatgpt_playwright_compat as compat


class FakeNode:
    def __init__(self, *, disabled=False, editable=True):
        self.disabled = disabled
        self.editable = editable

    def is_visible(self):
        return True

    def get_attribute(self, name):
        if name == "disabled":
            return "" if self.disabled else None
        if name in {"aria-disabled", "readonly", "contenteditable"}:
            return None
        return None

    def evaluate(self, _script):
        return "textarea"

    def is_enabled(self):
        return not self.disabled

    def is_editable(self):
        return self.editable and not self.disabled

    def bounding_box(self):
        return {"width": 600, "height": 48}


class FakeCollection:
    def __init__(self, nodes):
        self.nodes = list(nodes)

    def count(self):
        return len(self.nodes)

    def nth(self, index):
        return self.nodes[index]


class FakeRoot:
    def __init__(self, nodes):
        self.nodes = nodes

    def locator(self, selector):
        if selector == compat._COMPOSER_SELECTORS[0]:
            return FakeCollection(self.nodes)
        return FakeCollection([])


class FakePage(FakeRoot):
    frames = []
    main_frame = None


def test_disabled_visible_textarea_is_not_a_writable_composer():
    assert runtime._editable(FakeNode(disabled=True)) is False


def test_writable_composer_skips_disabled_decoy_and_uses_enabled_input():
    disabled = FakeNode(disabled=True)
    enabled = FakeNode(disabled=False)
    page = FakePage([disabled, enabled])
    found = runtime.writable_composer(page, timeout_ms=100)
    assert found is enabled
