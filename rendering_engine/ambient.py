"""Ambient margin decorations — drifting geometric shapes in the side strips.

These render at z=-60 (above the gradient/particles, behind any content) and
sit only in the margins outside the safe area where text and diagrams live.
A slow rotation + sin-wave drift keeps the canvas feeling alive.

Shapes are decorative only — they have no semantic tie to the script.
Toggle via ``ENABLE_AMBIENT_DECOR`` in :mod:`config`.
"""

from __future__ import annotations

import logging
import math
import random
from typing import Any

from manim import (
    Circle,
    RegularPolygon,
    Star,
    Triangle,
)

from rendering_engine.styles import (
    SAFE_AREA_BOTTOM,
    SAFE_AREA_LEFT,
    SAFE_AREA_RIGHT,
    SAFE_AREA_TOP,
)
from rendering_engine.themes import get_theme

logger = logging.getLogger(__name__)


# Margin strips — where shapes are allowed to live.  Outside the safe area
# but inside the visible canvas (-7.1..7.1 horizontally, -4..4 vertically).
_MARGIN_LEFT_X = (-7.0, SAFE_AREA_LEFT - 0.1)
_MARGIN_RIGHT_X = (SAFE_AREA_RIGHT + 0.1, 7.0)
_MARGIN_TOP_Y = (SAFE_AREA_TOP + 0.05, 3.85)
_MARGIN_BOTTOM_Y = (-3.85, SAFE_AREA_BOTTOM - 0.05)


def _build_shape(rng: random.Random, color):
    """Pick a random decorative shape with random size + low opacity."""
    kind = rng.choice(["star", "polygon5", "polygon6", "circle", "triangle"])
    size = rng.uniform(0.22, 0.55)
    opacity_stroke = rng.uniform(0.18, 0.32)
    opacity_fill = rng.uniform(0.05, 0.15)

    if kind == "star":
        mob = Star(n=5, outer_radius=size, inner_radius=size * 0.42, color=color)
    elif kind == "polygon5":
        mob = RegularPolygon(n=5, color=color).scale(size)
    elif kind == "polygon6":
        mob = RegularPolygon(n=6, color=color).scale(size)
    elif kind == "triangle":
        mob = Triangle(color=color).scale(size)
    else:
        mob = Circle(radius=size, color=color)

    mob.set_stroke(color, width=1.5, opacity=opacity_stroke)
    mob.set_fill(color, opacity=opacity_fill)
    return mob


def _random_margin_position(rng: random.Random) -> tuple[float, float]:
    """Pick a point in one of the four margin strips (left/right/top/bottom)."""
    strip = rng.choice(["left", "right", "top", "bottom"])
    if strip == "left":
        x = rng.uniform(*_MARGIN_LEFT_X)
        y = rng.uniform(-3.8, 3.8)
    elif strip == "right":
        x = rng.uniform(*_MARGIN_RIGHT_X)
        y = rng.uniform(-3.8, 3.8)
    elif strip == "top":
        x = rng.uniform(-7.0, 7.0)
        y = rng.uniform(*_MARGIN_TOP_Y)
    else:
        x = rng.uniform(-7.0, 7.0)
        y = rng.uniform(*_MARGIN_BOTTOM_Y)
    return (x, y)


def apply_margin_decor(scene: Any, category: str = "", count: int = 6) -> list:
    """Drop a handful of decorative shapes into the canvas margins.

    Returns the list of mobjects added (so callers can clean up if needed).
    No-op if disabled via config.  All shapes drift slowly via per-shape
    sin-wave updaters and rotate at ~1 RPM.
    """
    try:
        from config import AMBIENT_DECOR_COUNT, ENABLE_AMBIENT_DECOR
    except Exception:
        ENABLE_AMBIENT_DECOR = True
        AMBIENT_DECOR_COUNT = count

    if not ENABLE_AMBIENT_DECOR:
        return []

    n = max(1, int(AMBIENT_DECOR_COUNT))
    rng = random.Random(0xA1B2 + (sum(ord(c) for c in category) if category else 0))
    theme = get_theme(category)
    palette = [c for c in (theme.primary, theme.secondary, theme.accent) if c]
    if not palette:
        palette = [theme.primary]

    added = []
    for i in range(n):
        x, y = _random_margin_position(rng)
        color = palette[i % len(palette)]
        shape = _build_shape(rng, color)
        shape.move_to([x, y, 0])
        shape.set_z_index(-60)

        # Per-shape drift parameters
        amp_x = rng.uniform(0.10, 0.35)
        amp_y = rng.uniform(0.10, 0.30)
        period = rng.uniform(12.0, 28.0)
        phase = rng.uniform(0.0, math.tau)
        spin_period = rng.uniform(40.0, 90.0) * rng.choice([-1, 1])
        anchor = (x, y)
        state = {"t": 0.0, "last_angle": 0.0}

        def _drift(mob, dt, _amp_x=amp_x, _amp_y=amp_y, _period=period,
                   _phase=phase, _spin=spin_period,
                   _anchor=anchor, _s=state):
            _s["t"] += dt
            try:
                t = _s["t"]
                ox = _amp_x * math.sin(2 * math.pi * t / _period + _phase)
                oy = _amp_y * math.cos(2 * math.pi * t / _period * 0.6 + _phase)
                mob.move_to([_anchor[0] + ox, _anchor[1] + oy, 0])
                # Incremental rotation (rotate about own center)
                target_angle = 2 * math.pi * t / _spin
                delta = target_angle - _s["last_angle"]
                _s["last_angle"] = target_angle
                mob.rotate(delta)
            except Exception:
                pass

        shape.add_updater(_drift)
        scene.add(shape)
        added.append(shape)

    return added
