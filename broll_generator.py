"""AI-generated B-roll image cache.

Given a short text prompt, produces a 1024x1024 PNG via DALL-E 3 (or a local
model when ``BROLL_IMAGE_MODEL`` is set to something else), optionally removes
the background with ``rembg``, and caches the result on disk.

Calling :func:`get_broll_image` returns a path to a PNG that the Manim engine
renders with a Ken Burns pan in :func:`rendering_engine.broll.render_show_image`.
"""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

ASSETS_BROLL_DIR = Path("assets/broll")


def _enabled() -> bool:
    try:
        from config import ENABLE_AI_BROLL
        return bool(ENABLE_AI_BROLL)
    except Exception:
        return False


def _model() -> str:
    try:
        from config import BROLL_IMAGE_MODEL
        return BROLL_IMAGE_MODEL
    except Exception:
        return "dall-e-3"


def _hash_prompt(prompt: str, model: str) -> str:
    import hashlib
    h = hashlib.sha256()
    h.update(prompt.encode("utf-8"))
    h.update(b"\x00")
    h.update(model.encode("utf-8"))
    return h.hexdigest()[:24]


def _maybe_remove_background(src: Path, dest: Path) -> bool:
    """Attempt to remove the background with rembg.  Returns True on success."""
    try:
        from rembg import remove
        with open(src, "rb") as f:
            data = f.read()
        out = remove(data)
        with open(dest, "wb") as f:
            f.write(out)
        return True
    except Exception as e:
        logger.debug("rembg unavailable or failed (%s) — using raw image", e)
        return False


def _generate_dalle(prompt: str) -> bytes | None:
    """Call OpenAI image generation; returns raw PNG bytes or None on failure."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        result = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            n=1,
            size="1024x1024",
            response_format="b64_json",
        )
        b64 = result.data[0].b64_json
        return base64.b64decode(b64)
    except Exception as e:
        logger.warning("DALL-E generation failed: %s", e)
        return None


def get_broll_image(prompt: str, *, remove_bg: bool = False) -> str | None:
    """Return a path to a PNG matching *prompt*.  Cached on disk.

    Returns ``None`` when AI B-roll is disabled, the API call fails, or the
    cache directory cannot be written.
    """
    if not _enabled() or not prompt.strip():
        return None

    ASSETS_BROLL_DIR.mkdir(parents=True, exist_ok=True)
    model = _model()
    key = _hash_prompt(prompt, model)
    raw_path = ASSETS_BROLL_DIR / f"{key}.png"
    nobg_path = ASSETS_BROLL_DIR / f"{key}.nobg.png"

    if remove_bg and nobg_path.is_file():
        return str(nobg_path)
    if raw_path.is_file() and not remove_bg:
        return str(raw_path)

    if not raw_path.is_file():
        logger.info("Generating B-roll image: %r", prompt[:80])
        png = _generate_dalle(prompt)
        if not png:
            return None
        raw_path.write_bytes(png)

    if remove_bg:
        if _maybe_remove_background(raw_path, nobg_path):
            return str(nobg_path)
        return str(raw_path)
    return str(raw_path)
