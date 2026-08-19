from __future__ import annotations

import io
import re
import unicodedata
from pathlib import Path
from typing import Any, Mapping

import app.addition_chat_binding_policy as binding
import app.addition_final_validation_policy as final_validation
import app.addition_one_click_policy as one_click
import app.addition_parallel_generation_policy as parallel
import app.addition_product_creative_policy as creative
import app.addition_unique_chat_marker_policy as unique
import app.new_product_workflow_policy as additions


_INSTALLED = False
_BASE_PERSIST_IMAGE = None
_BASE_CREATE_DRAFT = None
_BASE_DESCRIPTION_PROMPT = None
_BASE_IMAGE_PROMPT = None

_TARGET_SIZE = (500, 500)
_MAX_BYTES = 100_000


def _kind(job: Mapping[str, Any]) -> str:
    return "theme" if str(job.get("kind") or "").strip().lower() == "theme" else "plugin"


def _slug(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower())
    text = re.sub(r"-{2,}", "-", text).strip("-")
    for suffix in ("-wordpress-plugin", "-wordpress-theme", "-plugin", "-theme", "-tema"):
        if text.endswith(suffix) and len(text) > len(suffix):
            text = text[: -len(suffix)].rstrip("-")
            break
    return text or "produto"


def _delivery_filename(job: Mapping[str, Any]) -> str:
    name = str(job.get("source_name") or job.get("title") or "produto").strip()
    suffix = "tema" if _kind(job) == "theme" else "plugin"
    return f"{_slug(name)}-{suffix}.webp"


def _chat_title(job_id: str, label: str) -> str:
    try:
        job = additions._row(job_id)
    except Exception:
        job = {}
    name = " ".join(str(job.get("source_name") or job.get("title") or "Produto WordPress").split()).strip()
    prefix = "Descrição" if "chat 1" in str(label).lower() else "Imagem" if "chat 2" in str(label).lower() else "Chat"
    return f"{prefix}: {name}"


def _prompt_name(job: Mapping[str, Any], prefix: str, base: str) -> str:
    name = " ".join(str(job.get("source_name") or job.get("title") or "Produto WordPress").split()).strip()
    body = str(base or "").strip()
    heading = f"{prefix}: {name}"
    if body.startswith(heading):
        return body
    return f"{heading}\n\n{body}"


def _description_prompt(job: Mapping[str, Any]) -> str:
    return _prompt_name(job, "Descrição", _BASE_DESCRIPTION_PROMPT(job))


def _image_prompt(job: Mapping[str, Any]) -> str:
    return _prompt_name(job, "Imagem", _BASE_IMAGE_PROMPT(job))


def _pillow() -> tuple[Any, Any, Any]:
    try:
        from PIL import Image, ImageOps, features
    except Exception as error:
        raise RuntimeError(
            "Pillow é necessário para otimizar a imagem final. Execute: python -m pip install -r requirements-image.txt"
        ) from error
    if not features.check("webp"):
        raise RuntimeError("A instalação do Pillow não possui suporte a WebP.")
    return Image, ImageOps, features


def _canvas_500(source: Path) -> Any:
    Image, ImageOps, _features = _pillow()
    resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
    with Image.open(source) as opened:
        try:
            opened.seek(0)
        except Exception:
            pass
        rgba = opened.convert("RGBA")
        fitted = ImageOps.contain(rgba, _TARGET_SIZE, method=resampling)
        canvas = Image.new("RGBA", _TARGET_SIZE, (0, 0, 0, 0))
        left = (_TARGET_SIZE[0] - fitted.width) // 2
        top = (_TARGET_SIZE[1] - fitted.height) // 2
        canvas.alpha_composite(fitted, (left, top))
        return canvas


def _webp_bytes(canvas: Any) -> tuple[bytes, int]:
    Image, _ImageOps, _features = _pillow()
    qualities = (88, 84, 80, 76, 72, 68, 64, 60, 56, 52, 48, 44, 40, 36, 32, 28, 24, 20, 16, 12, 8, 5)

    def encode(image: Any, quality: int) -> bytes:
        buffer = io.BytesIO()
        kwargs = {
            "format": "WEBP",
            "quality": quality,
            "method": 6,
            "lossless": False,
        }
        try:
            image.save(buffer, exact=True, **kwargs)
        except TypeError:
            image.save(buffer, **kwargs)
        return buffer.getvalue()

    smallest = b""
    for quality in qualities:
        raw = encode(canvas, quality)
        if not smallest or len(raw) < len(smallest):
            smallest = raw
        if len(raw) <= _MAX_BYTES:
            return raw, quality

    quantize_enum = getattr(Image, "Quantize", Image)
    dither_enum = getattr(Image, "Dither", Image)
    method = getattr(quantize_enum, "FASTOCTREE", 2)
    dither = getattr(dither_enum, "NONE", 0)
    for colors in (256, 128, 64, 32):
        reduced = canvas.quantize(colors=colors, method=method, dither=dither).convert("RGBA")
        for quality in (40, 30, 20, 12, 8, 5):
            raw = encode(reduced, quality)
            if not smallest or len(raw) < len(smallest):
                smallest = raw
            if len(raw) <= _MAX_BYTES:
                return raw, quality

    raise RuntimeError(
        f"Não foi possível reduzir a imagem 500x500 para até 100 KB; menor resultado: {len(smallest) / 1000:.1f} KB."
    )


def _validate_delivery(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        raise RuntimeError("A imagem final otimizada não existe no disco.")
    size = path.stat().st_size
    if path.suffix.lower() != ".webp":
        raise RuntimeError("A imagem final precisa estar em WebP.")
    if size > _MAX_BYTES:
        raise RuntimeError(f"A imagem final ultrapassou 100 KB: {size / 1000:.1f} KB.")
    Image, _ImageOps, _features = _pillow()
    with Image.open(path) as image:
        if tuple(image.size) != _TARGET_SIZE:
            raise RuntimeError(f"A imagem final precisa ter 500x500; recebido {image.width}x{image.height}.")
        if str(image.format or "").upper() != "WEBP":
            raise RuntimeError("O conteúdo da imagem final não é WebP.")
    return {"path": str(path), "size": size, "width": 500, "height": 500}


def _optimize_job_image(job_id: str, source_path: str | Path | None = None, *, emit: bool = True) -> str:
    job = additions._row(job_id)
    source = Path(str(source_path or job.get("image_path") or "")).expanduser()
    if not source.exists() or not source.is_file():
        raise RuntimeError("A imagem capturada do ChatGPT não existe para otimização.")

    additions._IMAGE_ROOT.mkdir(parents=True, exist_ok=True)
    target = additions._IMAGE_ROOT / _delivery_filename(job)

    if source.resolve() == target.resolve():
        try:
            _validate_delivery(target)
            additions._update(job_id, image_path=str(target), error="")
            additions._recalculate_state(job_id)
            return str(target)
        except Exception:
            pass

    canvas = _canvas_500(source)
    raw, quality = _webp_bytes(canvas)
    temporary = target.with_suffix(".webp.tmp")
    temporary.write_bytes(raw)
    temporary.replace(target)
    info = _validate_delivery(target)

    additions._update(job_id, image_path=str(target), error="")
    additions._recalculate_state(job_id)
    try:
        image_root = additions._IMAGE_ROOT.resolve()
        if source.resolve() != target.resolve() and source.resolve().parent == image_root:
            source.unlink(missing_ok=True)
    except Exception:
        pass

    if emit:
        one_click._emit(
            job_id,
            f"Imagem final otimizada: {target.name} | 500x500 | {info['size'] / 1000:.1f} KB | WebP (qualidade {quality}).",
            step="image_ready",
            progress=78,
        )
    return str(target)


def _persist_image_optimized(job_id: str, data_url: str) -> str:
    raw_path = _BASE_PERSIST_IMAGE(job_id, data_url)
    return _optimize_job_image(job_id, raw_path)


def _create_draft_with_delivery_image(job_id: str, confirmation: str) -> dict[str, Any]:
    job = additions._row(job_id)
    if str(job.get("image_path") or "").strip():
        _optimize_job_image(job_id, emit=False)
    return _BASE_CREATE_DRAFT(job_id, confirmation)


def install_addition_image_delivery_policy() -> None:
    global _INSTALLED, _BASE_PERSIST_IMAGE, _BASE_CREATE_DRAFT
    global _BASE_DESCRIPTION_PROMPT, _BASE_IMAGE_PROMPT
    if _INSTALLED:
        return

    _BASE_PERSIST_IMAGE = one_click._persist_image
    _BASE_CREATE_DRAFT = additions._create_or_resume_draft
    _BASE_DESCRIPTION_PROMPT = binding._description_only_prompt
    _BASE_IMAGE_PROMPT = parallel._parallel_image_prompt

    one_click._persist_image = _persist_image_optimized
    additions._create_or_resume_draft = _create_draft_with_delivery_image
    unique._desired_chat_name = _chat_title

    binding._description_only_prompt = _description_prompt
    parallel._parallel_image_prompt = _image_prompt
    creative._image_only_prompt = _image_prompt
    final_validation._description_prompt = _description_prompt
    final_validation._image_prompt = _image_prompt

    _INSTALLED = True
