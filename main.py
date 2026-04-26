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

def run_semantic_pipeline(topic: str, category: str = "auto") -> None:
    """Semantic pipeline: repair ids -> validate -> retention -> TTS -> audio -> render -> mux."""
    from llm_orchestrator_semantic import generate_semantic_script
    from semantic_audio import build_semantic_narration_track, mux_video_with_audio
    from semantic_repair import repair_duplicate_ids
    from semantic_validation import validate_semantic_script
    from rendering_engine.engine import render_full_semantic_video
    from tts_generator import generate_speech
    from config import RETENTION_MODE, MAX_IDLE_VISUAL_SECONDS

    run_dir = _make_run_dir(topic, "semantic")
    audio_dir = run_dir / "audio"
    video_dir = run_dir / "video"
    logger.info("Run directory: %s", run_dir)

    logger.info("--- Step 1: Generating script (semantic, category=%s) ---", category)
    script = generate_semantic_script(topic, category=category)
    logger.info(
        "Script generated with %d scenes (category: %s, subtitle: %s)",
        len(script.scenes), script.category, script.title_card_subtitle,
    )

    logger.info("--- Step 1b: Repairing duplicate definition ids ---")
    script = repair_duplicate_ids(script)

    logger.info("--- Step 1c: Validating semantic script ---")
    validate_semantic_script(script)

    if RETENTION_MODE:
        logger.info("--- Step 1d: Enriching retention beats ---")
        from retention import ensure_retention_beats
        script = ensure_retention_beats(script, max_idle_seconds=MAX_IDLE_VISUAL_SECONDS)

    try:
        from voice_moods import annotate_scenes_with_moods
        annotate_scenes_with_moods(script)
    except Exception as e:
        logger.debug("Voice mood annotation skipped: %s", e)

    script_json_path = run_dir / "script.json"
    script_json_path.write_text(
        json.dumps(script.model_dump(by_alias=True), indent=2, default=str),
        encoding="utf-8",
    )
    logger.info("Saved script JSON -> %s", script_json_path)

    if script.video_title:
        logger.info("Video title: %s", script.video_title)
    if script.suggested_youtube_title:
        logger.info("YouTube title: %s", script.suggested_youtube_title)

    logger.info("--- Step 2: Generating TTS audio ---")
    for scene in script.scenes:
        audio_path = str(audio_dir / f"{scene.scene_id}.mp3")
        mood = getattr(scene, "voice_mood", "") or None
        duration = generate_speech(scene.narration, audio_path, mood=mood)
        scene.audio_path = audio_path
        scene.audio_duration = duration
        logger.info(
            "Scene '%s' (mood=%s): audio %.2fs -> %s",
            scene.scene_id, mood or "default", duration, audio_path,
        )

    scene_paths = [s.audio_path for s in script.scenes if s.audio_path]
    scene_actions = [
        [a.model_dump(by_alias=True) for a in s.actions]
        for s in script.scenes
    ]
    scene_moods = [getattr(s, "music_mood", "") or "" for s in script.scenes]
    combined_audio = str(run_dir / "full_narration.mp3")
    build_semantic_narration_track(
        scene_paths,
        output_path=combined_audio,
        scene_actions=scene_actions,
        category=script.category,
        scene_moods=scene_moods,
    )

    logger.info("--- Step 3: Rendering full video (single Manim scene) ---")
    silent_video = render_full_semantic_video(script, output_dir=video_dir)
    if not silent_video:
        logger.error("Full semantic render failed. Aborting.")
        return

    from config import (
        ENABLE_VISION_QA,
        ENABLE_THUMBNAIL_GEN,
        ENABLE_YOUTUBE_UPLOAD,
        ENABLE_DUBS,
        DUB_LANGUAGES,
    )
    if ENABLE_VISION_QA:
        logger.info("--- Step 3b: Vision QA pass (GPT-4o) ---")
        from vision_qa import run_vision_qa, has_blocking_failures
        qa_report = run_dir / "vision_qa.json"
        issues = run_vision_qa(silent_video, report_path=str(qa_report))
        if has_blocking_failures(issues):
            logger.warning(
                "Vision QA detected %d failures. See %s",
                sum(1 for i in issues if i.severity == "fail"),
                qa_report,
            )

    logger.info("--- Step 4: Muxing video + narration ---")
    final_out = str(run_dir / "final_semantic.mp4")
    final_path = mux_video_with_audio(silent_video, combined_audio, final_out)
    logger.info("=== Pipeline complete! Final video: %s ===", final_path)

    try:
        from chrome_compositor import (
            concat_with_chrome,
            render_intro,
            render_outro,
        )
        from config import CHANNEL_NAME, CHANNEL_TAGLINE
        intro_clip = render_intro(CHANNEL_NAME, CHANNEL_TAGLINE,
                                  script.category or "", run_dir)
        outro_clip = render_outro(CHANNEL_NAME, "Subscribe for more",
                                  script.category or "", run_dir)
        if intro_clip or outro_clip:
            with_chrome = concat_with_chrome(
                final_path, intro_clip, outro_clip,
                str(run_dir / "final_with_chrome.mp4"),
            )
            if with_chrome != final_path:
                final_path = with_chrome
                logger.info("Composited Remotion chrome -> %s", final_path)
    except Exception as e:
        logger.debug("Remotion chrome step skipped: %s", e)

    if ENABLE_THUMBNAIL_GEN:
        try:
            from thumbnail_generator import generate_thumbnail
            thumb_path = run_dir / "thumbnail.jpg"
            title = script.suggested_thumbnail_text or script.video_title or topic
            generate_thumbnail(
                title=title,
                category=script.category or "",
                output_path=str(thumb_path),
            )
            logger.info("Thumbnail -> %s", thumb_path)
        except Exception as e:
            logger.warning("Thumbnail generation skipped: %s", e)

    if ENABLE_DUBS and DUB_LANGUAGES.strip():
        try:
            from dubs import generate_language_dubs
            langs = [s.strip() for s in DUB_LANGUAGES.split(",") if s.strip()]
            generate_language_dubs(
                script=script,
                silent_video=silent_video,
                run_dir=run_dir,
                languages=langs,
            )
        except Exception as e:
            logger.warning("Multi-language dubbing skipped: %s", e)

    if ENABLE_YOUTUBE_UPLOAD:
        try:
            from youtube_uploader import upload_video
            upload_video(final_path, script, run_dir=run_dir)
        except Exception as e:
            logger.warning("YouTube upload skipped: %s", e)


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
    parser.add_argument(
        "--category",
        type=str,
        default="auto",
        help=(
            "Specialty prompt category. Options: networking, data-structures, "
            "programming, cloud-architecture, system-design, business-analysis, "
            "databases, security, auto (LLM auto-detects)"
        ),
    )
    args = parser.parse_args()

    logger.info("=== Starting video generation pipeline ===")
    logger.info("Topic: %s | Engine: %s | Category: %s", args.topic, args.engine, args.category)

    if args.engine == "legacy":
        run_legacy_pipeline(args.topic)
    else:
        run_semantic_pipeline(args.topic, category=args.category)


if __name__ == "__main__":
    main()
