"""Narration density validation — warns when scripts are too dense."""

import logging
import re

logger = logging.getLogger(__name__)

TARGET_WPM_MIN = 120
TARGET_WPM_MAX = 145


def _word_count(text: str) -> int:
    return len(re.findall(r'\b\w+\b', text))


def validate_narration_density(scenes) -> None:
    """Log warnings for scenes with narration >TARGET_WPM_MAX words/minute."""
    for scene in scenes:
        wc = _word_count(scene.narration)
        dur = scene.audio_duration or scene.estimated_duration or 15.0
        wpm = (wc / dur) * 60
        if wpm > TARGET_WPM_MAX:
            logger.warning(
                "Scene '%s' narration too dense: %d words in %.1fs = %.0f WPM "
                "(target: %d-%d WPM). Consider splitting or shortening.",
                scene.scene_id, wc, dur, wpm, TARGET_WPM_MIN, TARGET_WPM_MAX,
            )
