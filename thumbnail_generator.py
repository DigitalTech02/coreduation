"""Auto-thumbnail generation (Pillow + optional AI background).

Produces a 1280x720 YouTube-ready thumbnail composed of:

  1. A category-themed gradient background (or AI-generated background if
     ``THUMBNAIL_USE_AI_BG=true`` and DALL-E is reachable).
  2. A bold title overlay (auto-wrapped, drop shadow for legibility).
  3. A small channel watermark in the corner.
  4. A vertical accent stripe matching the category palette.

Thumbnails are saved as JPG (YouTube max 2MB). Falls back gracefully if
Pillow is missing or the AI background call fails.
"""

from __future__ import annotations

import logging
import os
import random
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 1280, 720


def _category_colors(category: str) -> Tuple[str, str, str]:
    """Return ``(bg_top, bg_bottom, accent)`` hex colors for *category*."""
    try:
        from rendering_engine.themes import get_theme
        t = get_theme(category)
        accent = t.accent
        if hasattr(accent, "to_hex"):
            accent_hex = accent.to_hex()
        elif isinstance(accent, str):
            accent_hex = accent
        else:
            accent_hex = "#4fc3f7"
        return t.bg_top, t.bg_bottom, accent_hex
    except Exception:
        return "#1a1f3a", "#080d1e", "#4fc3f7"


def _hex_to_rgb(h: str) -> Tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _make_gradient_bg(top: str, bottom: str):
    from PIL import Image
    r1, g1, b1 = _hex_to_rgb(top)
    r2, g2, b2 = _hex_to_rgb(bottom)
    img = Image.new("RGB", (WIDTH, HEIGHT))
    px = img.load()
    for y in range(HEIGHT):
        t = y / max(HEIGHT - 1, 1)
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        for x in range(WIDTH):
            px[x, y] = (r, g, b)
    return img


def _maybe_ai_background(category: str, topic: str, output_dir: Path):
    if os.getenv("THUMBNAIL_USE_AI_BG", "false").lower() not in ("true", "1", "yes"):
        return None
    try:
        from broll_generator import get_broll_image
        prompt = (
            f"Cinematic, high-contrast widescreen background illustration for a "
            f"YouTube thumbnail about '{topic}'. Category: {category}. "
            f"Bold colors, clean composition, leave the right side darker so "
            f"a title can be overlaid."
        )
        path = get_broll_image(prompt, str(output_dir / ".thumb-bg"))
        if path:
            from PIL import Image
            img = Image.open(path).convert("RGB")
            return img.resize((WIDTH, HEIGHT))
    except Exception as e:
        logger.debug("AI background unavailable, using gradient: %s", e)
    return None


def _font(size: int):
    from PIL import ImageFont
    candidates = [
        os.getenv("THUMBNAIL_FONT", ""),
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for c in candidates:
        if c and Path(c).exists():
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _wrap_text(text: str, font, max_width: int) -> list[str]:
    from PIL import ImageDraw, Image
    img = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(img)

    words = text.split()
    lines: list[str] = []
    current = ""
    for w in words:
        candidate = (current + " " + w).strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def generate_thumbnail(
    title: str,
    category: str = "",
    output_path: str = "thumbnail.jpg",
    *,
    topic: str | None = None,
) -> str | None:
    """Render a 1280x720 thumbnail to *output_path*; return the path or ``None``."""
    try:
        from PIL import Image, ImageDraw, ImageFilter
    except ImportError:
        logger.warning("Pillow not installed — skipping thumbnail generation")
        return None

    title = (title or "").strip() or (topic or "Untitled")
    bg_top, bg_bottom, accent = _category_colors(category)
    output_dir = Path(output_path).resolve().parent
    output_dir.mkdir(parents=True, exist_ok=True)

    img = _maybe_ai_background(category, topic or title, output_dir)
    if img is None:
        img = _make_gradient_bg(bg_top, bg_bottom)

    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle([(0, 0), (int(WIDTH * 0.55), HEIGHT)], fill=(0, 0, 0, 110))

    accent_rgb = _hex_to_rgb(accent)
    od.rectangle([(0, 0), (14, HEIGHT)], fill=accent_rgb + (255,))

    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    title_font = _font(110)
    max_text_w = int(WIDTH * 0.50)
    lines = _wrap_text(title.upper(), title_font, max_text_w)

    for size in (110, 96, 84, 72, 64, 56):
        title_font = _font(size)
        lines = _wrap_text(title.upper(), title_font, max_text_w)
        if len(lines) <= 4:
            break

    try:
        line_h = title_font.getbbox("Ag")[3] - title_font.getbbox("Ag")[1]
    except Exception:
        line_h = title_font.size if hasattr(title_font, "size") else 60

    total_h = line_h * len(lines) + 12 * (len(lines) - 1)
    y = (HEIGHT - total_h) // 2

    for line in lines:
        x = 60
        for ox, oy in ((-3, 0), (3, 0), (0, -3), (0, 3)):
            draw.text((x + ox, y + oy), line, font=title_font, fill=(0, 0, 0))
        draw.text((x, y), line, font=title_font, fill=(255, 255, 255))
        y += line_h + 12

    accent_underline_y = y - line_h - 12 + line_h + 6
    draw.rectangle([(60, accent_underline_y), (60 + 220, accent_underline_y + 8)],
                   fill=accent_rgb)

    try:
        from config import CHANNEL_NAME
        channel = CHANNEL_NAME
    except Exception:
        channel = "CoreDuation"
    wm_font = _font(34)
    draw.text((WIDTH - 320, HEIGHT - 60), channel.upper(),
              font=wm_font, fill=accent_rgb)

    if category:
        cat_font = _font(28)
        draw.text((60, 32), category.upper(), font=cat_font, fill=accent_rgb)

    final_path = Path(output_path)
    if final_path.suffix.lower() not in (".jpg", ".jpeg"):
        final_path = final_path.with_suffix(".jpg")
    img.save(final_path, "JPEG", quality=92, optimize=True)
    logger.info("Thumbnail rendered -> %s (%dx%d)", final_path, WIDTH, HEIGHT)
    return str(final_path)
