"""Scene-level subtitle renderer — phrase-chunked lower-third captions.

Subtitles are generated from the narration text of each scene and displayed
as short phrase chunks during the scene's animation.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from manim import DOWN, FadeIn, FadeOut, RoundedRectangle, Text, VGroup

from rendering_engine.styles import (
    BG_COLOR,
    MUTED,
    SUBTITLE_BG_OPACITY,
    SUBTITLE_FONT_SIZE_DISPLAY,
    SUBTITLE_MAX_WIDTH,
    SUBTITLE_Y_OFFSET,
    WHITE,
)

logger = logging.getLogger(__name__)


def chunk_narration(text: str, max_words: int = 7) -> list[str]:
    """Split narration into short phrase chunks suitable for subtitles.

    Attempts to break on sentence boundaries and commas first, then falls
    back to word-count limits.
    """
    text = text.strip()
    if not text:
        return []

    sentences = re.split(r'(?<=[.!?])\s+', text)

    chunks: list[str] = []
    for sentence in sentences:
        parts = re.split(r',\s*|\s*—\s*|\s*–\s*', sentence)
        for part in parts:
            words = part.split()
            if not words:
                continue
            while words:
                chunk_words = words[:max_words]
                words = words[max_words:]
                chunk = " ".join(chunk_words)
                if chunk:
                    chunks.append(chunk)
    return chunks


def play_subtitles_for_scene(
    scene: Any,
    narration: str,
    duration: float,
    max_words: int = 7,
    position_y: float = SUBTITLE_Y_OFFSET,
) -> None:
    """Display phrase-chunked subtitles across the scene duration."""
    chunks = chunk_narration(narration, max_words=max_words)
    if not chunks:
        return

    time_per_chunk = max(0.5, duration / len(chunks))
    display_time = max(0.3, time_per_chunk - 0.3)

    for chunk_text in chunks:
        txt = Text(
            chunk_text,
            font_size=SUBTITLE_FONT_SIZE_DISPLAY,
            color=WHITE,
        )
        if txt.width > SUBTITLE_MAX_WIDTH:
            txt.set_width(SUBTITLE_MAX_WIDTH)

        bg = RoundedRectangle(
            width=txt.width + 0.5,
            height=txt.height + 0.25,
            corner_radius=0.1,
            color=BG_COLOR,
            fill_color=BG_COLOR,
            fill_opacity=SUBTITLE_BG_OPACITY,
            stroke_width=0,
        )
        bg.move_to(txt.get_center())

        subtitle = VGroup(bg, txt)
        subtitle.move_to([0, position_y, 0])

        scene.play(FadeIn(subtitle), run_time=0.15)
        scene.wait(display_time)
        scene.play(FadeOut(subtitle), run_time=0.15)
