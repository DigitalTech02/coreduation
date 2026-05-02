"""Concatenate per-scene narration, mix SFX and background music, mux with video."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from pydub import AudioSegment

from rendering_engine.styles import SCENE_GAP_SECONDS, TITLE_CARD_SECONDS


def _intro_seconds() -> float:
    """Duration the branded intro card holds before the title card."""
    try:
        from config import ENABLE_BRANDING, ENABLE_INTRO_CARD
        if not (ENABLE_BRANDING and ENABLE_INTRO_CARD):
            return 0.0
        from rendering_engine.branding import INTRO_DURATION
        return float(INTRO_DURATION)
    except Exception:
        return 0.0

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")
ASSETS_SFX_DIR = Path("assets/sfx")
ASSETS_MUSIC_DIR = Path("assets/music")

SFX_MAP: dict[str, str] = {
    "create_node": "soft_pop.mp3",
    "create_connection": "connect_click.mp3",
    "send_packet": "whoosh.mp3",
    "send_broadcast": "multi_whoosh.mp3",
    "show_table": "click.mp3",
    "show_code_block": "keyboard_tick.mp3",
    "show_math": "sparkle_ping.mp3",
    "shake_element": "error_buzz.mp3",
    "scene_transition": "transition_sweep.mp3",
    "emphasize_text": "impact_pop.mp3",
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


_MOOD_MUSIC_FILES: dict[str, str] = {
    "uplifting": "uplifting_loop.mp3",
    "tense":     "tense_loop.mp3",
    "curious":   "curious_loop.mp3",
    "calm":      "calm_loop.mp3",
    "dramatic":  "dramatic_loop.mp3",
    "neutral":   "explain_loop.mp3",
    "":          "explain_loop.mp3",
}


def _load_background_music(category: str = "", mood: str = "") -> AudioSegment | None:
    """Load a background music loop based on (mood, category) preference order."""
    candidates: list[Path] = []
    if mood:
        f = _MOOD_MUSIC_FILES.get(mood.lower())
        if f:
            candidates.append(ASSETS_MUSIC_DIR / f)
    candidates.extend([
        ASSETS_MUSIC_DIR / f"{category}_loop.mp3",
        ASSETS_MUSIC_DIR / "explain_loop.mp3",
        ASSETS_MUSIC_DIR / "curious_loop.mp3",
    ])
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
    scene_pauses: list[float] | None = None,
) -> AudioSegment | None:
    """Build a SFX track aligned to the narration timeline.

    ``scene_actions`` is a list of per-scene action dicts.
    ``scene_durations`` is the per-scene audio duration (same len).
    """
    from config import ENABLE_SFX

    if not ENABLE_SFX:
        return None

    intro_s = _intro_seconds()
    total_ms = int((TITLE_CARD_SECONDS + intro_s) * 1000)
    for i, dur in enumerate(scene_durations):
        total_ms += int(dur * 1000)
        if i < len(scene_durations) - 1:
            pause_s = (scene_pauses[i] if scene_pauses and i < len(scene_pauses) else 0.0)
            total_ms += int((SCENE_GAP_SECONDS + pause_s) * 1000)

    sfx_track = AudioSegment.silent(total_ms)
    cursor_ms = int((TITLE_CARD_SECONDS + intro_s) * 1000)
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
            pause_s = (scene_pauses[i] if scene_pauses and i < len(scene_pauses) else 0.0)
            cursor_ms += int((SCENE_GAP_SECONDS + pause_s) * 1000)

    return sfx_track if any_sfx else None


def build_music_track(
    total_duration_ms: int,
    music_volume_db: float = -28.0,
    category: str = "",
    scene_moods: list[str] | None = None,
    scene_durations: list[float] | None = None,
    scene_pauses: list[float] | None = None,
) -> AudioSegment | None:
    """Loop background music to fill the total duration, ducked to volume.

    When ``scene_moods`` and ``scene_durations`` are provided and
    ``ENABLE_MOOD_MUSIC`` is on, swap loops per scene with a smooth crossfade
    so each scene's emotional tone has its own bed.
    """
    from config import ENABLE_BACKGROUND_MUSIC, ENABLE_MOOD_MUSIC

    if not ENABLE_BACKGROUND_MUSIC:
        return None

    if ENABLE_MOOD_MUSIC and scene_moods and scene_durations:
        return _build_mood_music_track(
            total_duration_ms,
            music_volume_db,
            category,
            scene_moods,
            scene_durations,
            scene_pauses=scene_pauses,
        )

    music = _load_background_music(category)
    if music is None:
        return None

    music = music + music_volume_db

    loops_needed = (total_duration_ms // len(music)) + 1
    looped = music * loops_needed
    return looped[:total_duration_ms]


def _build_mood_music_track(
    total_duration_ms: int,
    music_volume_db: float,
    category: str,
    scene_moods: list[str],
    scene_durations: list[float],
    scene_pauses: list[float] | None = None,
) -> AudioSegment | None:
    """Construct a music track that swaps loop per scene."""
    intro_s = _intro_seconds()
    title_s = TITLE_CARD_SECONDS
    leading_ms = int((intro_s + title_s) * 1000)

    track = AudioSegment.silent(total_duration_ms)

    # Background bed for the intro/title card (use neutral)
    intro_bed = _load_background_music(category, "calm")
    if intro_bed is not None and leading_ms > 0:
        intro_bed = intro_bed + music_volume_db
        loops = (leading_ms // len(intro_bed)) + 1
        track = track.overlay((intro_bed * loops)[:leading_ms])

    cursor_ms = leading_ms
    for i, (mood, dur) in enumerate(zip(scene_moods, scene_durations)):
        seg_len_ms = int(dur * 1000)
        if seg_len_ms <= 0:
            continue
        loop = _load_background_music(category, mood or "")
        pause_s = (scene_pauses[i] if scene_pauses and i < len(scene_pauses) else 0.0)
        gap_ms = int((SCENE_GAP_SECONDS + pause_s) * 1000)
        if loop is None:
            cursor_ms += seg_len_ms
            if i < len(scene_durations) - 1:
                cursor_ms += gap_ms
            continue
        loop = loop + music_volume_db
        loops = (seg_len_ms // len(loop)) + 1
        bed = (loop * loops)[:seg_len_ms].fade_in(400).fade_out(400)
        end = min(cursor_ms + len(bed), len(track))
        track = track[:cursor_ms].overlay(bed[: end - cursor_ms]) + track[end:]
        cursor_ms += seg_len_ms
        if i < len(scene_durations) - 1:
            cursor_ms += gap_ms

    return track


def build_semantic_narration_track(
    scene_audio_paths: list[str],
    output_path: str | None = None,
    scene_actions: list[list[dict]] | None = None,
    category: str = "",
    scene_moods: list[str] | None = None,
    scene_pauses: list[float] | None = None,
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

    intro_s = _intro_seconds()
    combined = AudioSegment.silent(int((TITLE_CARD_SECONDS + intro_s) * 1000))
    scene_durations: list[float] = []

    for i, p in enumerate(scene_audio_paths):
        seg = AudioSegment.from_file(p)
        scene_durations.append(len(seg) / 1000.0)
        combined += seg
        # Add breathing pause after scene (pause_after + standard gap)
        pause_s = (scene_pauses[i] if scene_pauses and i < len(scene_pauses) else 0.0)
        gap_s = SCENE_GAP_SECONDS + pause_s
        if i < len(scene_audio_paths) - 1:
            combined += AudioSegment.silent(int(gap_s * 1000))

    if ENABLE_SFX and scene_actions:
        sfx_track = build_sfx_track(scene_actions, scene_durations, SFX_VOLUME_DB, scene_pauses=scene_pauses)
        if sfx_track is not None:
            min_len = min(len(combined), len(sfx_track))
            combined = combined[:min_len].overlay(sfx_track[:min_len])
            logger.info("Mixed SFX track into narration")

    if ENABLE_BACKGROUND_MUSIC:
        music_track = build_music_track(
            len(combined),
            MUSIC_VOLUME_DB,
            category,
            scene_moods=scene_moods,
            scene_durations=scene_durations,
            scene_pauses=scene_pauses,
        )
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
