from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import app.addition_final_validation_policy as final_validation
import app.addition_image_delivery_policy as delivery


_INSTALLED = False
_BASE_VALIDATE_IMAGE_FILE = None


def _validate_image_file(job_id: str, image_path: Path) -> None:
    path = Path(image_path)
    if path.suffix.lower() != ".webp":
        return _BASE_VALIDATE_IMAGE_FILE(job_id, path)

    delivery._validate_delivery(path)
    try:
        reference, reference_sha = final_validation._reference_hash(job_id)
    except Exception:
        reference, reference_sha = None, ""
    current_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if reference_sha and current_sha == reference_sha:
        name = getattr(reference, "name", "imagem de referência")
        raise RuntimeError(f"A imagem capturada é exatamente a referência {name}, não uma nova geração do produto.")


def install_addition_image_validation_policy() -> None:
    global _INSTALLED, _BASE_VALIDATE_IMAGE_FILE
    if _INSTALLED:
        return
    _BASE_VALIDATE_IMAGE_FILE = final_validation._validate_image_file
    final_validation._validate_image_file = _validate_image_file
    _INSTALLED = True
