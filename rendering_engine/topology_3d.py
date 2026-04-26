"""Optional 3D / pseudo-3D topology helpers.

A full Manim ``ThreeDScene`` swap would require parallel renderers, so we use
a lightweight visual trick: when ``ENABLE_3D_TOPOLOGY`` is on, topology nodes
created in this scene get a small ``z``-offset that produces depth shading +
a slow camera orbit illusion via parallax.

This keeps the existing 2D pipeline intact while delivering a noticeable
"3D depth" wow factor on tree/mesh layouts.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Iterable

logger = logging.getLogger(__name__)


def is_enabled() -> bool:
    try:
        from config import ENABLE_3D_TOPOLOGY
        return bool(ENABLE_3D_TOPOLOGY)
    except Exception:
        return False


def apply_pseudo_depth(nodes: Iterable[Any], depth: float = 0.45) -> None:
    """Apply a soft drop-shadow + slight scale to nodes based on a fake z-coord.

    Nodes farther "back" are dimmed and scaled down slightly; nodes closer to
    the viewer keep full opacity.  Renders as a stylised isometric look.
    """
    if not is_enabled():
        return

    nodes = list(nodes)
    if not nodes:
        return

    cy = sum(n.get_center()[1] for n in nodes) / len(nodes)

    for n in nodes:
        try:
            y = n.get_center()[1]
            z_norm = max(-1.0, min(1.0, (y - cy)))
            scale = 1.0 - 0.10 * z_norm
            opacity = 1.0 - 0.20 * max(0.0, z_norm)
            n.scale(scale)
            n.set_opacity(opacity)
            try:
                from rendering_engine.styles import make_shadow
                shadow = make_shadow(n, opacity=0.18)
                n.become(shadow)
            except Exception:
                pass
        except Exception as e:
            logger.debug("pseudo-depth skipped on node: %s", e)


def add_orbit_drift(scene: Any, *, radius: float = 0.1, period: float = 25.0):
    """Add a slow orbit-like camera drift (used during 3D topology scenes)."""
    if not is_enabled():
        return None
    camera = getattr(scene, "camera", None)
    frame = getattr(camera, "frame", None)
    if frame is None:
        return None

    state = {"t": 0.0, "cx": frame.get_center()[0], "cy": frame.get_center()[1]}

    def _orbit(mob, dt):
        state["t"] += dt
        try:
            t = state["t"]
            mob.move_to([
                state["cx"] + radius * math.sin(2 * math.pi * t / period),
                state["cy"] + radius * 0.5 * math.cos(2 * math.pi * t / period),
                0,
            ])
        except Exception:
            pass

    frame.add_updater(_orbit)
    return _orbit
