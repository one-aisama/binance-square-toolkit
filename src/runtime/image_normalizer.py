from __future__ import annotations

from pathlib import Path
from typing import Final

from PIL import Image, ImageOps

DEFAULT_OUTPUT_DIR = Path("data/normalized_images")
DEFAULT_TARGET_SIZE: Final[tuple[int, int]] = (1600, 800)
DEFAULT_TARGET_RATIO: Final[float] = 2.0
MIN_LANDSCAPE_RATIO: Final[float] = 1.45
MAX_LANDSCAPE_RATIO: Final[float] = 3.4
BACKGROUND_COLOR: Final[tuple[int, int, int]] = (13, 17, 27)


def normalize_image_to_landscape(
    source_path: str,
    *,
    output_path: str | None = None,
    target_size: tuple[int, int] = DEFAULT_TARGET_SIZE,
) -> str:
    """Normalize any image into a wide landscape asset for posting."""
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(f"Image not found: {source_path}")

    destination = Path(output_path) if output_path else _default_output_path(source)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(source) as raw_image:
        normalized = _normalize_canvas(raw_image.convert("RGB"), target_size)
        normalized.save(destination, format="PNG")

    return str(destination.resolve())


def is_landscape_ratio(width: int, height: int) -> bool:
    if width <= 0 or height <= 0:
        return False
    ratio = width / height
    return MIN_LANDSCAPE_RATIO <= ratio <= MAX_LANDSCAPE_RATIO


def _normalize_canvas(image: Image.Image, target_size: tuple[int, int]) -> Image.Image:
    rebalanced = _rebalance_ratio(image)
    canvas = Image.new("RGB", target_size, BACKGROUND_COLOR)
    fitted = ImageOps.contain(rebalanced, target_size, method=Image.Resampling.LANCZOS)
    offset = ((target_size[0] - fitted.width) // 2, (target_size[1] - fitted.height) // 2)
    canvas.paste(fitted, offset)
    return canvas


def _rebalance_ratio(image: Image.Image) -> Image.Image:
    width, height = image.size
    if width <= 0 or height <= 0:
        raise ValueError("Image has invalid dimensions")

    ratio = width / height
    if ratio < MIN_LANDSCAPE_RATIO:
        target_width = int(height * DEFAULT_TARGET_RATIO)
        canvas = Image.new("RGB", (target_width, height), BACKGROUND_COLOR)
        canvas.paste(image, ((target_width - width) // 2, 0))
        return canvas

    if ratio > MAX_LANDSCAPE_RATIO:
        target_width = int(height * MAX_LANDSCAPE_RATIO)
        left = max((width - target_width) // 2, 0)
        return image.crop((left, 0, left + target_width, height))

    return image


def _default_output_path(source: Path) -> Path:
    stem = source.stem
    return DEFAULT_OUTPUT_DIR / f"{stem}_wide.png"
