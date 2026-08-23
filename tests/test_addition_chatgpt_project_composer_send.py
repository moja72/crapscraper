from __future__ import annotations

import unittest

import app.addition_chatgpt_cdp_reconnect_policy as policy


class _Keyboard:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def press(self, value: str) -> None:
        self.calls.append(("press", value))

    def insert_text(self, value: str) -> None:
        self.calls.append(("insert_text", value))


class _Page:
    def __init__(self) -> None:
        self.keyboard = _Keyboard()


class _FillComposer:
    def __init__(self) -> None:
        self.value = ""
        self.click_called = False

    def click(self, *args, **kwargs) -> None:
        self.click_called = True
        raise AssertionError("A correção não deve usar clique de ponteiro no editor.")

    def fill(self, value: str, *, timeout: int) -> None:
        self.value = value


class _FocusFallbackComposer:
    def __init__(self) -> None:
        self.focused = False

    def fill(self, value: str, *, timeout: int) -> None:
        raise RuntimeError("fill indisponível")

    def focus(self, *, timeout: int) -> None:
        self.focused = True


class AdditionChatGPTProjectComposerSendTests(unittest.TestCase):
    def test_project_composer_is_filled_without_pointer_click(self) -> None:
        page = _Page()
        composer = _FillComposer()

        policy._fill_composer_without_pointer_click(page, composer, "Prompt do produto")

        self.assertEqual(composer.value, "Prompt do produto")
        self.assertFalse(composer.click_called)
        self.assertEqual(page.keyboard.calls, [])

    def test_keyboard_fallback_focuses_editor_without_pointer_click(self) -> None:
        page = _Page()
        composer = _FocusFallbackComposer()

        policy._fill_composer_without_pointer_click(page, composer, "Prompt alternativo")

        self.assertTrue(composer.focused)
        self.assertEqual(
            page.keyboard.calls,
            [("press", "Control+A"), ("insert_text", "Prompt alternativo")],
        )


if __name__ == "__main__":
    unittest.main()
