"""Concatenate per-scene narration and mux with the final silent video."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from pydub import AudioSegment

from rendering_engine.styles import SCENE_GAP_SECONDS, TITLE_CARD_SECONDS

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")


def build_semantic_narration_track(
    scene_audio_paths: list[str],
    output_path: str | None = None,
) -> str:
    """Prepend title-length silence, insert gap silence between scenes.

    Durations align with ``full_video_scene.run_full_video_construct`` pacing.
    """
    if not scene_audio_paths:
        raise ValueError("scene_audio_paths must not be empty")

    out = Path(output_path) if output_path else OUTPUT_DIR / "full_narration.mp3"
    out.parent.mkdir(parents=True, exist_ok=True)

    combined = AudioSegment.silent(int(TITLE_CARD_SECONDS * 1000))

    for i, p in enumerate(scene_audio_paths):
        seg = AudioSegment.from_file(p)
        combined += seg
        if i < len(scene_audio_paths) - 1:
            combined += AudioSegment.silent(int(SCENE_GAP_SECONDS * 1000))

    combined.export(str(out), format="mp3")
    dur_s = len(combined) / 1000.0
    logger.info("Combined narration: %s (%.2fs)", out, dur_s)
    return str(out)


def mux_video_with_audio(video_path: str, audio_path: str, output_path: str) -> str:
    """Combine video + audio via ffmpeg.  Uses -shortest so the output matches
    whichever track is shorter (ffmpeg pads last frame automatically)."""
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    out = str(dest)

    tmp = out + ".tmp.mp4"

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        tmp,
    ]

    logger.info("Muxing: %s", " ".join(cmd))
    result = subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )

    if result.returncode != 0:
        logger.error("ffmpeg mux failed:\n%s", (result.stderr or "")[-1500:])
        raise RuntimeError("ffmpeg mux failed — see log above")

    Path(out).unlink(missing_ok=True)
    shutil.move(tmp, out)
    logger.info("Final muxed video: %s", out)
    return out
