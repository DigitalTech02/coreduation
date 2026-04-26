"""Per-scene mood -> voice mapping for multi-voice TTS.

Maps mood tags (``narrator``, ``excited``, ``dramatic``, ``calm``, ``analytical``,
``urgent``, ``hook``) to provider-specific voice IDs.

For OpenAI, we shuffle between the standard voices (alloy/nova/echo/onyx/fable/shimmer).
For ElevenLabs, the user can override per-mood voice IDs via env vars
(``ELEVENLABS_VOICE_ID_HOOK`` etc.) — defaults fall back to the main voice.

Provides ``annotate_scenes_with_moods`` to auto-tag scenes with a mood when
the LLM didn't supply one (uses simple heuristics on scene type/title).
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


KNOWN_MOODS: tuple[str, ...] = (
    "narrator",
    "excited",
    "dramatic",
    "calm",
    "analytical",
    "urgent",
    "hook",
)


# OpenAI voice presets — sticks to the standard `tts-1` voices
OPENAI_MOOD_VOICES: dict[str, str] = {
    "narrator":   "alloy",
    "excited":    "nova",
    "dramatic":   "onyx",
    "calm":       "shimmer",
    "analytical": "echo",
    "urgent":     "onyx",
    "hook":       "nova",
}


def _elevenlabs_voice_for_mood(mood: str, default: str) -> str:
    """ElevenLabs lookup honours per-mood env overrides."""
    key = f"ELEVENLABS_VOICE_ID_{mood.upper()}"
    return os.getenv(key, "").strip() or default


def voice_for_mood(provider: str, mood: str, default: str) -> str:
    """Return the voice id for *provider* given *mood*.

    Unknown moods fall back to *default*.
    """
    mood = (mood or "").strip().lower()
    if mood not in KNOWN_MOODS:
        return default
    if provider == "openai":
        return OPENAI_MOOD_VOICES.get(mood, default)
    if provider == "elevenlabs":
        return _elevenlabs_voice_for_mood(mood, default)
    return default


# ---------------------------------------------------------------------------
# Heuristic mood tagger
# ---------------------------------------------------------------------------

_MOOD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "hook":       ("imagine", "what if", "did you know", "consider", "ever wondered"),
    "excited":    ("amazing", "incredible", "powerful", "wow", "boom"),
    "dramatic":   ("disaster", "outage", "broken", "crash", "fail", "warning"),
    "calm":       ("simply", "in summary", "to recap", "let's review"),
    "urgent":     ("must", "critical", "important", "never", "always"),
    "analytical": ("compare", "trade-off", "complexity", "metric", "benchmark"),
}


def _infer_mood(scene: dict | object) -> str:
    """Heuristic: pick a mood based on scene title/narration keywords + index."""
    if isinstance(scene, dict):
        idx = scene.get("_idx", 0)
        title = (scene.get("title") or "").lower()
        narr = (scene.get("narration") or "").lower()
        scene_type = (scene.get("type") or "").lower()
    else:
        idx = getattr(scene, "_idx", 0)
        title = (getattr(scene, "title", "") or "").lower()
        narr = (getattr(scene, "narration", "") or "").lower()
        scene_type = ""
        try:
            scene_type = scene.type.value if hasattr(scene.type, "value") else str(scene.type)
        except Exception:
            pass

    if idx == 0:
        return "hook"

    text = f"{title} {narr}"
    for mood, keywords in _MOOD_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return mood

    if "code" in scene_type:
        return "analytical"
    return "narrator"


def annotate_scenes_with_moods(script) -> None:
    """Attach a ``voice_mood`` attribute to each scene in *script*.

    Mutates the scenes in-place.  Uses any explicit ``voice_mood`` from the
    LLM script if present (kept on the dict via ``model_extra`` or attribute);
    otherwise infers heuristically.
    """
    try:
        from config import ENABLE_MULTI_VOICE, DEFAULT_VOICE_MOOD
    except Exception:
        ENABLE_MULTI_VOICE = True
        DEFAULT_VOICE_MOOD = "narrator"

    if not ENABLE_MULTI_VOICE:
        for scene in script.scenes:
            try:
                setattr(scene, "voice_mood", DEFAULT_VOICE_MOOD)
            except Exception:
                pass
        return

    for i, scene in enumerate(script.scenes):
        try:
            existing = getattr(scene, "voice_mood", None)
            if existing:
                continue
            try:
                scene._idx = i
            except Exception:
                pass
            setattr(scene, "voice_mood", _infer_mood(scene))
            logger.debug("Scene %s mood -> %s", scene.scene_id, scene.voice_mood)
        except Exception as e:
            logger.debug("Mood inference skipped for a scene: %s", e)
