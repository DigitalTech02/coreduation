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


def _outro_seconds() -> float:
    """Duration of the branded outro card after the last scene's narration."""
    try:
        from config import ENABLE_BRANDING, ENABLE_OUTRO_CARD
        if not (ENABLE_BRANDING and ENABLE_OUTRO_CARD):
            return 0.0
        from rendering_engine.branding import OUTRO_DURATION
        return float(OUTRO_DURATION)
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
    # Cinematic upgrade for full scene transitions (new asset 2026-05-04).
    "scene_transition": "whoosh_cinematic.mp3",
    "emphasize_text": "impact_pop.mp3",
    # Pattern-interrupt actions emitted by retention.py — get punchy SFX
    # so the visual interrupt has matching audio.
    "flash_cut": "suspenseful_boom.mp3",
    "zoom_punch": "cinematic_impact_hit.mp3",
    "glitch_transition": "cinematic_impact_hit.mp3",
    # Text reveals get a subtle pop — most beneficial in shorts where
    # text cards are the primary visual event.  Long-form gets a gentle
    # accent on every text reveal at -16 dB which is barely noticeable.
    "show_text_block": "soft_pop.mp3",
    "show_bullet_list": "click.mp3",
}


# Scene-kickoff SFX for shorts only — overlaid at each scene's video_start
# regardless of action contents.  Gives every scene a punchy audio "stamp"
# at the moment it begins, matching the user's TikTok/Reels expectation.
_SHORTS_KICKOFF_SFX: dict[str, str] = {
    "hook":       "suspenseful_boom.mp3",
    "dramatic":   "cinematic_impact_hit.mp3",
    "urgent":     "cinematic_impact_hit.mp3",
    "excited":    "whoosh_cinematic.mp3",
    "narrator":   "soft_pop.mp3",
    "analytical": "soft_pop.mp3",
    "calm":       "soft_pop.mp3",
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

    # Trailing runway so the outro card plays out without ffmpeg -shortest
    # cropping it. 0.6s buffer for the last scene's fade-out animation.
    outro_s = _outro_seconds()
    if outro_s > 0:
        combined += AudioSegment.silent(int((outro_s + 0.6) * 1000))

    if ENABLE_SFX and scene_actions:
        sfx_track = build_sfx_track(scene_actions, scene_durations, SFX_VOLUME_DB, scene_pauses=scene_pauses)
        if sfx_track is not None:
            # Don't truncate combined to sfx length — sfx_track only covers
            # intro+scenes (no outro silence), and truncating here would
            # crop the outro tail silence that was added above, causing the
            # last scene's narration to bleed into the outro card visually.
            # Overlay starting at t=0; pydub leaves the longer track intact.
            combined = combined.overlay(sfx_track, position=0)
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


def build_narration_track_from_manifest(
    scene_audio_paths: list[str],
    scene_ids: list[str],
    manifest: dict,
    output_path: str,
    *,
    scene_actions: list[list[dict]] | None = None,
    category: str = "",
    scene_moods: list[str] | None = None,
    voice_moods: list[str] | None = None,
    music_playback_mode: str | None = None,
    music_highlight_moods: str | None = None,
    shorts_kickoff_sfx: bool = False,
) -> str:
    """Lay narration audio onto the timeline declared by the renderer manifest.

    The manifest (written by ``rendering_engine.full_video_scene`` during
    Manim render) gives the actual ``video_start_seconds`` and
    ``video_end_seconds`` for each scene in the silent video.  Each scene's
    TTS mp3 is overlaid at exactly its ``video_start_seconds`` so the
    narration can never drift relative to what the viewer sees, regardless
    of how long action animations actually took to play.

    The output's total duration equals ``manifest["total_video_duration"]``,
    so ``ffmpeg -shortest`` won't crop the outro and no trailing pad is
    required.

    SFX (per action) and per-mood background music are also positioned via
    the manifest: SFX uses ``video_start + (action_idx/n_actions) * audio_duration``;
    music swaps at scene boundaries that match the visual cuts.

    Falls back gracefully if a scene_id isn't in the manifest (logs warning,
    uses positional match).  Caller should fall back to
    ``build_semantic_narration_track`` if the manifest itself is unavailable.
    """
    from config import ENABLE_BACKGROUND_MUSIC, ENABLE_SFX, MUSIC_VOLUME_DB, SFX_VOLUME_DB

    if not scene_audio_paths:
        raise ValueError("scene_audio_paths must not be empty")
    if len(scene_ids) != len(scene_audio_paths):
        raise ValueError("scene_ids and scene_audio_paths must have the same length")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    total_dur_s = float(manifest.get("total_video_duration", 0.0))
    if total_dur_s <= 0:
        raise ValueError("Manifest has no valid total_video_duration")
    total_ms = int(round(total_dur_s * 1000))

    track = AudioSegment.silent(total_ms)
    scene_by_id = {s.get("scene_id"): s for s in manifest.get("scenes", [])}
    manifest_list = manifest.get("scenes", [])

    placed_video_starts: list[float] = []
    placed_video_ends: list[float] = []
    placed_audio_durations: list[float] = []
    placed_actions: list[list[dict]] = []
    placed_moods: list[str] = []
    placed_voice_moods: list[str] = []

    for i, (sid, p) in enumerate(zip(scene_ids, scene_audio_paths)):
        m = scene_by_id.get(sid)
        if m is None and i < len(manifest_list):
            logger.warning(
                "scene_id '%s' not in manifest; falling back to positional match", sid,
            )
            m = manifest_list[i]
        if m is None:
            logger.warning("Scene '%s' not in manifest — skipping in mux", sid)
            continue

        try:
            seg = AudioSegment.from_file(p)
        except Exception as e:
            logger.warning("Could not load TTS audio for '%s' (%s): %s", sid, p, e)
            continue

        v_start = float(m.get("video_start_seconds", 0.0))
        v_end = float(m.get("video_end_seconds", v_start + len(seg) / 1000.0))
        pos_ms = int(round(v_start * 1000))
        if pos_ms < 0 or pos_ms >= total_ms:
            logger.warning(
                "Scene '%s' video_start=%.2fs is outside [0, %.2fs] — skipping",
                sid, v_start, total_dur_s,
            )
            continue

        # Trim mp3 if it would overrun the manifest's slot for this scene.
        # Should be rare because the renderer reserves >= audio_duration for
        # each scene, but enforce it so we never spill into the next scene.
        slot_ms = int(round((v_end - v_start) * 1000))
        if slot_ms > 0 and len(seg) > slot_ms + 50:
            logger.warning(
                "Scene '%s' TTS audio (%.2fs) longer than rendered slot (%.2fs); trimming",
                sid, len(seg) / 1000.0, slot_ms / 1000.0,
            )
            seg = seg[:slot_ms]

        track = track.overlay(seg, position=pos_ms)
        placed_video_starts.append(v_start)
        placed_video_ends.append(v_end)
        placed_audio_durations.append(len(seg) / 1000.0)
        placed_actions.append(scene_actions[i] if scene_actions and i < len(scene_actions) else [])
        placed_moods.append(scene_moods[i] if scene_moods and i < len(scene_moods) else "")
        placed_voice_moods.append(voice_moods[i] if voice_moods and i < len(voice_moods) else "")

    if ENABLE_SFX and any(placed_actions):
        sfx_track = _build_sfx_track_from_manifest(
            placed_actions, placed_video_starts, placed_audio_durations,
            total_ms, SFX_VOLUME_DB,
        )
        if sfx_track is not None:
            track = track.overlay(sfx_track, position=0)
            logger.info("Mixed SFX track into manifest-aligned narration")

    # Shorts: stamp every scene start with a mood-keyed SFX (boom on hook,
    # impact on tension, whoosh on excited/CTA, soft pop on narrator) so the
    # short feels punchy from the first frame regardless of what actions
    # the LLM emitted.
    if ENABLE_SFX and shorts_kickoff_sfx and placed_voice_moods:
        kickoff_track = _build_shorts_kickoff_track(
            placed_voice_moods, placed_video_starts, total_ms, SFX_VOLUME_DB,
        )
        if kickoff_track is not None:
            track = track.overlay(kickoff_track, position=0)
            logger.info("Mixed shorts scene-kickoff SFX")

    if ENABLE_BACKGROUND_MUSIC and placed_video_starts:
        music_track = _build_music_track_from_manifest(
            total_ms, MUSIC_VOLUME_DB, category,
            scene_moods=placed_moods,
            video_starts=placed_video_starts,
            video_ends=placed_video_ends,
            playback_mode_override=music_playback_mode,
            highlight_moods_override=music_highlight_moods,
        )
        if music_track is not None:
            track = track.overlay(music_track)
            logger.info("Mixed background music into manifest-aligned narration")

    track.export(str(out), format="mp3")
    logger.info(
        "Manifest-aligned narration: %s (%.2fs, %d scenes placed)",
        out, total_dur_s, len(placed_video_starts),
    )
    return str(out)


def _build_sfx_track_from_manifest(
    scene_actions: list[list[dict]],
    video_starts: list[float],
    audio_durations: list[float],
    total_ms: int,
    sfx_volume_db: float,
) -> AudioSegment | None:
    sfx_track = AudioSegment.silent(total_ms)
    any_sfx = False
    for actions, vstart, adur in zip(scene_actions, video_starts, audio_durations):
        n = max(len(actions), 1)
        time_per_action_ms = (adur * 1000.0) / n
        cursor_ms = float(vstart * 1000.0)
        for action in actions:
            sfx = _load_sfx(action.get("type", ""))
            if sfx is not None:
                sfx = sfx + sfx_volume_db
                pos = int(cursor_ms)
                if pos + len(sfx) <= len(sfx_track):
                    sfx_track = sfx_track.overlay(sfx, position=pos)
                    any_sfx = True
            cursor_ms += time_per_action_ms
    return sfx_track if any_sfx else None


def _build_shorts_kickoff_track(
    voice_moods: list[str],
    video_starts: list[float],
    total_ms: int,
    sfx_volume_db: float,
) -> AudioSegment | None:
    """Overlay a mood-keyed kickoff SFX at each shorts scene's video_start.

    Slightly louder than per-action SFX (-12 dB instead of -16 dB) because
    the kickoff IS the audio cue that says "new scene, look up".
    """
    track = AudioSegment.silent(total_ms)
    any_overlaid = False
    for mood, vstart in zip(voice_moods, video_starts):
        sfx_name = _SHORTS_KICKOFF_SFX.get((mood or "").lower())
        if not sfx_name:
            continue
        path = ASSETS_SFX_DIR / sfx_name
        if not path.is_file():
            continue
        try:
            sfx = AudioSegment.from_file(str(path)) + (sfx_volume_db + 4.0)
        except Exception as e:
            logger.debug("Could not load kickoff SFX %s: %s", path, e)
            continue
        pos = int(round(vstart * 1000))
        if pos + len(sfx) <= total_ms:
            track = track.overlay(sfx, position=pos)
            any_overlaid = True
    return track if any_overlaid else None


def _build_music_track_from_manifest(
    total_ms: int,
    music_volume_db: float,
    category: str,
    *,
    scene_moods: list[str],
    video_starts: list[float],
    video_ends: list[float],
    playback_mode_override: str | None = None,
    highlight_moods_override: str | None = None,
) -> AudioSegment | None:
    """Music bed that swaps mood at the actual visual scene boundaries.

    Honors ``MUSIC_PLAYBACK_MODE`` from config (overridable via
    ``playback_mode_override`` for callers who need different behavior than
    the user's default — e.g. shorts force "continuous" so a 40-second
    video isn't half-silent):
      * ``"selective"`` (default): music plays during intro card, outro card,
        and scenes whose mood is in ``MUSIC_HIGHLIGHT_MOODS`` only.  Most
        scenes are silent.  This is the user-preferred default
        (2026-05-04: continuous music with explain_loop.mp3 was irritating).
      * ``"continuous"``: legacy mode, music under every scene.
      * ``"off"``: returns ``None`` (no music track).
    """
    from config import (
        ENABLE_MOOD_MUSIC,
        MUSIC_HIGHLIGHT_MOODS,
        MUSIC_INCLUDE_INTRO_OUTRO_BEDS,
        MUSIC_PLAYBACK_MODE,
    )

    mode = (playback_mode_override or MUSIC_PLAYBACK_MODE or "selective").strip().lower()
    if mode == "off":
        return None
    selective = mode == "selective"

    highlight_source = highlight_moods_override or MUSIC_HIGHLIGHT_MOODS
    highlight_moods = {
        m.strip().lower()
        for m in (highlight_source or "").split(",")
        if m.strip()
    }

    track = AudioSegment.silent(total_ms)
    overlaid_any = False

    def _overlay_bed(start_ms: int, end_ms: int, mood: str) -> bool:
        nonlocal track
        end_ms = max(start_ms, min(end_ms, total_ms))
        seg_len_ms = end_ms - start_ms
        if seg_len_ms <= 0:
            return False
        loop = _load_background_music(category, mood) if (ENABLE_MOOD_MUSIC and mood) \
            else _load_background_music(category)
        if loop is None:
            return False
        loop = loop + music_volume_db
        loops = (seg_len_ms // len(loop)) + 1
        # Longer fades in selective mode so the music breathes in/out
        # rather than chopping mid-bar.
        fade = 700 if selective else 400
        fade = min(fade, max(80, seg_len_ms // 3))
        bed = (loop * loops)[:seg_len_ms].fade_in(fade).fade_out(fade)
        track = track.overlay(bed, position=start_ms)
        return True

    # Leading bed [0, scene_1_start] — covers intro + title cards.
    # In selective mode this is opt-in via MUSIC_INCLUDE_INTRO_OUTRO_BEDS
    # (off by default — user feedback: even brief stings here contributed
    # to the "continuous score" feel).  In continuous mode we always
    # cover the leading silence so the video doesn't open in dead air.
    include_lead_trail = (not selective) or MUSIC_INCLUDE_INTRO_OUTRO_BEDS
    if include_lead_trail and video_starts:
        lead_end_ms = int(round(video_starts[0] * 1000))
        if lead_end_ms > 0:
            if _overlay_bed(0, lead_end_ms, "calm"):
                overlaid_any = True

    # Per-scene beds.  In selective mode, only scenes with a highlight mood
    # get a bed; in continuous mode, every scene does.
    n_scenes = len(video_starts)
    for i, vstart in enumerate(video_starts):
        mood = (scene_moods[i] if i < len(scene_moods) else "").strip().lower()
        if selective and mood not in highlight_moods:
            continue

        if i + 1 < n_scenes:
            end_ms = int(round(video_starts[i + 1] * 1000))
        else:
            # Last scene: extend through outro only if intro/outro beds enabled
            end_ms = total_ms if include_lead_trail else int(round(video_ends[i] * 1000))
        start_ms = int(round(vstart * 1000))
        if _overlay_bed(start_ms, end_ms, mood):
            overlaid_any = True

    # Trailing bed for outro card.  Same opt-in gate as the leading bed.
    if include_lead_trail and video_ends:
        last_scene_end_ms = int(round(video_ends[-1] * 1000))
        if last_scene_end_ms < total_ms:
            if _overlay_bed(last_scene_end_ms, total_ms, "calm"):
                overlaid_any = True

    return track if overlaid_any else None


def _probe_duration_seconds(path: str) -> float | None:
    """Return media file duration in seconds via ffprobe, or None on failure."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=30,
        )
        if result.returncode != 0:
            return None
        return float(result.stdout.strip())
    except Exception:
        return None


def _pad_audio_to_video(audio_path: str, video_path: str) -> str:
    """If the silent video is longer than the narration, append silence so the
    outro card and trailing fade-outs aren't cropped by ffmpeg ``-shortest``.

    Returns the path to use as the audio input for muxing.  If padding isn't
    needed (or duration probe fails), returns ``audio_path`` unchanged.
    """
    video_dur = _probe_duration_seconds(video_path)
    audio_dur = _probe_duration_seconds(audio_path)
    if video_dur is None or audio_dur is None:
        return audio_path
    deficit = video_dur - audio_dur
    if deficit <= 0.05:
        return audio_path

    padded = AudioSegment.from_file(audio_path) + AudioSegment.silent(int(deficit * 1000))
    padded_path = audio_path.replace(".mp3", ".padded.mp3")
    padded.export(padded_path, format="mp3")
    logger.info(
        "Padded narration with %.2fs of trailing silence to match video (%.2fs -> %.2fs)",
        deficit, audio_dur, audio_dur + deficit,
    )
    return padded_path


def mux_video_with_audio(video_path: str, audio_path: str, output_path: str) -> str:
    """Combine video + audio via ffmpeg.

    The audio is first padded with silence (if needed) so it matches the
    silent video's duration — this keeps ffmpeg ``-shortest`` from clipping
    the outro card off the end of the timeline.
    """
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    out = str(dest)

    audio_for_mux = _pad_audio_to_video(audio_path, video_path)

    tmp = out + ".tmp.mp4"

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_for_mux,
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
