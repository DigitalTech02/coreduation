"""AI-generated B-roll image cache.

Given a short text prompt, produces a 1024x1024 PNG via one of four providers:

* ``fal``       — fal.ai FLUX, ~$0.003/image (FLUX schnell).  Default.
* ``openai``    — DALL-E 3, ~$0.04/image.
* ``recraft``   — Recraft V3, ~$0.04/image.  Best vector/illustration style.
* ``replicate`` — Replicate (FLUX, SDXL, SD 3.5, ...).  Large model catalog.

Provider selected by ``BROLL_IMAGE_PROVIDER`` config flag.  All non-OpenAI
providers fall back to OpenAI DALL-E if their API key is missing or SDK is
not installed, so the pipeline never breaks because of provider issues.

Optionally removes the background with ``rembg``.  Caches results on disk
by ``(prompt, provider_model_id)`` hash — re-running the same prompt with
the same provider is instant and free.  Switching providers regenerates
because different providers produce different images from the same prompt.

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
        from config import (
            BROLL_IMAGE_MODEL,
            FAL_IMAGE_MODEL,
            RECRAFT_IMAGE_MODEL,
            REPLICATE_IMAGE_MODEL,
        )
        if provider == "fal":
            return FAL_IMAGE_MODEL or "fal-ai/flux/schnell"
        if provider == "recraft":
            return RECRAFT_IMAGE_MODEL or "recraftv3"
        if provider == "replicate":
            return REPLICATE_IMAGE_MODEL or "black-forest-labs/flux-schnell"
        return BROLL_IMAGE_MODEL or "dall-e-3"
    except Exception:
        defaults = {
            "fal":       "fal-ai/flux/schnell",
            "recraft":   "recraftv3",
            "replicate": "black-forest-labs/flux-schnell",
        }
        return defaults.get(provider, "dall-e-3")


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


def _generate_recraft(prompt: str, model: str) -> bytes | None:
    """Call Recraft V3 image generation; returns raw PNG bytes or None on failure.

    Uses the public REST API directly (no SDK dependency).  Requires
    ``RECRAFT_API_TOKEN`` env var.  Recraft's strength: vector and
    digital-illustration styles that match the infographic look.
    """
    api_key = os.getenv("RECRAFT_API_TOKEN") or os.getenv("RECRAFT_API_KEY")
    if not api_key:
        logger.debug("RECRAFT_API_TOKEN not set — Recraft provider unavailable")
        return None

    try:
        from config import RECRAFT_STYLE
    except Exception:
        RECRAFT_STYLE = "digital_illustration"

    import json as _json
    import urllib.request

    body = _json.dumps({
        "prompt": prompt,
        "style": RECRAFT_STYLE or "digital_illustration",
        "size": "1024x1024",
        "model": model or "recraftv3",
        "n": 1,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://external.api.recraft.ai/v1/images/generations",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "coreduation/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning("Recraft generation failed: %s", e)
        return None

    images = data.get("data") or []
    if not images:
        logger.warning("Recraft returned no images: %s", data)
        return None

    url = images[0].get("url")
    if not url:
        logger.warning("Recraft response had no URL: %s", images[0])
        return None

    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            return resp.read()
    except Exception as e:
        logger.warning("Failed to download Recraft image (%s): %s", url, e)
        return None


def _generate_replicate(prompt: str, model: str) -> bytes | None:
    """Call Replicate image generation; returns raw PNG bytes or None on failure.

    Uses the ``replicate`` Python SDK (``pip install replicate``) for the
    cleanest API.  Requires ``REPLICATE_API_TOKEN`` env var (auto-detected
    by the SDK).

    Model id format is ``owner/model`` (e.g. ``black-forest-labs/flux-schnell``).
    The SDK handles polling for completion automatically.
    """
    if not os.getenv("REPLICATE_API_TOKEN"):
        logger.debug("REPLICATE_API_TOKEN not set — Replicate provider unavailable")
        return None

    try:
        import replicate
    except ImportError:
        logger.warning(
            "replicate SDK not installed.  pip install replicate.  "
            "Falling back to other provider."
        )
        return None

    model_id = model or "black-forest-labs/flux-schnell"
    try:
        output = replicate.run(
            model_id,
            input={
                "prompt": prompt,
                "num_outputs": 1,
                "aspect_ratio": "1:1",
                "output_format": "png",
                "num_inference_steps": 4,  # FLUX schnell default
            },
        )
    except Exception as e:
        logger.warning("Replicate run failed (%s): %s", model_id, e)
        return None

    # Output can be a list of URLs, a single URL, or a FileOutput object.
    if isinstance(output, list):
        item = output[0] if output else None
    else:
        item = output
    if item is None:
        logger.warning("Replicate returned no output")
        return None

    # Newer replicate SDK returns FileOutput objects with .read()
    if hasattr(item, "read") and not isinstance(item, str):
        try:
            return item.read()
        except Exception as e:
            logger.warning("Replicate FileOutput.read() failed: %s", e)
            return None

    # Otherwise it's a URL string
    url = str(item)
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=60) as resp:
            return resp.read()
    except Exception as e:
        logger.warning("Failed to download Replicate image (%s): %s", url, e)
        return None


# Provider-specific generators registered in dispatch order.  When a
# non-OpenAI provider fails, _generate_image falls back to OpenAI DALL-E
# so the pipeline never breaks because of a missing API key or SDK.
_PROVIDER_GENERATORS = {
    "fal":       _generate_fal,
    "recraft":   _generate_recraft,
    "replicate": _generate_replicate,
}


def _generate_image(prompt: str, provider: str, model: str) -> bytes | None:
    """Dispatch to the configured provider; fall back to OpenAI on failure.

    OpenAI is the universal fallback since most users already have an
    OPENAI_API_KEY for the LLM script generation step.
    """
    gen = _PROVIDER_GENERATORS.get(provider)
    if gen is not None:
        png = gen(prompt, model)
        if png is not None:
            return png
        logger.info("%s unavailable — falling back to OpenAI DALL-E", provider)
        return _generate_openai(prompt, "dall-e-3")

    # provider == "openai" or unknown — go straight to OpenAI with the
    # configured model.
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
