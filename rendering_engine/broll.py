"""Render B-roll images with a Ken-Burns slow-zoom-and-pan effect."""

from __future__ import annotations

import logging
from typing import Any

from manim import (
    DOWN,
    LEFT,
    ORIGIN,
    RIGHT,
    UP,
    FadeIn,
    FadeOut,
    ImageMobject,
    Rectangle,
    RoundedRectangle,
    Text,
    VGroup,
)

from rendering_engine.styles import (
    ACCENT,
    BG_COLOR,
    MUTED,
    SUBTITLE_BG_OPACITY,
    SUBTITLE_FONT_SIZE_DISPLAY,
    WHITE,
)

logger = logging.getLogger(__name__)


def render_show_image(scene: Any, state, action) -> None:
    """Display a Ken-Burns image with optional caption.

    Generates the image lazily via the AI B-roll cache when ``image_prompt``
    is set, otherwise loads ``image_path`` directly.
    """
    path = (action.image_path or "").strip()
    if not path and (action.image_prompt or "").strip():
        try:
            from broll_generator import get_broll_image
            path = get_broll_image(action.image_prompt) or ""
        except Exception as e:
            logger.warning("B-roll generation skipped: %s", e)
            return
    if not path:
        logger.debug("show_image: no image source available")
        return

    try:
        img = ImageMobject(path)
    except Exception as e:
        logger.warning("ImageMobject load failed (%s): %s", path, e)
        return

    img.set_z_index(-5)
    if img.height > 5.0:
        img.scale(5.0 / img.height)
    if img.width > 9.0:
        img.scale(9.0 / img.width)
    img.move_to(ORIGIN)

    pan = (action.pan or "auto").lower()
    if pan == "auto":
        pan = "in"

    end_scale = 1.10
    end_offset = [0.0, 0.0, 0.0]
    if pan == "left":
        end_offset = [-0.5, 0.0, 0.0]
    elif pan == "right":
        end_offset = [0.5, 0.0, 0.0]
    elif pan == "in":
        end_scale = 1.15
    elif pan == "out":
        img.scale(1.12)
        end_scale = 1 / 1.12

    caption_group = None
    if action.caption:
        cap_txt = Text(action.caption[:120], font_size=SUBTITLE_FONT_SIZE_DISPLAY,
                       color=WHITE)
        if cap_txt.width > 9.5:
            cap_txt.set_width(9.5)
        bg = RoundedRectangle(
            width=cap_txt.width + 0.5,
            height=cap_txt.height + 0.25,
            corner_radius=0.1,
            color=BG_COLOR,
            fill_color=BG_COLOR,
            fill_opacity=SUBTITLE_BG_OPACITY,
            stroke_width=0,
        )
        bg.move_to(cap_txt.get_center())
        caption_group = VGroup(bg, cap_txt)
        caption_group.next_to(img, DOWN, buff=0.25)

    duration = max(1.5, float(action.duration))

    scene.play(FadeIn(img), run_time=0.35)
    if caption_group is not None:
        scene.play(FadeIn(caption_group, shift=UP * 0.15), run_time=0.3)
    scene.play(
        img.animate.scale(end_scale).shift(end_offset),
        run_time=duration - 0.7,
    )
    if caption_group is not None:
        scene.play(FadeOut(caption_group), run_time=0.25)
    scene.play(FadeOut(img), run_time=0.3)
