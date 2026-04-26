"""Render a real D3-based chart inside a Manim scene.

Falls back to a stylised text card if the Playwright render is unavailable —
the pipeline never crashes on missing optional dependencies.
"""

from __future__ import annotations

import logging
from typing import Any

from manim import (
    DOWN,
    FadeIn,
    FadeOut,
    ImageMobject,
    Text,
    UP,
    VGroup,
)

from rendering_engine.styles import (
    BODY_FONT_SIZE,
    MUTED,
    SUBTITLE_FONT_SIZE,
    TITLE_FONT_SIZE,
    WHITE,
)

logger = logging.getLogger(__name__)


def render_show_chart(scene: Any, state, action) -> None:
    """Render an animated D3 chart by importing the screenshot."""
    chart_type = action.chart_type or "bar"
    title = action.title or ""
    labels = list(action.labels)
    series = list(action.series)
    series_labels = list(action.series_labels)

    if not labels or not series:
        _render_fallback(scene, title, "Chart data missing")
        return

    image_path: str | None = None
    try:
        from charts import render_chart_to_image
        image_path = render_chart_to_image(
            chart_type, title, labels, series, series_labels,
        )
    except Exception as e:
        logger.warning("Chart render failed (%s) — falling back", e)

    if not image_path:
        _render_fallback(scene, title, ", ".join(
            f"{lbl}: {val}" for lbl, val in zip(labels, series)
        ))
        return

    try:
        img = ImageMobject(image_path)
    except Exception as e:
        logger.warning("Chart image load failed: %s", e)
        _render_fallback(scene, title, "Chart image unavailable")
        return

    if img.height > 5.5:
        img.scale(5.5 / img.height)
    if img.width > 11.5:
        img.scale(11.5 / img.width)

    scene.play(FadeIn(img, shift=UP * 0.15), run_time=0.45)
    scene.wait(max(1.0, float(action.duration) - 0.9))
    scene.play(FadeOut(img), run_time=0.4)


def _render_fallback(scene: Any, title: str, body: str) -> None:
    """Stylised text card when the real chart isn't available."""
    title_txt = Text(title or "Chart", font_size=TITLE_FONT_SIZE - 4, color=WHITE)
    body_txt = Text(body[:300] or "—", font_size=BODY_FONT_SIZE - 2, color=MUTED)
    if body_txt.width > 11.0:
        body_txt.set_width(11.0)
    block = VGroup(title_txt, body_txt).arrange(DOWN, buff=0.45)
    scene.play(FadeIn(block, shift=UP * 0.2), run_time=0.4)
    scene.wait(2.5)
    scene.play(FadeOut(block), run_time=0.3)
