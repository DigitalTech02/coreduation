"""Channel branding — animated intro/outro cards and persistent watermark.

The intro card plays before the topic title card; the outro plays at the end
with a "Subscribe" CTA and topic placeholders.  A persistent watermark is
added once and stays in the corner via Manim's UpdateFromFunc trick.

All elements are gated by config flags so they can be disabled per-run.
"""

from __future__ import annotations

import logging
from typing import Any

from manim import (
    DOWN,
    LEFT,
    ORIGIN,
    RIGHT,
    UP,
    Circle,
    Create,
    FadeIn,
    FadeOut,
    GrowFromCenter,
    Rectangle,
    RoundedRectangle,
    Text,
    VGroup,
    Write,
)

from rendering_engine.styles import (
    ACCENT,
    BG_COLOR,
    CATEGORY_ACCENT,
    GLOW_OPACITY,
    MUTED,
    PRIMARY,
    WHITE,
)

logger = logging.getLogger(__name__)


def _get_branding_config():
    try:
        from config import (
            CHANNEL_NAME,
            CHANNEL_TAGLINE,
            ENABLE_BRANDING,
            ENABLE_INTRO_CARD,
            ENABLE_OUTRO_CARD,
            ENABLE_WATERMARK,
        )
        return {
            "enable": ENABLE_BRANDING,
            "intro": ENABLE_INTRO_CARD,
            "outro": ENABLE_OUTRO_CARD,
            "watermark": ENABLE_WATERMARK,
            "name": CHANNEL_NAME,
            "tagline": CHANNEL_TAGLINE,
        }
    except Exception:
        return {
            "enable": True,
            "intro": True,
            "outro": True,
            "watermark": True,
            "name": "DT2",
            "tagline": "Engineering, explained.",
        }


# ---------------------------------------------------------------------------
# Intro card (3 sec)
# ---------------------------------------------------------------------------

INTRO_DURATION = 2.6


def play_intro_card(scene: Any, category: str = "") -> None:
    """A short branded intro: a logo-mark grows, then channel name writes in."""
    cfg = _get_branding_config()
    if not (cfg["enable"] and cfg["intro"]):
        return

    accent = CATEGORY_ACCENT.get(category, ACCENT)

    outer = Circle(radius=0.55, color=accent, stroke_width=4)
    inner = Circle(radius=0.32, color=accent, stroke_width=0)
    inner.set_fill(accent, opacity=0.85)
    glyph = Text("DT2", font_size=22, color=BG_COLOR, weight="BOLD")
    glyph.move_to(inner.get_center())
    logo = VGroup(outer, inner, glyph).move_to(ORIGIN)

    name = Text(cfg["name"], font_size=42, color=WHITE, weight="BOLD")
    tagline = Text(cfg["tagline"], font_size=22, color=MUTED)

    name.next_to(logo, DOWN, buff=0.45)
    tagline.next_to(name, DOWN, buff=0.18)

    scene.play(GrowFromCenter(logo), run_time=0.55)
    scene.play(Write(name, run_time=0.55), FadeIn(tagline, shift=UP * 0.15, run_time=0.55))
    scene.wait(max(0.05, INTRO_DURATION - 1.5))
    scene.play(
        FadeOut(VGroup(logo, name, tagline), shift=UP * 0.2),
        run_time=0.4,
    )


# ---------------------------------------------------------------------------
# Outro card (subscribe CTA, ~3 sec)
# ---------------------------------------------------------------------------

OUTRO_DURATION = 3.5


def play_outro_card(scene: Any, category: str = "", topic: str = "") -> None:
    """A 'Thanks for watching — Subscribe' card with channel branding."""
    cfg = _get_branding_config()
    if not (cfg["enable"] and cfg["outro"]):
        return

    accent = CATEGORY_ACCENT.get(category, ACCENT)

    title = Text("Thanks for watching", font_size=44, color=WHITE, weight="BOLD")
    subtitle = Text(
        f"Subscribe to {cfg['name']} for more deep dives.",
        font_size=24,
        color=MUTED,
    )

    button = RoundedRectangle(
        width=3.6, height=0.85, corner_radius=0.18,
        color=accent, stroke_width=3,
    )
    button.set_fill(accent, opacity=0.92)
    button_label = Text("Subscribe", font_size=28, color=BG_COLOR, weight="BOLD")
    button_label.move_to(button.get_center())
    cta = VGroup(button, button_label)

    block = VGroup(title, subtitle, cta).arrange(DOWN, buff=0.45)
    block.move_to(ORIGIN)

    scene.play(FadeIn(title, shift=UP * 0.2), run_time=0.5)
    scene.play(FadeIn(subtitle, run_time=0.3))
    scene.play(GrowFromCenter(cta), run_time=0.5)
    try:
        scene.play(button.animate.scale(1.06), run_time=0.25, rate_func=lambda t: t)
        scene.play(button.animate.scale(1 / 1.06), run_time=0.25)
    except Exception:
        pass
    scene.wait(max(0.05, OUTRO_DURATION - 1.8))
    scene.play(FadeOut(block, shift=DOWN * 0.2), run_time=0.4)


# ---------------------------------------------------------------------------
# Persistent watermark
# ---------------------------------------------------------------------------

_WATERMARK_KEY = "__watermark"


def add_watermark(scene: Any, state, category: str = "") -> None:
    """Add a small channel-name watermark to the bottom-right corner.

    Uses an updater so it stays anchored to the camera frame even when
    ``MovingCameraScene`` zooms or pans.
    """
    cfg = _get_branding_config()
    if not (cfg["enable"] and cfg["watermark"]):
        return

    accent = CATEGORY_ACCENT.get(category, ACCENT)
    name = Text(cfg["name"], font_size=14, color=accent)
    name.set_opacity(0.55)

    camera = getattr(scene, "camera", None)
    frame = getattr(camera, "frame", None)

    def _anchor(mob):
        if frame is None:
            mob.to_corner(DOWN + RIGHT, buff=0.18)
            return
        try:
            cx = frame.get_center()[0] + frame.get_width() / 2 - mob.width / 2 - 0.18
            cy = frame.get_center()[1] - frame.get_height() / 2 + mob.height / 2 + 0.18
            mob.move_to([cx, cy, 0])
        except Exception:
            mob.to_corner(DOWN + RIGHT, buff=0.18)

    _anchor(name)
    name.add_updater(_anchor)
    scene.add(name)

    if state is not None:
        try:
            state.objects[_WATERMARK_KEY] = name
            state._categories[_WATERMARK_KEY] = "persistent"
        except Exception:
            pass
