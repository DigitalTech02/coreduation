"""Stripe.com-style mesh gradient background — opt-in, both pipelines.

Replaces the simple vertical gradient + particle field with three or four
overlapping radial color blobs that drift slowly.  Produces the modern
"SaaS landing page" background look without the cost of a real shader or
external tool.

Toggleable via ``ENABLE_MESH_GRADIENT`` config flag.  Off by default —
the existing themed gradient is the safe fallback.

Composition (z-index):
  z=-100  Solid backdrop (dark navy/black)
  z=-95   3-4 large translucent radial circles (the "blobs"), each in a
          different mood-color, with sin-wave drift updaters

The blobs are sized larger than the canvas (radius 5-7 units) so their
edges are off-screen and only the colored centers/midtones show — that's
what gives the smooth gradient feel without hard circle outlines.
"""

from __future__ import annotations

import logging
import math
import random
from typing import Any

from manim import Circle, Rectangle, VGroup

from rendering_engine.styles import BG_COLOR

logger = logging.getLogger(__name__)


# Per-category mesh palettes — pick three colors that harmonize.  All
# blobs render at low opacity so they BLEND into a smooth gradient rather
# than reading as 3 distinct circles.
_MESH_PALETTES: dict[str, tuple[str, str, str]] = {
    "security":           ("#ff2d55", "#bf5af2", "#0a84ff"),  # red→purple→blue
    "networking":         ("#0a84ff", "#3fdca1", "#5e5ce6"),  # blue→teal→indigo
    "data-structures":    ("#bf5af2", "#ff2d55", "#ffcc00"),  # purple→red→gold
    "programming":        ("#3fdca1", "#0a84ff", "#bf5af2"),  # green→blue→purple
    "cloud-architecture": ("#0a84ff", "#3fdca1", "#5e5ce6"),
    "system-design":      ("#ff6b1f", "#ffcc00", "#ff2d55"),  # orange→gold→red
    "business-analysis":  ("#3fdca1", "#0a84ff", "#5e5ce6"),
    "databases":          ("#ffcc00", "#ff6b1f", "#bf5af2"),
}

_DEFAULT_PALETTE = ("#0a84ff", "#bf5af2", "#3fdca1")


def apply_mesh_gradient_background(scene: Any, category: str = "") -> Any | None:
    """Paint a 3-blob mesh gradient as the scene's backdrop.

    Returns the VGroup so callers can keep a handle (rarely needed since
    the mesh sits at z=-95 and is anchored permanently to the camera).
    """
    cat = (category or "").strip().lower()
    palette = _MESH_PALETTES.get(cat, _DEFAULT_PALETTE)

    # Solid dark base — fills the whole canvas behind the blobs.
    backdrop = Rectangle(
        width=20, height=20,
        color=BG_COLOR, stroke_width=0,
        fill_color=BG_COLOR, fill_opacity=1.0,
    )
    backdrop.set_z_index(-100)
    scene.add(backdrop)

    blobs = VGroup()
    rng = random.Random(0xC07F + sum(ord(c) for c in cat))

    # 3 blobs at well-separated positions so they cover the canvas evenly.
    positions = [
        (rng.uniform(-3.0, -1.5), rng.uniform(2.0, 4.5)),
        (rng.uniform(1.5, 3.0),   rng.uniform(-1.0, 1.5)),
        (rng.uniform(-2.0, 2.0),  rng.uniform(-4.5, -2.0)),
    ]

    for color, (cx, cy) in zip(palette, positions):
        radius = rng.uniform(5.0, 6.5)
        blob = Circle(radius=radius, color=color, stroke_width=0)
        blob.set_fill(color, opacity=0.45)
        blob.move_to([cx, cy, 0])
        blob.set_z_index(-95)

        # Slow sin-wave drift so the gradient feels alive without being
        # distracting.  Each blob has its own period and phase so the
        # overall pattern never repeats cleanly.
        amp_x = rng.uniform(0.4, 0.8)
        amp_y = rng.uniform(0.3, 0.6)
        period = rng.uniform(14.0, 22.0)
        phase = rng.uniform(0.0, math.tau)
        anchor = (cx, cy)
        clock = [0.0]

        def _drift(mob, dt, _amp_x=amp_x, _amp_y=amp_y, _period=period,
                   _phase=phase, _anchor=anchor, _t=clock):
            _t[0] += dt
            try:
                t = _t[0]
                ox = _amp_x * math.sin(2 * math.pi * t / _period + _phase)
                oy = _amp_y * math.cos(2 * math.pi * t / _period * 0.7 + _phase)
                mob.move_to([_anchor[0] + ox, _anchor[1] + oy, 0])
            except Exception:
                pass

        blob.add_updater(_drift)
        blobs.add(blob)
        scene.add(blob)

    return blobs
