"""Pattern-interrupt effects — flash_cut, zoom_punch, glitch_transition.

These are the YouTube-viral visual stings that reset the viewer's attention
every 30-45 seconds.  Each renderer is fail-soft: a missing target_id or
unsupported camera fallback simply logs a warning instead of crashing.

The retention enrichment in :mod:`retention` may auto-inject a flash_cut or
zoom_punch when a scene runs longer than ``PATTERN_INTERRUPT_INTERVAL`` without
visual variety.
"""

from __future__ import annotations

import logging
import random
from typing import Any

from manim import FadeIn, FadeOut, Rectangle, VGroup

from rendering_engine.styles import resolve_color

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# flash_cut
# ---------------------------------------------------------------------------

def render_flash_cut(scene: Any, state, action) -> None:
    color = resolve_color(action.color or "white")
    flash = Rectangle(width=20, height=12, stroke_width=0)
    flash.set_fill(color, opacity=0.45)
    flash.set_z_index(50)
    duration = max(0.04, float(action.duration))

    scene.play(FadeIn(flash), run_time=min(0.05, duration / 2))
    scene.play(FadeOut(flash), run_time=min(0.08, duration))


# ---------------------------------------------------------------------------
# zoom_punch
# ---------------------------------------------------------------------------

def render_zoom_punch(scene: Any, state, action) -> None:
    camera = getattr(scene, "camera", None)
    frame = getattr(camera, "frame", None)
    if frame is None:
        logger.debug("zoom_punch: no movable camera; skipping")
        return

    base_w = frame.get_width()
    base_center = frame.get_center().copy()

    target_center = base_center
    target_id = getattr(action, "target_id", None)
    if target_id and target_id in state.objects:
        try:
            target_center = state.objects[target_id].get_center()
        except Exception:
            pass

    intensity = float(getattr(action, "intensity", 0.10) or 0.10)
    duration = max(0.2, float(action.duration))

    zoom_w = base_w * (1.0 - intensity)
    if zoom_w < 4.0:
        zoom_w = 4.0

    half = duration / 2
    scene.play(
        frame.animate.set_width(zoom_w).move_to(target_center),
        run_time=half,
    )
    scene.play(
        frame.animate.set_width(base_w).move_to(base_center),
        run_time=half,
    )


# ---------------------------------------------------------------------------
# glitch_transition
# ---------------------------------------------------------------------------

def render_glitch_transition(scene: Any, state, action) -> None:
    """Brief RGB-split style glitch using stacked colored bands."""
    duration = max(0.2, float(action.duration))
    palette = ["#ff3344", "#33ddff", "#ffee44"]

    bands: list = []
    for i in range(7):
        h = random.uniform(0.3, 1.4)
        y = random.uniform(-3.5, 3.5)
        bar = Rectangle(width=20, height=h, stroke_width=0)
        bar.set_fill(color=random.choice(palette), opacity=random.uniform(0.4, 0.85))
        bar.move_to([random.uniform(-0.6, 0.6), y, 0])
        bar.set_z_index(40)
        bands.append(bar)
    group = VGroup(*bands)

    scene.play(FadeIn(group), run_time=min(0.12, duration / 3))
    for _ in range(2):
        for b in bands:
            try:
                b.shift([random.uniform(-0.3, 0.3), 0, 0])
            except Exception:
                pass
        scene.wait(min(0.04, duration / 8))
    scene.play(FadeOut(group), run_time=min(0.18, duration / 2))
