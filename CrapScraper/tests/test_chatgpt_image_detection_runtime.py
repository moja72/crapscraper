from __future__ import annotations

from app.additions.chatgpt_image_detection_runtime import (
    _image_candidate_key,
    _is_probable_generated_image,
)


def test_generated_image_accepts_large_main_conversation_image():
    item = {
        "src": "https://files.oaiusercontent.com/file-abc/image.png",
        "width": 1024,
        "height": 1024,
        "alt": "",
        "scope": "main",
        "index": 7,
    }
    assert _is_probable_generated_image(item)
    assert "file-abc" in _image_candidate_key(item)


def test_generated_image_rejects_avatar_and_small_icon():
    assert not _is_probable_generated_image(
        {
            "src": "https://example.com/avatar.png",
            "width": 512,
            "height": 512,
            "alt": "avatar",
            "scope": "main",
            "index": 1,
        }
    )
    assert not _is_probable_generated_image(
        {
            "src": "https://example.com/icon.png",
            "width": 64,
            "height": 64,
            "alt": "",
            "scope": "main",
            "index": 2,
        }
    )


def test_candidate_key_distinguishes_duplicate_src_inserted_later():
    first = {
        "src": "blob:https://chatgpt.com/abc",
        "width": 1024,
        "height": 1024,
        "alt": "",
        "scope": "main",
        "index": 3,
    }
    second = {**first, "index": 4}
    assert _image_candidate_key(first) != _image_candidate_key(second)
