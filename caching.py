"""Persistent disk cache for expensive pipeline calls (TTS, LLM scripts).

Uses :mod:`diskcache` if available; otherwise falls back to a tiny no-op cache
so the pipeline still works in environments without the dependency installed.

Cache keys are deterministic SHA-256 hashes of the relevant inputs (text +
voice + model for TTS, topic + category + prompt-hash for LLM scripts).

Public helpers:
    cached_tts(text, voice, model, output_path) -> float | None
    cache_tts_result(text, voice, model, output_path, duration) -> None
    cached_llm_script(topic, category, prompt_hash) -> dict | None
    cache_llm_script(topic, category, prompt_hash, script_dict) -> None
    purge_cache(namespace=None) -> int
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    try:
        from config import ENABLE_CACHE
        return bool(ENABLE_CACHE)
    except Exception:
        return True


def _cache_dir() -> Path:
    try:
        from config import CACHE_DIR
        return Path(CACHE_DIR)
    except Exception:
        return Path(".cache")


def _hash(*parts: Any) -> str:
    h = hashlib.sha256()
    for p in parts:
        if isinstance(p, (dict, list)):
            h.update(json.dumps(p, sort_keys=True, default=str).encode("utf-8"))
        else:
            h.update(str(p).encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


# ---------------------------------------------------------------------------
# diskcache wrapper (graceful fallback)
# ---------------------------------------------------------------------------

class _NullCache:
    def get(self, *a, **kw):
        return None

    def set(self, *a, **kw):
        return False

    def delete(self, *a, **kw):
        return False

    def clear(self):
        return 0

    def close(self):
        pass


def _open_cache(namespace: str):
    if not _enabled():
        return _NullCache()
    try:
        import diskcache
    except ImportError:
        logger.debug("diskcache not installed — caching disabled")
        return _NullCache()
    base = _cache_dir() / namespace
    base.mkdir(parents=True, exist_ok=True)
    return diskcache.Cache(str(base))


# ---------------------------------------------------------------------------
# TTS cache — stores audio bytes + measured duration
# ---------------------------------------------------------------------------

_TTS_NAMESPACE = "tts"


def cached_tts(
    text: str, voice: str, model: str, output_path: str, speed: float = 1.0
) -> float | None:
    """If a cached TTS file exists for these inputs, copy it to *output_path*
    and return the duration.  Returns None on miss."""
    cache = _open_cache(_TTS_NAMESPACE)
    try:
        key = _hash("tts-v2", text, voice, model, round(float(speed), 3))
        entry = cache.get(key)
        if not entry:
            return None
        audio_bytes = entry.get("audio")
        duration = entry.get("duration")
        if not audio_bytes or duration is None:
            return None
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(audio_bytes)
        logger.info("TTS cache HIT (%.2fs) -> %s", duration, output_path)
        return float(duration)
    finally:
        cache.close()


def cache_tts_result(
    text: str, voice: str, model: str, output_path: str, duration: float, speed: float = 1.0
) -> None:
    """Store an already-generated TTS file under the input key."""
    cache = _open_cache(_TTS_NAMESPACE)
    try:
        key = _hash("tts-v2", text, voice, model, round(float(speed), 3))
        try:
            audio_bytes = Path(output_path).read_bytes()
        except OSError:
            return
        cache.set(key, {"audio": audio_bytes, "duration": float(duration)})
        logger.debug("TTS cache STORE (%d bytes, %.2fs)", len(audio_bytes), duration)
    finally:
        cache.close()


# ---------------------------------------------------------------------------
# LLM script cache
# ---------------------------------------------------------------------------

_LLM_NAMESPACE = "llm_scripts"


def cached_llm_script(topic: str, category: str, prompt_hash: str, model: str) -> dict | None:
    """Return a cached SemanticVideoScript dict, or None on miss."""
    cache = _open_cache(_LLM_NAMESPACE)
    try:
        key = _hash("llm-script-v1", topic, category, prompt_hash, model)
        data = cache.get(key)
        if data:
            logger.info("LLM script cache HIT (topic=%s category=%s)", topic, category)
        return data
    finally:
        cache.close()


def cache_llm_script(
    topic: str, category: str, prompt_hash: str, model: str, script_dict: dict
) -> None:
    cache = _open_cache(_LLM_NAMESPACE)
    try:
        key = _hash("llm-script-v1", topic, category, prompt_hash, model)
        cache.set(key, script_dict)
        logger.debug("LLM script cache STORE (topic=%s)", topic)
    finally:
        cache.close()


# ---------------------------------------------------------------------------
# Generic JSON cache (B-roll prompts, translations)
# ---------------------------------------------------------------------------

def cached_json(namespace: str, *parts: Any) -> Any:
    cache = _open_cache(namespace)
    try:
        key = _hash(namespace, *parts)
        return cache.get(key)
    finally:
        cache.close()


def cache_json(namespace: str, value: Any, *parts: Any) -> None:
    cache = _open_cache(namespace)
    try:
        key = _hash(namespace, *parts)
        cache.set(key, value)
    finally:
        cache.close()


# ---------------------------------------------------------------------------
# Generic binary cache (B-roll image bytes, audio bytes)
# ---------------------------------------------------------------------------

def cached_bytes(namespace: str, *parts: Any) -> bytes | None:
    cache = _open_cache(namespace)
    try:
        key = _hash(namespace, *parts)
        return cache.get(key)
    finally:
        cache.close()


def cache_bytes(namespace: str, value: bytes, *parts: Any) -> None:
    cache = _open_cache(namespace)
    try:
        key = _hash(namespace, *parts)
        cache.set(key, value)
    finally:
        cache.close()


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------

def purge_cache(namespace: str | None = None) -> int:
    """Remove cache entries.  Returns number of namespaces cleared."""
    base = _cache_dir()
    if namespace:
        target = base / namespace
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
            return 1
        return 0
    if base.is_dir():
        shutil.rmtree(base, ignore_errors=True)
        return 1
    return 0
