"""AI Video Generation Pipeline — entry point.

Orchestrates: script generation -> TTS -> animation -> final video.
Supports two engines:
  --engine legacy    : LLM generates raw Manim code (original pipeline)
  --engine semantic  : LLM produces visual actions; one deterministic Manim pass + mux

Each run gets its own timestamped folder under ``output/``.
"""

import argparse
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


def _slugify(text: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-")


def _make_run_dir(topic: str, engine: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"{ts}_{engine}_{_slugify(topic)}"
    run_dir = Path("output") / name
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "audio").mkdir(exist_ok=True)
    (run_dir / "video").mkdir(exist_ok=True)
    return run_dir


# ---------------------------------------------------------------------------
# Legacy pipeline
# ---------------------------------------------------------------------------

def run_legacy_pipeline(topic: str) -> None:
    """Original pipeline: LLM -> raw Manim code -> error healer -> stitch."""
    from llm_orchestrator import generate_video_script
    from animation_renderer import render_scene
    from video_stitcher import stitch_video
    from tts_generator import generate_speech

    run_dir = _make_run_dir(topic, "legacy")
    audio_dir = run_dir / "audio"
    video_dir = run_dir / "video"
    logger.info("Run directory: %s", run_dir)

    logger.info("--- Step 1: Generating script (legacy) ---")
    script = generate_video_script(topic)
    logger.info("Script generated with %d scenes", len(script.scenes))

    logger.info("--- Step 2: Generating TTS audio ---")
    for scene in script.scenes:
        audio_path = str(audio_dir / f"{scene.scene_id}.mp3")
        duration = generate_speech(scene.narration, audio_path)
        scene.audio_path = audio_path
        scene.audio_duration = duration
        logger.info("Scene '%s': audio %.2fs -> %s", scene.scene_id, duration, audio_path)

    logger.info("--- Step 3: Rendering animations (legacy) ---")
    for scene in script.scenes:
        video_path = render_scene(
            manim_code=scene.manim_code,
            scene_id=scene.scene_id,
            target_duration=scene.audio_duration,
            output_dir=video_dir,
        )
        if video_path:
            scene.video_path = video_path
            logger.info("Scene '%s': video -> %s", scene.scene_id, video_path)
        else:
            logger.warning("Scene '%s': SKIPPED (render failed)", scene.scene_id)

    renderable = [s for s in script.scenes if s.video_path and s.audio_path]
    logger.info("%d/%d scenes ready for stitching", len(renderable), len(script.scenes))

    if not renderable:
        logger.error("No scenes rendered successfully. Aborting.")
        return

    logger.info("--- Step 4: Stitching final video ---")
    final_out = str(run_dir / "final.mp4")
    final_path = stitch_video(renderable, output_path=final_out)
    logger.info("=== Pipeline complete! Final video: %s ===", final_path)


# ---------------------------------------------------------------------------
# Semantic pipeline
# ---------------------------------------------------------------------------

def run_semantic_pipeline(topic: str) -> None:
    """Semantic pipeline: repair ids -> validate -> TTS -> combine audio -> render -> mux."""
    from llm_orchestrator_semantic import generate_semantic_script
    from semantic_audio import build_semantic_narration_track, mux_video_with_audio
    from semantic_repair import repair_duplicate_ids
    from semantic_validation import validate_semantic_script
    from rendering_engine.engine import render_full_semantic_video
    from tts_generator import generate_speech

    run_dir = _make_run_dir(topic, "semantic")
    audio_dir = run_dir / "audio"
    video_dir = run_dir / "video"
    logger.info("Run directory: %s", run_dir)

    logger.info("--- Step 1: Generating script (semantic) ---")
    script = generate_semantic_script(topic)
    logger.info("Script generated with %d scenes", len(script.scenes))

    logger.info("--- Step 1b: Repairing duplicate definition ids ---")
    script = repair_duplicate_ids(script)

    logger.info("--- Step 1c: Validating semantic script ---")
    validate_semantic_script(script)

    script_json_path = run_dir / "script.json"
    script_json_path.write_text(
        json.dumps(script.model_dump(by_alias=True), indent=2, default=str),
        encoding="utf-8",
    )
    logger.info("Saved script JSON -> %s", script_json_path)

    logger.info("--- Step 2: Generating TTS audio ---")
    for scene in script.scenes:
        audio_path = str(audio_dir / f"{scene.scene_id}.mp3")
        duration = generate_speech(scene.narration, audio_path)
        scene.audio_path = audio_path
        scene.audio_duration = duration
        logger.info("Scene '%s': audio %.2fs -> %s", scene.scene_id, duration, audio_path)

    scene_paths = [s.audio_path for s in script.scenes if s.audio_path]
    combined_audio = str(run_dir / "full_narration.mp3")
    build_semantic_narration_track(scene_paths, output_path=combined_audio)

    logger.info("--- Step 3: Rendering full video (single Manim scene) ---")
    silent_video = render_full_semantic_video(script, output_dir=video_dir)
    if not silent_video:
        logger.error("Full semantic render failed. Aborting.")
        return

    logger.info("--- Step 4: Muxing video + narration ---")
    final_out = str(run_dir / "final_semantic.mp4")
    final_path = mux_video_with_audio(silent_video, combined_audio, final_out)
    logger.info("=== Pipeline complete! Final video: %s ===", final_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="AI Video Generation Pipeline")
    parser.add_argument(
        "--topic",
        type=str,
        default="TCP Three-Way Handshake",
        help="Video topic",
    )
    parser.add_argument(
        "--engine",
        choices=["legacy", "semantic"],
        default="semantic",
        help="legacy: raw Manim code; semantic: action vocabulary + full render",
    )
    args = parser.parse_args()

    logger.info("=== Starting video generation pipeline ===")
    logger.info("Topic: %s | Engine: %s", args.topic, args.engine)

    if args.engine == "legacy":
        run_legacy_pipeline(args.topic)
    else:
        run_semantic_pipeline(args.topic)


if __name__ == "__main__":
    main()
