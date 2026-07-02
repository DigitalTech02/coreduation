"""Confetti / particle burst — celebrates the payoff / reward beat.

Manim-native particle effect: scatters ~50 colored shapes (squares, triangles,
small dots) from a focal point with arc trajectories under gravity, fading
out as they fall.  No assets, no deps.

Triggered automatically by ``full_video_scene.run_full_video_construct`` when
a scene's ``voice_mood == "excited"`` OR its ``scene_id`` matches the
celebration regex (final / takeaway / reveal / payoff / done / secured /
complete / success).  Works in both long-form and shorts pipelines.
"""

from __future__ import annotations

import logging
import math
import random
import re
from typing import Any

from manim import (
    DOWN,
    FadeIn,
    FadeOut,
    RIGHT,
    Square,
    Triangle,
    UP,
    VGroup,
)

logger = logging.getLogger(__name__)


# Regex matched against scene_id (case-insensitive).  Compiled once.
_CELEBRATION_RE = re.compile(
    r"\b(final|takeaway|reveal|payoff|done|secured|complete|success|cta|"
    r"protected|safe-now|locked-down|verified|wraps?-up|conclusion)\b",
    re.IGNORECASE,
)


def should_celebrate(voice_mood: str, scene_id: str, narration: str = "") -> bool:
    """Heuristic: should this scene trigger a confetti burst?

    Returns True when the scene reads as a "reward / climax" moment.
    """
    if (voice_mood or "").strip().lower() == "excited":
        return True
    if _CELEBRATION_RE.search(scene_id or ""):
        return True
    # Narration-keyword fallback for scenes the LLM tagged with a generic
    # voice_mood but that read as a payoff in the script.
    n = (narration or "").lower()
    if any(k in n for k in (
        "now you're safe", "your data is protected", "the handshake just",
        "successfully secured", "fully encrypted",
    )):
        return True
    return False


# Default confetti palette — bright, varied, readable on any panel color.
_CONFETTI_COLORS = (
    "#ff2d55",  # neon red
    "#ffcc00",  # neon gold
    "#3fdca1",  # mint green
    "#0a84ff",  # electric blue
    "#bf5af2",  # purple
    "#ffffff",  # white pop
)


def play_confetti_burst(
    scene: Any,
    *,
    origin: tuple[float, float] = (0.0, 1.0),
    count: int = 48,
    spread_x: float = 4.5,
    rise: float = 4.5,
    duration: float = 1.6,
) -> None:
    """Fire a confetti burst from *origin* outward and downward.

    Each particle: small Square or Triangle in a random palette color.
    Trajectory: parabolic — arc up + spread, then gravity pulls them down
    while they tumble (rotation animation) and fade out near the end.

    Total wall-clock time consumed: ``duration`` (default 1.6s).  Designed
    to fire BEFORE the scene's main content so it doesn't compete with
    text reveals.
    """
    rng = random.Random(0x4242)  # deterministic so re-renders are stable
    particles = VGroup()
    targets = []  # (mob, end_position, end_rotation)

    ox, oy = origin

    for _ in range(count):
        size = rng.uniform(0.10, 0.22)
        if rng.random() < 0.6:
            mob = Square(side_length=size, color=rng.choice(_CONFETTI_COLORS), stroke_width=0)
        else:
            mob = Triangle(color=rng.choice(_CONFETTI_COLORS), stroke_width=0)
            mob.scale(size * 1.2)
        mob.set_fill(mob.get_color(), opacity=1.0)
        mob.move_to([ox, oy, 0])
        mob.set_z_index(70)  # above content, below subtitle (60? — subtitle is 60)

        # Random end position: spread horizontally, falling vertically.
        end_x = ox + rng.uniform(-spread_x, spread_x)
        # Arc height before fall — bigger for particles that will land further
        end_y = oy + rise * (1.0 - abs(end_x - ox) / spread_x) - rng.uniform(2.0, 4.0)
        end_rot = rng.uniform(-math.tau, math.tau)

        particles.add(mob)
        targets.append((mob, [end_x, end_y, 0], end_rot))

    scene.add(particles)

    # Phase 1 (40%): arc up + spread + tumble
    arc_dur = duration * 0.40
    arc_anims = []
    for mob, end_pos, end_rot in targets:
        # Mid-point of trajectory: average of origin and end, with a peak boost
        peak_x = (ox + end_pos[0]) / 2.0
        peak_y = max(oy, end_pos[1]) + rise * 0.4
        try:
            arc_anims.append(mob.animate.move_to([peak_x, peak_y, 0]).rotate(end_rot * 0.5))
        except Exception:
            arc_anims.append(mob.animate.move_to([peak_x, peak_y, 0]))

    if arc_anims:
        try:
            scene.play(*arc_anims, run_time=arc_dur)
        except Exception as e:
            logger.debug("Confetti arc phase failed: %s", e)

    # Phase 2 (60%): fall + final rotate + fade
    fall_dur = duration * 0.60
    fall_anims = []
    for mob, end_pos, end_rot in targets:
        try:
            fall_anims.append(mob.animate.move_to(end_pos).rotate(end_rot * 0.5))
        except Exception:
            fall_anims.append(mob.animate.move_to(end_pos))

    if fall_anims:
        try:
            scene.play(*fall_anims, run_time=fall_dur * 0.7)
            scene.play(FadeOut(particles), run_time=fall_dur * 0.3)
        except Exception as e:
            logger.debug("Confetti fall phase failed: %s", e)

    try:
        scene.remove(particles)
    except Exception:
        pass
