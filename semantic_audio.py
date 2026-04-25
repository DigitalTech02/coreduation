"""Concatenate per-scene narration, mix SFX and background music, mux with video."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from pydub import AudioSegment

from rendering_engine.styles import SCENE_GAP_SECONDS, TITLE_CARD_SECONDS

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")
ASSETS_SFX_DIR = Path("assets/sfx")
ASSETS_MUSIC_DIR = Path("assets/music")

SFX_MAP: dict[str, str] = {
    "create_node": "soft_pop.wav",
    "create_connection": "connect_click.wav",
    "send_packet": "whoosh.wav",
    "send_broadcast": "multi_whoosh.wav",
    "show_table": "click.wav",
    "show_code_block": "keyboard_tick.wav",
    "show_math": "sparkle_ping.wav",
    "shake_element": "error_buzz.wav",
    "scene_transition": "transition_sweep.wav",
    "emphasize_text": "impact_pop.wav",
}


def _load_sfx(action_type: str) -> AudioSegment | None:
    """Load the SFX file for an action type, or None if missing."""
    filename = SFX_MAP.get(action_type)
    if not filename:
        return None
    path = ASSETS_SFX_DIR / filename
    if not path.is_file():
        logger.debug("SFX file not found: %s — skipping", path)
        return None
    try:
        return AudioSegment.from_file(str(path))
    except Exception as e:
        logger.warning("Failed to load SFX %s: %s", path, e)
        return None


def _load_background_music(category: str = "") -> AudioSegment | None:
    """Load a background music loop based on category."""
    candidates = [
        ASSETS_MUSIC_DIR / f"{category}_loop.mp3",
        ASSETS_MUSIC_DIR / "explain_loop.mp3",
        ASSETS_MUSIC_DIR / "curious_loop.mp3",
    ]
    for path in candidates:
        if path.is_file():
            try:
                return AudioSegment.from_file(str(path))
            except Exception as e:
                logger.warning("Failed to load music %s: %s", path, e)
    logger.debug("No background music found — skipping")
    return None


def build_sfx_track(
    scene_actions: list[list[dict]],
    scene_durations: list[float],
    sfx_volume_db: float = -16.0,
) -> AudioSegment | None:
    """Build a SFX track aligned to the narration timeline.

    ``scene_actions`` is a list of per-scene action dicts.
    ``scene_durations`` is the per-scene audio duration (same len).
    """
    from config import ENABLE_SFX

    if not ENABLE_SFX:
        return None

    total_ms = int(TITLE_CARD_SECONDS * 1000)
    for i, dur in enumerate(scene_durations):
        total_ms += int(dur * 1000)
        if i < len(scene_durations) - 1:
            total_ms += int(SCENE_GAP_SECONDS * 1000)

    sfx_track = AudioSegment.silent(total_ms)
    cursor_ms = int(TITLE_CARD_SECONDS * 1000)
    any_sfx = False

    for i, (actions, dur) in enumerate(zip(scene_actions, scene_durations)):
        n_actions = max(len(actions), 1)
        time_per_action = (dur * 1000) / n_actions
        action_cursor = cursor_ms

        for action in actions:
            sfx = _load_sfx(action.get("type", ""))
            if sfx is not None:
                sfx = sfx + sfx_volume_db
                pos = int(action_cursor)
                if pos + len(sfx) <= len(sfx_track):
                    sfx_track = sfx_track.overlay(sfx, position=pos)
                    any_sfx = True
            action_cursor += time_per_action

        cursor_ms += int(dur * 1000)
        if i < len(scene_durations) - 1:
            cursor_ms += int(SCENE_GAP_SECONDS * 1000)

    return sfx_track if any_sfx else None


def build_music_track(
    total_duration_ms: int,
    music_volume_db: float = -28.0,
    category: str = "",
) -> AudioSegment | None:
    """Loop background music to fill the total duration, ducked to volume."""
    from config import ENABLE_BACKGROUND_MUSIC

    if not ENABLE_BACKGROUND_MUSIC:
        return None

    music = _load_background_music(category)
    if music is None:
        return None

    music = music + music_volume_db

    loops_needed = (total_duration_ms // len(music)) + 1
    looped = music * loops_needed
    return looped[:total_duration_ms]


def build_semantic_narration_track(
    scene_audio_paths: list[str],
    output_path: str | None = None,
    scene_actions: list[list[dict]] | None = None,
    category: str = "",
) -> str:
    """Prepend title-length silence, insert gap silence between scenes.

    Optionally mixes SFX and background music if assets are available.
    Durations align with ``full_video_scene.run_full_video_construct`` pacing.
    """
    if not scene_audio_paths:
        raise ValueError("scene_audio_paths must not be empty")

    from config import ENABLE_BACKGROUND_MUSIC, ENABLE_SFX, MUSIC_VOLUME_DB, SFX_VOLUME_DB

    out = Path(output_path) if output_path else OUTPUT_DIR / "full_narration.mp3"
    out.parent.mkdir(parents=True, exist_ok=True)

    combined = AudioSegment.silent(int(TITLE_CARD_SECONDS * 1000))
    scene_durations: list[float] = []

    for i, p in enumerate(scene_audio_paths):
        seg = AudioSegment.from_file(p)
        scene_durations.append(len(seg) / 1000.0)
        combined += seg
        if i < len(scene_audio_paths) - 1:
            combined += AudioSegment.silent(int(SCENE_GAP_SECONDS * 1000))

    if ENABLE_SFX and scene_actions:
        sfx_track = build_sfx_track(scene_actions, scene_durations, SFX_VOLUME_DB)
        if sfx_track is not None:
            min_len = min(len(combined), len(sfx_track))
            combined = combined[:min_len].overlay(sfx_track[:min_len])
            logger.info("Mixed SFX track into narration")

    if ENABLE_BACKGROUND_MUSIC:
        music_track = build_music_track(len(combined), MUSIC_VOLUME_DB, category)
        if music_track is not None:
            combined = combined.overlay(music_track)
            logger.info("Mixed background music into narration")

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
