"""Lottie / SVG icon renderer for shorts.

Resolves an *icon id* to an SVG file (preferring real Lottie JSONs in
``assets/lottie/<id>.json`` when the optional ``lottie`` package is
installed; falling back to bundled SVGs in ``assets/svg_icons/<id>.svg``).
The SVG is then loaded as a Manim ``SVGMobject`` and animated with a
spring-pop entrance + brief hold + fade-out, mirroring how a Lottie file
plays once and disappears.

Resolution order (in ``_resolve_icon_path``):

1. ``assets/lottie/<id>.json`` → convert via ``lottie`` to a cached SVG
   in ``assets/lottie/.svg_cache/<id>.svg``, return cached path.
2. ``assets/lottie/<id>.svg`` → return directly.
3. ``assets/svg_icons/<id>.svg`` → bundled fallback.

If none match, returns None and the caller renders nothing.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ASSETS_LOTTIE_DIR = Path("assets/lottie")
ASSETS_SVG_FALLBACK_DIR = Path("assets/svg_icons")
_LOTTIE_SVG_CACHE = ASSETS_LOTTIE_DIR / ".svg_cache"


def _convert_lottie_json_to_svg(json_path: Path, svg_path: Path) -> bool:
    """Convert a Lottie JSON to a single SVG frame using ``lottie`` package.

    Picks the middle-time frame of the animation as a representative
    static rendering.  Cached on disk by the caller.

    Returns True on success, False if the package isn't installed or the
    conversion fails for any reason — caller falls back to bundled SVG.
    """
    try:
        from lottie.parsers.tgs import parse_tgs_json
        from lottie.exporters.svg import export_svg
    except ImportError:
        logger.debug(
            "lottie package not installed (pip install lottie); "
            "falling back to bundled SVG for %s", json_path.name,
        )
        return False

    try:
        import json
        with open(json_path, "r", encoding="utf-8") as f:
            anim = parse_tgs_json(json.load(f))
        # Render at the middle of the animation timeline so we get the
        # icon at its "settled" state, not mid-animation.
        mid_frame = (anim.in_point + anim.out_point) / 2.0
        svg_path.parent.mkdir(parents=True, exist_ok=True)
        export_svg(anim, str(svg_path), frame=mid_frame)
        return True
    except Exception as e:
        logger.warning("Lottie → SVG conversion failed for %s: %s", json_path.name, e)
        return False


def _resolve_icon_path(icon_id: str) -> str | None:
    """Find an SVG file for *icon_id*, converting Lottie JSON if needed."""
    if not icon_id:
        return None
    icon_id = icon_id.strip().lower().replace("-", "_")

    # 1. Real Lottie JSON in assets/lottie/<id>.json — convert + cache to SVG
    json_path = ASSETS_LOTTIE_DIR / f"{icon_id}.json"
    if json_path.is_file():
        cached_svg = _LOTTIE_SVG_CACHE / f"{icon_id}.svg"
        if cached_svg.is_file():
            return str(cached_svg)
        if _convert_lottie_json_to_svg(json_path, cached_svg) and cached_svg.is_file():
            return str(cached_svg)

    # 2. Pre-rendered SVG in assets/lottie/<id>.svg
    direct_svg = ASSETS_LOTTIE_DIR / f"{icon_id}.svg"
    if direct_svg.is_file():
        return str(direct_svg)

    # 3. Bundled fallback in assets/svg_icons/<id>.svg
    fallback_svg = ASSETS_SVG_FALLBACK_DIR / f"{icon_id}.svg"
    if fallback_svg.is_file():
        return str(fallback_svg)

    logger.debug("No Lottie/SVG found for icon_id=%r", icon_id)
    return None


def render_show_lottie(scene: Any, state, action) -> None:
    """Display the resolved icon for ``action.lottie_id`` with a spring-pop
    entrance, brief hold, and fade-out.  Tagged ``presentation`` so the
    next presentation action auto-clears it.
    """
    icon_id = (getattr(action, "lottie_id", None) or "").strip()
    if not icon_id:
        logger.debug("show_lottie: empty lottie_id, skipping")
        return

    path = _resolve_icon_path(icon_id)
    if not path:
        logger.warning("show_lottie: no asset found for id=%r", icon_id)
        return

    try:
        from manim import FadeIn, FadeOut, SVGMobject
    except ImportError as e:
        logger.warning("Manim SVGMobject unavailable: %s", e)
        return

    try:
        mob = SVGMobject(path)
    except Exception as e:
        logger.warning("SVGMobject load failed (%s): %s", path, e)
        return

    # Sizing
    target_height = float(getattr(action, "scale", 0) or 0) * 1.0
    if target_height <= 0:
        target_height = 2.4  # default height in canvas units
    try:
        mob.set_height(target_height)
    except Exception:
        pass

    # Position — default to upper-mid area in shorts (above text card)
    pos = (getattr(action, "position", "") or "").strip().lower()
    is_shorts = getattr(state, "mode", "long") == "shorts"
    if pos in ("top", "upper"):
        cy = 4.4 if is_shorts else 2.4
    elif pos in ("bottom", "lower"):
        cy = -3.2 if is_shorts else -2.4
    elif pos == "center":
        cy = 0.0
    else:
        cy = 4.4 if is_shorts else 0.0  # default: upper for shorts, center for long-form

    try:
        mob.move_to([0, cy, 0])
    except Exception:
        pass
    mob.set_z_index(72)  # above content text + cards, below subtitle

    # Spring-pop entrance via rate_func
    try:
        from rendering_engine.easing import spring_out
        rf = spring_out
    except Exception:
        rf = None

    duration = max(0.6, float(getattr(action, "duration", 1.0)))
    pop_in = 0.40
    hold = max(0.1, duration - 0.7)
    fade_out = 0.30

    try:
        if rf is not None:
            scene.play(FadeIn(mob, scale=0.6, rate_func=rf), run_time=pop_in)
        else:
            scene.play(FadeIn(mob, scale=0.6), run_time=pop_in)
    except Exception:
        scene.add(mob)

    if hold > 0:
        scene.wait(hold)

    try:
        scene.play(FadeOut(mob), run_time=fade_out)
    except Exception:
        try:
            scene.remove(mob)
        except Exception:
            pass

    import uuid
    key = f"lottie_{icon_id}_{uuid.uuid4().hex[:6]}"
    state.objects[key] = mob
    state._categories[key] = "presentation"
