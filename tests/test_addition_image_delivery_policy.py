from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.addition_image_delivery_policy as policy


class AdditionImageDeliveryPolicyTests(unittest.TestCase):
    def test_plugin_filename_uses_product_slug_and_type(self) -> None:
        self.assertEqual(
            policy._delivery_filename({"source_name": "Presto Player Pro", "kind": "plugin"}),
            "presto-player-pro-plugin.webp",
        )

    def test_theme_filename_avoids_duplicate_type_suffix(self) -> None:
        self.assertEqual(
            policy._delivery_filename({"source_name": "Meu Tema WordPress Theme", "kind": "theme"}),
            "meu-tema-tema.webp",
        )

    def test_chat_titles_use_colon_format(self) -> None:
        job = {"source_name": "3D Carousel For WordPress", "kind": "plugin"}
        with patch.object(policy.additions, "_row", return_value=job):
            self.assertEqual(policy._chat_title("job", "Chat 1/2 — descrição"), "Descrição: 3D Carousel For WordPress")
            self.assertEqual(policy._chat_title("job", "Chat 2/2 — imagem"), "Imagem: 3D Carousel For WordPress")

    def test_prompts_start_with_readable_chat_title(self) -> None:
        job = {"source_name": "Presto Player Pro", "kind": "plugin"}
        old_description = policy._BASE_DESCRIPTION_PROMPT
        old_image = policy._BASE_IMAGE_PROMPT
        try:
            policy._BASE_DESCRIPTION_PROMPT = lambda _job: "Escreva somente a descrição."
            policy._BASE_IMAGE_PROMPT = lambda _job: "Gere somente a imagem."
            self.assertTrue(policy._description_prompt(job).startswith("Descrição: Presto Player Pro\n\n"))
            self.assertTrue(policy._image_prompt(job).startswith("Imagem: Presto Player Pro\n\n"))
        finally:
            policy._BASE_DESCRIPTION_PROMPT = old_description
            policy._BASE_IMAGE_PROMPT = old_image

    @unittest.skipUnless(importlib.util.find_spec("PIL"), "Pillow não instalado")
    def test_webp_output_is_500_square_and_under_100kb(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.png"
            target = Path(temp_dir) / "result.webp"
            image = Image.new("RGBA", (920, 640), (0, 0, 0, 0))
            for x in range(0, 920, 16):
                for y in range(0, 640, 16):
                    image.paste(((x * 3) % 255, (y * 5) % 255, ((x + y) * 7) % 255, 220), (x, y, min(x + 16, 920), min(y + 16, 640)))
            image.save(source)

            canvas = policy._canvas_500(source)
            raw, _quality = policy._webp_bytes(canvas)
            target.write_bytes(raw)
            info = policy._validate_delivery(target)

            self.assertEqual((info["width"], info["height"]), (500, 500))
            self.assertLessEqual(info["size"], 100 * 1024)
            self.assertEqual(target.suffix, ".webp")


if __name__ == "__main__":
    unittest.main()
