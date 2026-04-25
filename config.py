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
