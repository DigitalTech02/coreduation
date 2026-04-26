"""Easing curves & camera helpers — turns linear interpolations into pleasant motion.

Provides drop-in replacements for ``linear`` ``rate_func`` values and a
``parallax`` updater that gently drifts the camera while a scene plays.

We don't import Manim's full ``rate_functions`` module because we want stable
fallbacks in test environments without Manim installed.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Easing functions
# ---------------------------------------------------------------------------

def linear(t: float) -> float:
    return t


def cubic_ease_in_out(t: float) -> float:
    if t < 0.5:
        return 4 * t * t * t
    return 1 - ((-2 * t + 2) ** 3) / 2


def cubic_ease_out(t: float) -> float:
    return 1 - (1 - t) ** 3


def quint_ease_in_out(t: float) -> float:
    if t < 0.5:
        return 16 * t ** 5
    return 1 - ((-2 * t + 2) ** 5) / 2


def back_ease_out(t: float, overshoot: float = 1.70158) -> float:
    c1 = overshoot
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def smooth_step(t: float) -> float:
    return t * t * (3 - 2 * t)


def ease_in_out(t: float) -> float:
    return cubic_ease_in_out(t)


# Manim convenience: a default "smooth" rate to substitute for linear.
DEFAULT_RATE: Callable[[float], float] = cubic_ease_in_out


# ---------------------------------------------------------------------------
# Parallax camera updater
# ---------------------------------------------------------------------------

def add_parallax(
    scene: Any,
    *,
    amplitude: float = 0.06,
    period: float = 16.0,
    enable_zoom_breathing: bool = True,
):
    """Attach a soft parallax updater to the camera frame.

    Returns the updater function so callers can ``frame.remove_updater(...)``
    later if they want to disable the drift for a particular sequence.
    """
    try:
        from config import ENABLE_PARALLAX
    except Exception:
        ENABLE_PARALLAX = True
    if not ENABLE_PARALLAX:
        return None

    camera = getattr(scene, "camera", None)
    frame = getattr(camera, "frame", None)
    if frame is None:
        return None

    state = {"t": 0.0, "base_w": frame.get_width(), "base_x": 0.0, "base_y": 0.0}

    try:
        c = frame.get_center()
        state["base_x"] = c[0]
        state["base_y"] = c[1]
    except Exception:
        pass

    def _drift(mob, dt):
        state["t"] += dt
        try:
            t = state["t"]
            x = state["base_x"] + amplitude * math.sin(2 * math.pi * t / period)
            y = state["base_y"] + amplitude * 0.6 * math.cos(2 * math.pi * t / (period * 1.3))
            mob.move_to([x, y, 0])
            if enable_zoom_breathing:
                breathe = 1.0 + 0.005 * math.sin(2 * math.pi * t / (period * 1.1))
                mob.set_width(state["base_w"] * breathe)
        except Exception:
            pass

    frame.add_updater(_drift)
    return _drift


def remove_parallax(scene: Any, updater) -> None:
    if updater is None:
        return
    camera = getattr(scene, "camera", None)
    frame = getattr(camera, "frame", None)
    if frame is None:
        return
    try:
        frame.remove_updater(updater)
    except Exception:
        pass
