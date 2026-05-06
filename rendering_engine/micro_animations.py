"""Manim-native micro-animations — Lottie-style polish moments.

Lightweight animations for "reward / alert / status" beats that sit on top
of scene content.  All built from Manim primitives — no Lottie deps,
no asset bundles.  Designed to play quickly (0.4–1.0s) and clear on their
own, mirroring how Lottie files play once and disappear.

Each function takes (scene, ...) and plays the animation synchronously.
Auto-cleared via FadeOut at the end so they don't pile up.

Triggers (auto-injected from full_video_scene.py):
- ``play_success_stamp`` — ✓ in a green circle that pops in then settles.
                            Fires when scene_id matches "secured|verified|
                            protected|done|safe" or scene contains an
                            emphasize_text whose target is a key_phrase.
- ``play_warning_pulse`` — yellow ⚠ that pulses 3× then fades.  Fires
                            when shake_element runs OR voice_mood in
                            {dramatic, urgent}.
- ``play_padlock_close`` — small padlock whose shackle clicks down
                            into "locked" state.  Fires on scenes whose
                            narration contains "lock|encrypt|secure".
"""

from __future__ import annotations

import logging
import math
from typing import Any

from manim import (
    Arc,
    Circle,
    DOWN,
    FadeIn,
    FadeOut,
    LEFT,
    PI,
    RIGHT,
    RoundedRectangle,
    Text,
    Triangle,
    UP,
    VGroup,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Success stamp — ✓ in a circle, "green tick"
# ---------------------------------------------------------------------------

def play_success_stamp(
    scene: Any,
    *,
    position: tuple[float, float] = (0.0, 0.0),
    color: str = "#3fdca1",  # mint green
    scale: float = 1.0,
    duration: float = 0.95,
) -> None:
    """Pop-in green checkmark stamp.  Plays once and fades out.

    Sequence:
      0.00 – 0.25s   circle grows from 0 with overshoot
      0.25 – 0.50s   ✓ writes in
      0.50 – 0.85s   gentle pulse (1.0 → 1.08 → 1.0)
      0.85 – 0.95s   fade out
    """
    cx, cy = position

    circle = Circle(radius=0.85 * scale, color=color, stroke_width=10)
    circle.set_fill(color, opacity=0.18)
    circle.move_to([cx, cy, 0])

    check = Text("✓", font_size=int(110 * scale), color=color, weight="BOLD")
    check.move_to(circle.get_center() + DOWN * 0.05 * scale)

    group = VGroup(circle, check)
    group.set_z_index(75)

    # 0.00–0.25 — circle grows from zero with overshoot
    circle.scale(0.001)
    check.set_opacity(0.0)
    scene.add(group)
    try:
        scene.play(circle.animate.scale(1.0 / 0.001 * 1.08), run_time=0.20)
        scene.play(circle.animate.scale(1.0 / 1.08), run_time=0.05)
    except Exception:
        circle.scale(1.0 / 0.001)

    # 0.25–0.50 — checkmark writes in
    try:
        scene.play(FadeIn(check, scale=1.4), run_time=0.25)
    except Exception:
        check.set_opacity(1.0)

    # 0.50–0.85 — pulse
    try:
        scene.play(group.animate.scale(1.10), run_time=0.18)
        scene.play(group.animate.scale(1.0 / 1.10), run_time=0.17)
    except Exception:
        pass

    # 0.85–0.95 — fade out
    try:
        scene.play(FadeOut(group), run_time=0.10)
    except Exception:
        try:
            scene.remove(group)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Warning pulse — yellow triangle that strobes
# ---------------------------------------------------------------------------

def play_warning_pulse(
    scene: Any,
    *,
    position: tuple[float, float] = (0.0, 0.0),
    color: str = "#ffd23f",  # yellow
    scale: float = 1.0,
    pulse_count: int = 3,
    duration: float = 0.90,
) -> None:
    """Pulsing warning triangle.  Each pulse: scale 1.0 → 1.18 → 1.0."""
    cx, cy = position

    triangle = Triangle(color=color, stroke_width=10)
    triangle.scale(1.0 * scale)
    triangle.set_fill(color, opacity=0.22)
    triangle.move_to([cx, cy, 0])

    bang = Text("!", font_size=int(82 * scale), color=color, weight="BOLD")
    bang.move_to(triangle.get_center() + DOWN * 0.05 * scale)

    group = VGroup(triangle, bang)
    group.set_z_index(75)

    scene.add(group)
    try:
        scene.play(FadeIn(group, scale=0.6), run_time=0.18)
    except Exception:
        pass

    pulse_dur = (duration - 0.18 - 0.12) / max(1, pulse_count)
    for _ in range(pulse_count):
        try:
            scene.play(group.animate.scale(1.18), run_time=pulse_dur * 0.45)
            scene.play(group.animate.scale(1.0 / 1.18), run_time=pulse_dur * 0.55)
        except Exception:
            pass

    try:
        scene.play(FadeOut(group), run_time=0.12)
    except Exception:
        try:
            scene.remove(group)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Padlock close — shackle clicks down into locked state
# ---------------------------------------------------------------------------

def play_padlock_close(
    scene: Any,
    *,
    position: tuple[float, float] = (0.0, 0.0),
    color: str = "#3fdca1",
    scale: float = 1.0,
    duration: float = 0.85,
) -> None:
    """Padlock shackle drops down + locks.  Cleaner than rendering a metaphor."""
    cx, cy = position
    s = scale

    body = RoundedRectangle(
        width=1.5 * s, height=1.2 * s, corner_radius=0.16 * s,
        color=color, stroke_width=8,
        fill_color=color, fill_opacity=0.30,
    )
    body.move_to([cx, cy - 0.3 * s, 0])

    arc = Arc(
        radius=0.55 * s, angle=PI,
        color=color, stroke_width=8,
    )
    arc_open = arc.copy()
    arc_open.move_to([cx, cy + 0.85 * s, 0])  # raised
    arc_closed_pos = [cx, cy + 0.45 * s, 0]   # dropped to body top

    keyhole = Circle(radius=0.10 * s, color=color, stroke_width=0)
    keyhole.set_fill(color, opacity=1.0)
    keyhole.move_to(body.get_center() + UP * 0.08 * s)

    group = VGroup(arc_open, body, keyhole)
    group.set_z_index(75)

    scene.add(group)
    try:
        scene.play(FadeIn(group), run_time=0.22)
    except Exception:
        pass

    # Drop the shackle
    try:
        scene.play(arc_open.animate.move_to(arc_closed_pos), run_time=0.30)
    except Exception:
        arc_open.move_to(arc_closed_pos)

    # Quick "click" pulse on the body
    try:
        scene.play(body.animate.scale(1.06), run_time=0.10)
        scene.play(body.animate.scale(1.0 / 1.06), run_time=0.10)
    except Exception:
        pass

    # Hold a beat then fade
    try:
        scene.play(FadeOut(group), run_time=0.13)
    except Exception:
        try:
            scene.remove(group)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Glow pulse — quick highlight ring around a target mobject
# ---------------------------------------------------------------------------

def play_glow_pulse(
    scene: Any,
    target: Any,
    *,
    color: str = "#ffd23f",
    duration: float = 0.55,
) -> None:
    """Brief glowing ring that grows around *target* and fades — for emphasis.

    Used as the visual partner to ``emphasize_text`` so the highlighted
    phrase gets a halo, not just a color change.
    """
    if target is None:
        return
    try:
        ring = Circle(
            radius=max(target.width, target.height) * 0.65,
            color=color, stroke_width=8,
        )
        ring.move_to(target.get_center())
        ring.set_z_index(72)
        ring.set_opacity(0.0)
    except Exception as e:
        logger.debug("Glow pulse: could not measure target: %s", e)
        return

    scene.add(ring)
    try:
        scene.play(ring.animate.set_opacity(0.85).scale(1.18), run_time=duration * 0.45)
        scene.play(ring.animate.set_opacity(0.0).scale(1.4), run_time=duration * 0.55)
    except Exception:
        pass
    try:
        scene.remove(ring)
    except Exception:
        pass
