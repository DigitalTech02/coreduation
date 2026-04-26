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
    audio_path: str | None = None,
) -> None:
    """Display subtitles across the scene duration.

    When ``audio_path`` is provided and ``ENABLE_KINETIC_SUBTITLES`` is on,
    Whisper word-level timestamps drive a karaoke-style word-by-word reveal.
    Otherwise we fall back to evenly-spaced phrase chunks.
    """
    try:
        from config import ENABLE_KINETIC_SUBTITLES
    except Exception:
        ENABLE_KINETIC_SUBTITLES = False

    if ENABLE_KINETIC_SUBTITLES and audio_path:
        try:
            from whisper_align import align_words
            words = align_words(audio_path)
            if words:
                _play_kinetic_subtitles(scene, words, duration, max_words, position_y)
                return
        except Exception as e:
            logger.debug("Kinetic subtitle path failed (%s); falling back to chunks", e)

    _play_chunked_subtitles(scene, narration, duration, max_words, position_y)


def _subtitle_y(scene: Any, offset_y: float) -> float:
    """Get the absolute Y position for subtitles, anchored to the camera frame."""
    try:
        frame = scene.camera.frame
        return frame.get_bottom()[1] - offset_y
    except Exception:
        return offset_y


def _play_chunked_subtitles(
    scene: Any,
    narration: str,
    duration: float,
    max_words: int,
    position_y: float,
) -> None:
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
        y = _subtitle_y(scene, 1.0)
        subtitle.move_to([0, y, 0])

        scene.play(FadeIn(subtitle), run_time=0.15)
        scene.wait(display_time)
        scene.play(FadeOut(subtitle), run_time=0.15)


def _play_kinetic_subtitles(
    scene: Any,
    words,  # list[WordTiming]
    duration: float,
    max_words: int,
    position_y: float,
) -> None:
    """Word-by-word karaoke reveal driven by Whisper timings.

    Words are grouped into rolling phrases of up to ``max_words``; each word
    in a phrase highlights briefly when spoken, and the whole phrase fades
    out before the next phrase begins.
    """
    if not words:
        return

    phrases: list[list] = []
    current: list = []
    for w in words:
        current.append(w)
        if len(current) >= max_words or w.text.endswith((".", "!", "?")):
            phrases.append(current)
            current = []
    if current:
        phrases.append(current)

    last_end = 0.0
    for phrase in phrases:
        if not phrase:
            continue
        phrase_text = " ".join(w.text for w in phrase)
        txt = Text(phrase_text, font_size=SUBTITLE_FONT_SIZE_DISPLAY, color=WHITE)
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
        group = VGroup(bg, txt)
        y = _subtitle_y(scene, 1.0)
        group.move_to([0, y, 0])

        wait_to = max(0.0, phrase[0].start - last_end - 0.05)
        if wait_to > 0:
            scene.wait(wait_to)
        scene.play(FadeIn(group), run_time=0.12)

        phrase_dur = max(0.4, phrase[-1].end - phrase[0].start)
        scene.wait(phrase_dur)
        scene.play(FadeOut(group), run_time=0.12)
        last_end = phrase[-1].end
