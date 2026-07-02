"""
Salvage script for a run where Manim wedged after writing the silent MP4
but before the parent subprocess.run() returned.

Recovers the silent video + scene_timings.json that were rescued from /tmp,
then runs the post-render steps manually:
  - manifest-aligned audio mux
  - video + audio mux
  - frame validation report

Usage:
    python salvage_run.py output/20260507_002239_semantic_tcp-three-way-handshake
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path

from models_semantic import EnrichedVideoScript
from semantic_audio import build_narration_track_from_manifest, mux_video_with_audio

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("salvage")


def _rescale_manifest_to_actual_video(manifest_path: Path, video_path: Path) -> dict:
    """Rescale every time-bearing field so audio mux uses offsets that
    exist in the *actual* silent video.  See
    ``engine._verify_concat_matches_manifest`` for the rationale.
    """
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_total = float(manifest.get("total_video_duration", 0.0))
    if manifest_total <= 0:
        return manifest
    result = subprocess.run(
        ["ffprobe", "-v", "error",
         "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1",
         str(video_path)],
        capture_output=True, text=True, timeout=20,
    )
    actual = float(result.stdout.strip())
    delta = abs(manifest_total - actual)
    if delta <= 0.5:
        logger.info("Manifest already matches video within %.2fs — no rescale", delta)
        return manifest
    scale = actual / manifest_total
    logger.warning(
        "Rescaling manifest by %.4f (manifest=%.2fs, actual=%.2fs, delta=%.2fs)",
        scale, manifest_total, actual, delta,
    )
    for key in ("intro_card_end_seconds", "title_card_end_seconds",
                "outro_start_seconds", "outro_end_seconds"):
        if key in manifest:
            manifest[key] = float(manifest[key]) * scale
    for sc in manifest.get("scenes", []) or []:
        if "video_start_seconds" in sc:
            sc["video_start_seconds"] = float(sc["video_start_seconds"]) * scale
        if "video_end_seconds" in sc:
            sc["video_end_seconds"] = float(sc["video_end_seconds"]) * scale
    manifest["total_video_duration"] = actual
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main(run_dir_arg: str) -> int:
    run_dir = Path(run_dir_arg).resolve()
    if not run_dir.is_dir():
        logger.error("Run dir not found: %s", run_dir)
        return 1

    audio_dir = run_dir / "audio"
    video_dir = run_dir / "video"
    video_dir.mkdir(exist_ok=True)

    # Move salvaged files into the layout main.py expects.
    salvage_silent = run_dir / "full_semantic_silent.mp4"
    salvage_manifest = run_dir / "scene_timings.json"
    target_silent = video_dir / "full_semantic_silent.mp4"
    target_manifest = video_dir / "scene_timings.json"

    if salvage_silent.is_file() and not target_silent.exists():
        shutil.move(str(salvage_silent), str(target_silent))
        logger.info("Moved silent video into %s", target_silent)
    if salvage_manifest.is_file() and not target_manifest.exists():
        shutil.move(str(salvage_manifest), str(target_manifest))
        logger.info("Moved scene_timings.json into %s", target_manifest)

    if not target_silent.is_file():
        logger.error("Silent video missing at %s", target_silent)
        return 1
    if not target_manifest.is_file():
        logger.error("Scene timing manifest missing at %s", target_manifest)
        return 1

    script_path = run_dir / "script.json"
    if not script_path.is_file():
        logger.error("script.json missing at %s", script_path)
        return 1
    script = EnrichedVideoScript.model_validate(
        json.loads(script_path.read_text(encoding="utf-8"))
    )

    # Re-attach audio paths so the rest of the flow has them.
    for scene in script.scenes:
        candidate = audio_dir / f"{scene.scene_id}.mp3"
        if candidate.is_file():
            scene.audio_path = str(candidate)
        else:
            logger.warning("Audio file missing for scene '%s'", scene.scene_id)

    scenes_with_audio = [s for s in script.scenes if s.audio_path]
    scene_paths = [s.audio_path for s in scenes_with_audio]
    scene_ids = [s.scene_id for s in scenes_with_audio]
    scene_actions = [
        [a.model_dump(by_alias=True) for a in s.actions]
        for s in scenes_with_audio
    ]
    scene_moods = [getattr(s, "music_mood", "") or "" for s in scenes_with_audio]

    combined_audio = str(run_dir / "full_narration.mp3")

    # Reconcile manifest with actual silent-video duration BEFORE the mux,
    # so per-scene narration is placed at offsets that exist in the
    # rendered video.  Without this the audio cues drift relative to the
    # visuals after the first ~10s.
    manifest = _rescale_manifest_to_actual_video(target_manifest, target_silent)

    logger.info("--- Manifest-aligned audio mux ---")
    build_narration_track_from_manifest(
        scene_paths,
        scene_ids,
        manifest,
        output_path=combined_audio,
        scene_actions=scene_actions,
        category=script.category,
        scene_moods=scene_moods,
    )

    final_out = str(run_dir / "final_semantic.mp4")
    logger.info("--- Final mux: video + audio ---")
    final_path = mux_video_with_audio(str(target_silent), combined_audio, final_out)
    logger.info("=== Salvage complete! Final video: %s ===", final_path)

    # Frame validation is non-blocking; skip if it errors.
    try:
        from frame_validator import format_report, validate_video_against_script
        scenes_for_validation = [s.model_dump(by_alias=True) for s in script.scenes]
        findings = validate_video_against_script(
            final_path, scenes=scenes_for_validation,
        )
        report = format_report(findings)
        for line in report.splitlines():
            logger.info("FrameValidator: %s", line)
        (run_dir / "frame_validation.json").write_text(
            json.dumps([r.to_dict() for r in findings], indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("Frame validation skipped: %s", e)

    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python salvage_run.py <run-dir>")
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
