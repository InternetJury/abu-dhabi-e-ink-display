from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont


FONT_DIR = Path(__file__).resolve().parent / "fonts"
FONT_FILES = {
    "space": FONT_DIR / "SpaceGrotesk[wght].ttf",
    "inter": FONT_DIR / "Inter[opsz,wght].ttf",
    "symbols": FONT_DIR / "material-symbols-outlined.ttf",
}
SYMBOL_CODEPOINTS_FILE = FONT_DIR / "material-symbols-outlined.codepoints"
DEFAULT_FAMILY = "space"


@lru_cache(maxsize=128)
def load_font(
    family: str = DEFAULT_FAMILY,
    size: int = 16,
    weight: int = 400,
    fill: int = 0,
    grade: int = 0,
    optical_size: int | None = None,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = FONT_FILES.get(family, FONT_FILES[DEFAULT_FAMILY])
    if not path.exists():
        return ImageFont.load_default()
    font = ImageFont.truetype(str(path), size=size)
    if hasattr(font, "set_variation_by_axes"):
        try:
            if family == "symbols":
                font.set_variation_by_axes(
                    [
                        max(0, min(fill, 1)),
                        max(-50, min(grade, 200)),
                        max(20, min(optical_size or size, 48)),
                        max(100, min(weight, 700)),
                    ]
                )
            else:
                font.set_variation_by_axes([max(300, min(weight, 900))])
        except OSError:
            pass
    return font


@lru_cache(maxsize=1)
def load_symbol_codepoints() -> dict[str, str]:
    if not SYMBOL_CODEPOINTS_FILE.exists():
        return {}
    mapping: dict[str, str] = {}
    with SYMBOL_CODEPOINTS_FILE.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                name, codepoint = line.split(" ", 1)
            except ValueError:
                continue
            mapping[name] = chr(int(codepoint, 16))
    return mapping


def icon_glyph(name: str, fallback: str = "cloud") -> str:
    mapping = load_symbol_codepoints()
    if name in mapping:
        return mapping[name]
    if fallback in mapping:
        return mapping[fallback]
    return "?"
