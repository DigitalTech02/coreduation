"""Centralized configuration — environment variables with safe defaults."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _bool(key: str, default: bool = True) -> bool:
    val = os.getenv(key, "").strip().lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "on")


def _float(key: str, default: float) -> float:
    val = os.getenv(key, "").strip()
    if not val:
        return default
    try:
        return float(val)
    except ValueError:
        return default


def _int(key: str, default: int) -> int:
    val = os.getenv(key, "").strip()
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _str(key: str, default: str) -> str:
    return os.getenv(key, default).strip() or default


# Retention
RETENTION_MODE: bool = _bool("RETENTION_MODE", True)
MAX_IDLE_VISUAL_SECONDS: float = _float("MAX_IDLE_VISUAL_SECONDS", 3.0)

# Camera
ENABLE_CAMERA_MOTION: bool = _bool("ENABLE_CAMERA_MOTION", True)
CAMERA_DEFAULT_ZOOM: float = _float("CAMERA_DEFAULT_ZOOM", 1.2)
CAMERA_MAX_ZOOM: float = _float("CAMERA_MAX_ZOOM", 1.35)

# Progress UI
ENABLE_PROGRESS_UI: bool = _bool("ENABLE_PROGRESS_UI", True)

# Subtitles
ENABLE_SUBTITLES: bool = _bool("ENABLE_SUBTITLES", True)
SUBTITLE_MODE: str = _str("SUBTITLE_MODE", "phrase")
SUBTITLE_POSITION: str = _str("SUBTITLE_POSITION", "bottom")
SUBTITLE_MAX_WORDS: int = _int("SUBTITLE_MAX_WORDS", 7)

# SFX
ENABLE_SFX: bool = _bool("ENABLE_SFX", True)
SFX_VOLUME_DB: float = _float("SFX_VOLUME_DB", -16.0)

# Background music
ENABLE_BACKGROUND_MUSIC: bool = _bool("ENABLE_BACKGROUND_MUSIC", True)
MUSIC_VOLUME_DB: float = _float("MUSIC_VOLUME_DB", -28.0)

# --- Engagement upgrade ---

# Vision QA loop (GPT-4o)
ENABLE_VISION_QA: bool = _bool("ENABLE_VISION_QA", False)
VISION_QA_SAMPLE_SECONDS: float = _float("VISION_QA_SAMPLE_SECONDS", 8.0)
VISION_QA_MODEL: str = _str("VISION_QA_MODEL", "gpt-4o")

# Cache layer (TTS + LLM scripts)
ENABLE_CACHE: bool = _bool("ENABLE_CACHE", True)
CACHE_DIR: str = _str("CACHE_DIR", ".cache")

# Branding
ENABLE_BRANDING: bool = _bool("ENABLE_BRANDING", True)
CHANNEL_NAME: str = _str("CHANNEL_NAME", "DT2")
CHANNEL_TAGLINE: str = _str("CHANNEL_TAGLINE", "Engineering, explained.")
ENABLE_INTRO_CARD: bool = _bool("ENABLE_INTRO_CARD", True)
ENABLE_OUTRO_CARD: bool = _bool("ENABLE_OUTRO_CARD", True)
ENABLE_WATERMARK: bool = _bool("ENABLE_WATERMARK", True)

# Themes
ENABLE_THEMED_BACKGROUNDS: bool = _bool("ENABLE_THEMED_BACKGROUNDS", True)
ENABLE_GRADIENT_BACKGROUND: bool = _bool("ENABLE_GRADIENT_BACKGROUND", True)

# Animated background particle field
ENABLE_BACKGROUND_PARTICLES: bool = _bool("ENABLE_BACKGROUND_PARTICLES", True)
BACKGROUND_PARTICLE_COUNT: int = _int("BACKGROUND_PARTICLE_COUNT", 22)

# Margin-zone ambient decorations (stars, polygons, circles)
ENABLE_AMBIENT_DECOR: bool = _bool("ENABLE_AMBIENT_DECOR", True)
AMBIENT_DECOR_COUNT: int = _int("AMBIENT_DECOR_COUNT", 6)

# Per-scene keyword burst (large faint background word).
# DISABLED — explicit user feedback (2026-05-04): the dimmed background word
# at very large font competes with the actual content on the canvas, even
# when relocated to a "vacant" region. Kept as a flag for future experiments
# but defaults OFF. Do not enable without re-validating against frames.
ENABLE_KEYWORD_BURST: bool = _bool("ENABLE_KEYWORD_BURST", False)

# Whisper-aligned kinetic typography
ENABLE_KINETIC_SUBTITLES: bool = _bool("ENABLE_KINETIC_SUBTITLES", False)
WHISPER_MODEL: str = _str("WHISPER_MODEL", "base")

# Whisper word-level alignment for SCHEDULED subtitles (different from
# kinetic above — this drives the regular phrase-chunk subtitle scheduler
# with REAL spoken-word timestamps instead of word-count proportional
# estimates. Eliminates subtitle/narration drift.  Requires whisper.
ENABLE_SUBTITLE_ALIGNMENT: bool = _bool("ENABLE_SUBTITLE_ALIGNMENT", True)

# Multi-voice TTS (per-scene mood)
ENABLE_MULTI_VOICE: bool = _bool("ENABLE_MULTI_VOICE", True)
DEFAULT_VOICE_MOOD: str = _str("DEFAULT_VOICE_MOOD", "narrator")

# Mood-matched background music
ENABLE_MOOD_MUSIC: bool = _bool("ENABLE_MOOD_MUSIC", True)

# Easing & camera
ENABLE_PARALLAX: bool = _bool("ENABLE_PARALLAX", True)

# Pattern interrupts
ENABLE_PATTERN_INTERRUPTS: bool = _bool("ENABLE_PATTERN_INTERRUPTS", True)
PATTERN_INTERRUPT_INTERVAL: float = _float("PATTERN_INTERRUPT_INTERVAL", 50.0)

# AI B-roll
ENABLE_AI_BROLL: bool = _bool("ENABLE_AI_BROLL", False)
BROLL_IMAGE_MODEL: str = _str("BROLL_IMAGE_MODEL", "dall-e-3")

# 3D topology
ENABLE_3D_TOPOLOGY: bool = _bool("ENABLE_3D_TOPOLOGY", True)

# Isometric drop-shadow on cards / boxed content (cheap depth)
ENABLE_ISOMETRIC_SHADOW: bool = _bool("ENABLE_ISOMETRIC_SHADOW", True)

# Export final video to Youtube_Upload/videos/ for the standalone uploader
ENABLE_YOUTUBE_UPLOAD_EXPORT: bool = _bool("ENABLE_YOUTUBE_UPLOAD_EXPORT", True)

# Remotion chrome (intro/outro/lower-thirds rendered by Node project).
# DISABLED by default (user feedback 2026-05-04): Manim already renders an
# intro card + title card + outro card inside ``final_semantic.mp4`` via
# ``play_intro_card`` / ``play_outro_card`` in the scene runner. Layering
# Remotion chrome on top duplicates both ends of the video. Re-enable only
# when the Manim intro/outro have been suppressed (e.g. via custom build).
ENABLE_REMOTION_CHROME: bool = _bool("ENABLE_REMOTION_CHROME", False)
REMOTION_INTRO_DURATION: float = _float("REMOTION_INTRO_DURATION", 3.0)
REMOTION_OUTRO_DURATION: float = _float("REMOTION_OUTRO_DURATION", 4.0)

# YouTube upload
ENABLE_YOUTUBE_UPLOAD: bool = _bool("ENABLE_YOUTUBE_UPLOAD", False)
YOUTUBE_PRIVACY_STATUS: str = _str("YOUTUBE_PRIVACY_STATUS", "private")
YOUTUBE_PRIVACY: str = YOUTUBE_PRIVACY_STATUS  # alias
YOUTUBE_CATEGORY_ID: str = _str("YOUTUBE_CATEGORY_ID", "27")  # Education

# Thumbnails
ENABLE_THUMBNAIL_GEN: bool = _bool("ENABLE_THUMBNAIL_GEN", True)

# Multi-language dubs
ENABLE_DUBS: bool = _bool("ENABLE_DUBS", False)
DUB_LANGUAGES: str = _str("DUB_LANGUAGES", "")  # comma-separated e.g. "es,hi,fr"
OPENAI_TRANSLATION_MODEL: str = _str("OPENAI_TRANSLATION_MODEL", "gpt-4o")
