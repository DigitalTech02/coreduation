"""AI-generated B-roll image cache.

Given a short text prompt, produces a 1024x1024 PNG via one of two providers:

* ``openai`` — DALL-E 3, ~$0.04/image, high quality.
* ``fal``    — fal.ai FLUX, ~$0.003/image (FLUX schnell), ~13x cheaper.

Provider selected by ``BROLL_IMAGE_PROVIDER`` config flag.  Optionally removes
the background with ``rembg``.  Caches results on disk by prompt+model hash —
re-running the same prompt is instant and free.

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


def _provider() -> str:
    try:
        from config import BROLL_IMAGE_PROVIDER
        return (BROLL_IMAGE_PROVIDER or "fal").strip().lower()
    except Exception:
        return "fal"


def _model_for_provider(provider: str) -> str:
    """Return the model name to use as the cache key + generator argument."""
    try:
        from config import BROLL_IMAGE_MODEL, FAL_IMAGE_MODEL
        if provider == "fal":
            return FAL_IMAGE_MODEL or "fal-ai/flux/schnell"
        return BROLL_IMAGE_MODEL or "dall-e-3"
    except Exception:
        return "fal-ai/flux/schnell" if provider == "fal" else "dall-e-3"


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


def _generate_openai(prompt: str, model: str) -> bytes | None:
    """Call OpenAI image generation; returns raw PNG bytes or None on failure."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        result = client.images.generate(
            model=model or "dall-e-3",
            prompt=prompt,
            n=1,
            size="1024x1024",
            response_format="b64_json",
        )
        b64 = result.data[0].b64_json
        return base64.b64decode(b64)
    except Exception as e:
        logger.warning("OpenAI image generation failed: %s", e)
        return None


def _generate_fal(prompt: str, model: str) -> bytes | None:
    """Call fal.ai image generation; returns raw PNG bytes or None on failure.

    Requires ``fal-client`` (``pip install fal-client``) and ``FAL_KEY`` env
    var.  Defaults to FLUX schnell which is the cheapest+fastest option
    (~$0.003/image, ~2s latency).
    """
    if not os.getenv("FAL_KEY"):
        logger.debug("FAL_KEY not set — fal.ai provider unavailable")
        return None

    try:
        import fal_client
    except ImportError:
        logger.warning(
            "fal_client not installed.  pip install fal-client.  "
            "Falling back to other provider."
        )
        return None

    model_id = model or "fal-ai/flux/schnell"
    try:
        # Sync call.  fal_client.run blocks until image is generated.
        # FLUX schnell typically returns in ~2s, dev in ~5s.
        result = fal_client.run(
            model_id,
            arguments={
                "prompt": prompt,
                "image_size": "square_hd",  # 1024x1024
                "num_inference_steps": 4,   # FLUX schnell default
                "num_images": 1,
                "enable_safety_checker": True,
            },
        )
    except Exception as e:
        logger.warning("fal.ai run failed (%s): %s", model_id, e)
        return None

    images = (result or {}).get("images") or []
    if not images:
        logger.warning("fal.ai returned no images")
        return None

    url = images[0].get("url")
    if not url:
        logger.warning("fal.ai response had no URL: %s", images[0])
        return None

    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=60) as resp:
            return resp.read()
    except Exception as e:
        logger.warning("Failed to download fal.ai image (%s): %s", url, e)
        return None


def _generate_image(prompt: str, provider: str, model: str) -> bytes | None:
    """Dispatch to the configured provider; fall back to the other if it fails.

    Order of attempts when provider="fal":  fal → openai (defensive fallback).
    Order of attempts when provider="openai": openai only (no fallback to fal
    since DALL-E is the user's explicit pick).
    """
    if provider == "fal":
        png = _generate_fal(prompt, model)
        if png is not None:
            return png
        logger.info("fal.ai unavailable — falling back to OpenAI DALL-E")
        # Fallback uses OpenAI's default DALL-E model since the fal model
        # name isn't valid for OpenAI.
        return _generate_openai(prompt, "dall-e-3")
    return _generate_openai(prompt, model)


def get_broll_image(prompt: str, *, remove_bg: bool = False) -> str | None:
    """Return a path to a PNG matching *prompt*.  Cached on disk.

    Returns ``None`` when AI B-roll is disabled, both providers fail, or the
    cache directory cannot be written.

    Cache key: SHA-256 of (prompt + provider-specific model name).  Switching
    providers or models produces a fresh image.
    """
    if not _enabled() or not prompt.strip():
        return None

    ASSETS_BROLL_DIR.mkdir(parents=True, exist_ok=True)
    provider = _provider()
    model = _model_for_provider(provider)
    key = _hash_prompt(prompt, model)
    raw_path = ASSETS_BROLL_DIR / f"{key}.png"
    nobg_path = ASSETS_BROLL_DIR / f"{key}.nobg.png"

    if remove_bg and nobg_path.is_file():
        return str(nobg_path)
    if raw_path.is_file() and not remove_bg:
        return str(raw_path)

    if not raw_path.is_file():
        logger.info(
            "Generating B-roll image (%s/%s): %r",
            provider, model, prompt[:80],
        )
        png = _generate_image(prompt, provider, model)
        if not png:
            return None
        raw_path.write_bytes(png)

    if remove_bg:
        if _maybe_remove_background(raw_path, nobg_path):
            return str(nobg_path)
        return str(raw_path)
    return str(raw_path)
