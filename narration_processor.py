"""Narration density validation — warns when scripts are too dense."""

import logging
import re

logger = logging.getLogger(__name__)

TARGET_WPM_MIN = 120
TARGET_WPM_MAX = 145


def _word_count(text: str) -> int:
    return len(re.findall(r'\b\w+\b', text))


# Sentences matching this regex are stripped from the LAST scene's narration
# because the outro card already handles the channel CTA visually.  A
# duplicated spoken "thanks for watching" creates an awkward double-ending.
_CTA_SENTENCE_RE = re.compile(
    r'(?:^|(?<=[.!?]))\s*[^.!?]*?\b('
    r'thanks?\s+for\s+watching'
    r'|like\s+(?:and|&)\s+subscribe'
    r'|don\'?t\s+forget\s+to\s+(?:like|subscribe)'
    r'|hit\s+(?:the\s+)?(?:bell|like|subscribe)'
    r'|please\s+subscribe'
    r'|see\s+you\s+(?:next\s+time|in\s+the\s+next)'
    r'|smash\s+that\s+(?:like|subscribe)'
    r')\b[^.!?]*[.!?]?',
    re.IGNORECASE,
)


def strip_outro_ctas(text: str) -> str:
    """Remove trailing 'thanks for watching / subscribe' sentences.

    The branded outro card carries the CTA visually; narrating the same line
    causes the final scene to overlap with the outro card and the narrator
    to repeat the message.  Returns the cleaned text (may be unchanged).
    """
    if not text:
        return text
    cleaned = _CTA_SENTENCE_RE.sub('', text)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def scrub_closing_ctas(scenes) -> None:
    """Strip CTA sentences from the LAST scene's narration in-place."""
    if not scenes:
        return
    last = scenes[-1]
    original = getattr(last, "narration", "") or ""
    cleaned = strip_outro_ctas(original)
    if cleaned != original:
        last.narration = cleaned or original  # never empty out the scene
        logger.info(
            "Stripped closing CTA from last scene '%s' (outro card handles it)",
            getattr(last, "scene_id", "?"),
        )


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
