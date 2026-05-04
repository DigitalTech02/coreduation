"""Per-category visual themes — full palettes (bg, primary, secondary, accent).

Replaces the "one accent color per category" approach with cohesive themes so
each category looks visually distinct.

Also provides an animated gradient backdrop with a slowly drifting particle
field — both run at near-zero compute cost via Manim updaters.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass
from typing import Any

from manim import (
    BLUE,
    BLUE_B,
    BLUE_E,
    DOWN,
    Dot,
    GREEN,
    GREEN_B,
    GREEN_E,
    GREY,
    GREY_B,
    GREY_D,
    LEFT,
    ORANGE,
    PURPLE,
    PURPLE_B,
    PURPLE_E,
    RED,
    RED_B,
    RED_E,
    RIGHT,
    TEAL,
    TEAL_B,
    TEAL_E,
    UP,
    YELLOW,
    YELLOW_B,
    Line,
    Rectangle,
    RegularPolygon,
    VGroup,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Theme:
    """A category visual identity."""

    name: str
    bg: str
    bg_top: str  # gradient top
    bg_bottom: str  # gradient bottom
    primary: Any
    secondary: Any
    accent: Any
    positive: Any
    negative: Any


# Each theme uses cohesive palette: bg darkens from a tinted top to a near-black
# bottom for depth.  Accent matches the spec in `CATEGORY_ACCENT` for backward
# compat but the rest of the palette now varies per category.
THEMES: dict[str, Theme] = {
    "networking": Theme(
        name="networking",
        bg="#0a1530",
        bg_top="#102449",
        bg_bottom="#070b1a",
        primary=BLUE_B,
        secondary=TEAL,
        accent=BLUE,
        positive=GREEN_B,
        negative=RED_B,
    ),
    "data-structures": Theme(
        name="data-structures",
        bg="#1a0f2a",
        bg_top="#2a1a44",
        bg_bottom="#0d0717",
        primary=PURPLE_B,
        secondary="#b388ff",
        accent="#b388ff",
        positive=GREEN_B,
        negative=RED_B,
    ),
    "programming": Theme(
        name="programming",
        bg="#0d1f12",
        bg_top="#15331f",
        bg_bottom="#070d09",
        primary=GREEN_B,
        secondary=TEAL_B,
        accent=GREEN,
        positive=GREEN_B,
        negative=RED_B,
    ),
    "cloud-architecture": Theme(
        name="cloud-architecture",
        bg="#091a26",
        bg_top="#0f2a3d",
        bg_bottom="#040d14",
        primary="#4fc3f7",
        secondary=BLUE_B,
        accent="#4fc3f7",
        positive=GREEN_B,
        negative=RED_B,
    ),
    "system-design": Theme(
        name="system-design",
        bg="#1f1208",
        bg_top="#33200d",
        bg_bottom="#100805",
        primary=ORANGE,
        secondary=YELLOW_B,
        accent=ORANGE,
        positive=GREEN_B,
        negative=RED_B,
    ),
    "databases": Theme(
        name="databases",
        bg="#1a1408",
        bg_top="#2c2210",
        bg_bottom="#0c0904",
        primary=YELLOW_B,
        secondary=ORANGE,
        accent=YELLOW_B,
        positive=GREEN_B,
        negative=RED_B,
    ),
    "security": Theme(
        name="security",
        bg="#1f0a0f",
        bg_top="#33121a",
        bg_bottom="#100406",
        primary=RED_B,
        secondary=ORANGE,
        accent=RED_B,
        positive=GREEN_B,
        negative=RED,
    ),
    "business-analysis": Theme(
        name="business-analysis",
        bg="#0d1f1f",
        bg_top="#173535",
        bg_bottom="#070f0f",
        primary=TEAL_B,
        secondary=BLUE_B,
        accent=TEAL,
        positive=GREEN_B,
        negative=RED_B,
    ),
    "default": Theme(
        name="default",
        bg="#0f1117",
        bg_top="#171a26",
        bg_bottom="#06080d",
        primary=BLUE_B,
        secondary=TEAL,
        accent=YELLOW_B,
        positive=GREEN_B,
        negative=RED_B,
    ),
}


def get_theme(category: str) -> Theme:
    """Return a Theme for *category*, falling back to the default theme."""
    if not category:
        return THEMES["default"]
    return THEMES.get(category.lower().strip(), THEMES["default"])


# ---------------------------------------------------------------------------
# Animated gradient background
# ---------------------------------------------------------------------------

def apply_themed_background(scene: Any, category: str = "") -> Any | None:
    """Set up a vertical-gradient background, plus optional particle field.

    Returns the gradient mobject (added at the back) so callers can keep a
    reference if they want to tween it later, or ``None`` if disabled.
    """
    try:
        from config import ENABLE_GRADIENT_BACKGROUND, ENABLE_THEMED_BACKGROUNDS
    except Exception:
        ENABLE_GRADIENT_BACKGROUND = True
        ENABLE_THEMED_BACKGROUNDS = True

    theme = get_theme(category)

    try:
        scene.camera.background_color = theme.bg
    except Exception:
        pass

    if not (ENABLE_THEMED_BACKGROUNDS and ENABLE_GRADIENT_BACKGROUND):
        return None

    try:
        bg = Rectangle(width=20.0, height=12.0, stroke_width=0)
        bg.set_fill(color=[theme.bg_top, theme.bg_bottom], opacity=1.0)
        try:
            bg.set_sheen_direction(DOWN)
        except Exception:
            pass
        bg.set_z_index(-100)
        scene.add(bg)

        time_elapsed = [0.0]

        def _drift(mob, dt):
            time_elapsed[0] += dt
            try:
                mob.shift([0.0, 0.0008 * (1 if int(time_elapsed[0] * 2) % 2 == 0 else -1), 0])
            except Exception:
                pass

        bg.add_updater(_drift)
    except Exception as e:
        logger.debug("Themed background skipped: %s", e)
        bg = None

    # ------------------------------------------------------------------
    # Particle field — slow-drifting dots at z=-90 (behind decor at -60,
    # behind content at 0+, in front of gradient at -100).
    # ------------------------------------------------------------------
    try:
        from config import BACKGROUND_PARTICLE_COUNT, ENABLE_BACKGROUND_PARTICLES
    except Exception:
        ENABLE_BACKGROUND_PARTICLES = True
        BACKGROUND_PARTICLE_COUNT = 22

    if ENABLE_BACKGROUND_PARTICLES:
        try:
            _add_particle_field(scene, theme, count=BACKGROUND_PARTICLE_COUNT)
        except Exception as e:
            logger.debug("Particle field skipped: %s", e)

    return bg


# ---------------------------------------------------------------------------
# Particle field
# ---------------------------------------------------------------------------

# Safe area where text/diagrams live — particles stay outside (or are very
# faint inside) so they never compete with content.
_PARTICLE_SAFE_X = 5.5
_PARTICLE_SAFE_Y = 2.6


def _add_particle_field(scene: Any, theme: "Theme", count: int = 22) -> None:
    """Slowly drifting dots scattered across the canvas, mostly in the margins.

    Each dot has its own tiny sin-wave updater so the field never repeats
    cleanly — gives an organic ambient feel.  Z-index −90.
    """
    rng = random.Random(0xC07E + (sum(ord(c) for c in theme.name) if theme.name else 0))

    palette = [theme.primary, theme.secondary, theme.accent]
    palette = [p for p in palette if p]

    for i in range(max(1, count)):
        # Bias placement toward the margins; reject samples that would land
        # squarely in the safe area where content sits.
        for _ in range(6):
            x = rng.uniform(-7.5, 7.5)
            y = rng.uniform(-3.7, 3.7)
            in_safe = abs(x) < _PARTICLE_SAFE_X and abs(y) < _PARTICLE_SAFE_Y
            if not in_safe:
                break

        radius = rng.uniform(0.018, 0.055)
        color = palette[i % len(palette)] if palette else theme.primary
        opacity = rng.uniform(0.18, 0.42)
        if abs(x) < _PARTICLE_SAFE_X and abs(y) < _PARTICLE_SAFE_Y:
            opacity *= 0.35  # very faint when inside content area

        dot = Dot(point=[x, y, 0], radius=radius, color=color)
        dot.set_fill(color, opacity=opacity)
        dot.set_stroke(width=0)
        dot.set_z_index(-90)

        # Per-dot drift parameters — period and amplitude vary so the field
        # doesn't pulse in lockstep.
        amp_x = rng.uniform(0.05, 0.25)
        amp_y = rng.uniform(0.05, 0.20)
        period = rng.uniform(8.0, 22.0)
        phase = rng.uniform(0.0, math.tau)
        anchor = (x, y)
        state_t = [0.0]

        def _drift(mob, dt, _amp_x=amp_x, _amp_y=amp_y,
                   _period=period, _phase=phase, _anchor=anchor, _t=state_t):
            _t[0] += dt
            try:
                t = _t[0]
                ox = _amp_x * math.sin(2 * math.pi * t / _period + _phase)
                oy = _amp_y * math.cos(2 * math.pi * t / _period * 0.7 + _phase)
                mob.move_to([_anchor[0] + ox, _anchor[1] + oy, 0])
            except Exception:
                pass

        dot.add_updater(_drift)
        scene.add(dot)
