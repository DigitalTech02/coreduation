"""Word-level alignment via OpenAI Whisper — drives kinetic typography.

Returns per-word ``(start, end, text)`` tuples we can use to time karaoke-style
subtitle reveals exactly with the narration.

Caches alignment results by audio file hash so re-runs are instant.

Whisper is a heavy dependency (~1GB model + CUDA optional).  Falls back to
even time-spacing if the import or transcribe call fails.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class WordTiming:
    start: float
    end: float
    text: str


def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()[:16]


def align_words(audio_path: str) -> list[WordTiming]:
    """Return per-word timings for *audio_path*.

    Empty list on failure (caller should fall back to even spacing).
    """
    try:
        from caching import cache_json, cached_json
    except Exception:
        cache_json = lambda *a, **kw: None
        cached_json = lambda *a, **kw: None

    audio_path = str(audio_path)
    if not Path(audio_path).is_file():
        return []

    file_hash = _hash_file(audio_path)
    cached = cached_json("whisper_align", file_hash)
    if cached:
        return [WordTiming(**w) for w in cached]

    try:
        import whisper
    except ImportError:
        logger.info("openai-whisper not installed — skipping word alignment")
        return []

    try:
        from config import WHISPER_MODEL
    except Exception:
        WHISPER_MODEL = "base"

    try:
        logger.info("Whisper: loading %s model and aligning %s", WHISPER_MODEL, audio_path)
        model = whisper.load_model(WHISPER_MODEL)
        result = model.transcribe(audio_path, word_timestamps=True, verbose=False)
    except Exception as e:
        logger.warning("Whisper alignment failed: %s", e)
        return []

    timings: list[WordTiming] = []
    for seg in result.get("segments", []):
        for w in seg.get("words", []) or []:
            text = (w.get("word") or "").strip()
            start = float(w.get("start", 0.0))
            end = float(w.get("end", start))
            if text:
                timings.append(WordTiming(start=start, end=end, text=text))

    try:
        cache_json("whisper_align", [t.__dict__ for t in timings], file_hash)
    except Exception:
        pass

    logger.info("Whisper aligned %d words", len(timings))
    return timings


def split_per_scene(
    timings: list[WordTiming],
    scene_durations: list[float],
    leading_silence_s: float = 0.0,
    gap_s: float = 0.0,
) -> list[list[WordTiming]]:
    """Split a flat list of timings across scenes by per-scene duration.

    Used when the whole narration was synthesised as one MP3.  When each scene
    has its own MP3 (the current pipeline) you can call ``align_words`` per
    scene directly and this helper isn't needed.
    """
    out: list[list[WordTiming]] = []
    cursor = leading_silence_s
    idx = 0
    for dur in scene_durations:
        end = cursor + dur
        scene_words: list[WordTiming] = []
        while idx < len(timings) and timings[idx].start < end:
            w = timings[idx]
            scene_words.append(WordTiming(
                start=max(0.0, w.start - cursor),
                end=max(0.0, w.end - cursor),
                text=w.text,
            ))
            idx += 1
        out.append(scene_words)
        cursor = end + gap_s
    return out
