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
# Volume lowered (user feedback 2026-05-04: -28 dB was too loud, irritating
# with explain_loop.mp3 playing under all narration).  -36 dB sits well below
# the voice without disappearing.
ENABLE_BACKGROUND_MUSIC: bool = _bool("ENABLE_BACKGROUND_MUSIC", True)
MUSIC_VOLUME_DB: float = _float("MUSIC_VOLUME_DB", -36.0)

# Music playback mode: "selective" (default) plays music only during the
# intro card, the outro card, and scenes whose ``music_mood`` matches
# ``MUSIC_HIGHLIGHT_MOODS``.  Most scenes are silent — keeps music as
# accent rather than constant background (user feedback 2026-05-04:
# explain_loop.mp3 throughout the video was irritating).
# "continuous" plays under every scene (legacy behaviour); "off" disables
# music entirely (equivalent to ENABLE_BACKGROUND_MUSIC=False).
MUSIC_PLAYBACK_MODE: str = _str("MUSIC_PLAYBACK_MODE", "selective")

# Moods that get a music bed in selective mode.  Comma-separated.  Values
# match ``music_mood`` in the LLM vocab (NOT ``voice_mood``):
#   uplifting | tense | curious | calm | dramatic | neutral
# Default narrowed to just ``tense`` per user feedback (2026-05-04):
# even with selective mode + dramatic scenes, the background score still
# felt continuous.  ``tense`` reliably tags only the hook scene (verified
# across 12 recent runs), so music plays for ~10s total in a typical
# 4-min video.  Add "dramatic" back if you want music on big reveals too.
MUSIC_HIGHLIGHT_MOODS: str = _str(
    "MUSIC_HIGHLIGHT_MOODS",
    "tense",
)

# Whether selective mode adds a brief music bed under the intro card +
# title card and under the outro card.  On by default — user feedback
# 2026-05-05: the video felt empty opening and closing in dead silence.
# At MUSIC_VOLUME_DB=-36 these stings are subtle (~5s + ~3.5s) and frame
# the video without contributing to "continuous score" feel.
MUSIC_INCLUDE_INTRO_OUTRO_BEDS: bool = _bool("MUSIC_INCLUDE_INTRO_OUTRO_BEDS", True)

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

# Stripe-style mesh gradient backdrop (3 colored blobs that drift).  Off
# by default — the existing themed gradient + particle field is the safe
# baseline.  Two separate flags so long-form and shorts can be controlled
# independently — typical use case is "shorts on, long-form off" since
# the long-form's themed gradient is established and a sudden swap to
# mesh would feel like a regression for that audience.
ENABLE_MESH_GRADIENT_LONG: bool = _bool("ENABLE_MESH_GRADIENT_LONG", False)
ENABLE_MESH_GRADIENT_SHORTS: bool = _bool("ENABLE_MESH_GRADIENT_SHORTS", False)

# Backwards-compat alias: if the old single ENABLE_MESH_GRADIENT is set,
# it acts as the default for whichever per-pipeline flag isn't explicitly
# set.  Lets existing setups keep working without a .env edit.
_MESH_LEGACY = _bool("ENABLE_MESH_GRADIENT", False)
if _MESH_LEGACY:
    if not os.environ.get("ENABLE_MESH_GRADIENT_LONG"):
        ENABLE_MESH_GRADIENT_LONG = True
    if not os.environ.get("ENABLE_MESH_GRADIENT_SHORTS"):
        ENABLE_MESH_GRADIENT_SHORTS = True

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

# Provider for AI B-roll image generation.
#   "fal"       — fal.ai (~$0.003/image with FLUX schnell, default)
#   "openai"    — DALL-E 3 (~$0.04/image, high quality)
#   "recraft"   — Recraft V3 (~$0.04, best for vector/illustration style)
#   "replicate" — Replicate (~$0.003 with FLUX schnell, large catalog)
# All providers fall back to OpenAI DALL-E if their API key is missing
# or the SDK isn't installed, so the pipeline never breaks.
BROLL_IMAGE_PROVIDER: str = _str("BROLL_IMAGE_PROVIDER", "fal")

# Model name when BROLL_IMAGE_PROVIDER="fal".
#   fal-ai/flux/schnell — cheapest, ~$0.003/image, ~2s latency, good quality
#   fal-ai/flux/dev     — higher quality, ~$0.025/image, ~5s latency
#   fal-ai/flux-pro     — best quality, ~$0.05/image
FAL_IMAGE_MODEL: str = _str("FAL_IMAGE_MODEL", "fal-ai/flux/schnell")

# Recraft V3 — best for vector / infographic / illustration style.
#   recraftv3              — $0.04/image
#   recraft-20b            — $0.022/image (cheaper, slightly less polished)
RECRAFT_IMAGE_MODEL: str = _str("RECRAFT_IMAGE_MODEL", "recraftv3")
# Recraft style preset.  Most useful for shorts:
#   digital_illustration   — vibrant cartoon panels (default)
#   vector_illustration    — flat vector / icon style
#   realistic_image        — photorealistic
# Sub-styles supported via slash, e.g. "digital_illustration/3d".
RECRAFT_STYLE: str = _str("RECRAFT_STYLE", "digital_illustration")

# Replicate model id.  Format is "owner/model".
#   black-forest-labs/flux-schnell    — ~$0.003/image, fastest
#   black-forest-labs/flux-dev        — ~$0.025/image, higher quality
#   black-forest-labs/flux-1.1-pro    — ~$0.04/image, best FLUX
#   stability-ai/stable-diffusion-3.5-large — SD 3.5 alternative
REPLICATE_IMAGE_MODEL: str = _str("REPLICATE_IMAGE_MODEL", "black-forest-labs/flux-schnell")

# 3D topology
ENABLE_3D_TOPOLOGY: bool = _bool("ENABLE_3D_TOPOLOGY", True)

# Isometric drop-shadow on cards / boxed content (cheap depth)
ENABLE_ISOMETRIC_SHADOW: bool = _bool("ENABLE_ISOMETRIC_SHADOW", True)

# Export final video to Youtube_Upload/videos/ for the standalone uploader
ENABLE_YOUTUBE_UPLOAD_EXPORT: bool = _bool("ENABLE_YOUTUBE_UPLOAD_EXPORT", True)

# --- Shorts pipeline (YouTube Shorts / Instagram Reels / TikTok) ---

# Generate a 50s vertical short alongside the long-form video.  Off by
# default — opted into via ``--shorts`` / ``--shorts-only`` CLI flags.
ENABLE_SHORTS: bool = _bool("ENABLE_SHORTS", False)

# Target total visual duration for shorts (seconds).  Hard-clamped to 60
# inside the orchestrator since YouTube Shorts and IG Reels both cap at
# 60s for safe cross-platform reach (TikTok allows longer but the viral
# sweet spot is 15-60s).
SHORTS_TARGET_DURATION: float = _float("SHORTS_TARGET_DURATION", 50.0)

# Whether to emit platform-named copies (youtube_short.mp4, instagram_reel.mp4,
# tiktok.mp4) of the same final short.  Same content, just renamed for
# convenience when uploading.  Off saves disk if you don't need the copies.
SHORTS_EMIT_PLATFORM_COPIES: bool = _bool("SHORTS_EMIT_PLATFORM_COPIES", True)

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
