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
import os
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
    from semantic_audio import (
        build_narration_track_from_manifest,
        build_semantic_narration_track,
        mux_video_with_audio,
    )
    from semantic_repair import repair_duplicate_ids
    from semantic_validation import validate_layout, validate_semantic_script
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
    validate_layout(script)

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
    from tts_generator import speed_for_pace
    from narration_processor import scrub_closing_ctas

    scrub_closing_ctas(script.scenes)

    for scene in script.scenes:
        audio_path = str(audio_dir / f"{scene.scene_id}.mp3")
        mood = getattr(scene, "voice_mood", "") or None
        pace = getattr(scene, "narration_pace", "normal") or "normal"
        speed = speed_for_pace(pace)
        duration = generate_speech(scene.narration, audio_path, mood=mood, speed=speed)
        scene.audio_path = audio_path
        scene.audio_duration = duration
        logger.info(
            "Scene '%s' (mood=%s, pace=%s): audio %.2fs -> %s",
            scene.scene_id, mood or "default", pace, duration, audio_path,
        )

    from narration_processor import validate_narration_density
    validate_narration_density(script.scenes)

    # Per-scene Whisper alignment — gives the rendering engine real
    # spoken-word timestamps so subtitle chunks anchor to actual audio
    # progression instead of evenly-divided estimates.  Cached by file
    # hash so re-runs are instant.
    try:
        from config import ENABLE_SUBTITLE_ALIGNMENT
    except Exception:
        ENABLE_SUBTITLE_ALIGNMENT = False
    if ENABLE_SUBTITLE_ALIGNMENT:
        try:
            from whisper_align import align_words
            for scene in script.scenes:
                if not scene.audio_path:
                    continue
                try:
                    timings = align_words(scene.audio_path)
                    if timings:
                        scene.whisper_words = [
                            {"start": w.start, "end": w.end, "text": w.text}
                            for w in timings
                        ]
                        logger.info(
                            "Whisper aligned scene '%s': %d words",
                            scene.scene_id, len(timings),
                        )
                except Exception as e:
                    logger.debug(
                        "Whisper alignment for %s failed: %s; "
                        "subtitles will use proportional fallback",
                        scene.scene_id, e,
                    )
        except Exception as e:
            logger.warning("Whisper alignment skipped: %s", e)

    scenes_with_audio = [s for s in script.scenes if s.audio_path]
    scene_paths = [s.audio_path for s in scenes_with_audio]
    scene_ids = [s.scene_id for s in scenes_with_audio]
    scene_actions = [
        [a.model_dump(by_alias=True) for a in s.actions]
        for s in scenes_with_audio
    ]
    scene_moods = [getattr(s, "music_mood", "") or "" for s in scenes_with_audio]
    scene_pauses = [getattr(s, "pause_after", 0.0) or 0.0 for s in scenes_with_audio]
    combined_audio = str(run_dir / "full_narration.mp3")

    logger.info("--- Step 3: Rendering full video (single Manim scene) ---")
    silent_video = render_full_semantic_video(script, output_dir=video_dir)
    if not silent_video:
        logger.error("Full semantic render failed. Aborting.")
        return

    # Manifest-aligned narration: the renderer wrote scene_timings.json
    # with each scene's actual video_start_seconds.  Use those to lay
    # out audio so per-scene boundaries match the silent video exactly,
    # eliminating the cross-scene drift that accumulates when action
    # animations overshoot their declared budget.  Falls back to the
    # legacy estimated-cumulative builder only if the manifest is missing.
    manifest_path = video_dir / "scene_timings.json"
    used_manifest = False
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            build_narration_track_from_manifest(
                scene_paths,
                scene_ids,
                manifest,
                output_path=combined_audio,
                scene_actions=scene_actions,
                category=script.category,
                scene_moods=scene_moods,
            )
            used_manifest = True
        except Exception as e:
            logger.warning(
                "Manifest-aligned audio build failed (%s); falling back to legacy builder",
                e,
            )

    if not used_manifest:
        build_semantic_narration_track(
            scene_paths,
            output_path=combined_audio,
            scene_actions=scene_actions,
            category=script.category,
            scene_moods=scene_moods,
            scene_pauses=scene_pauses,
        )

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

    # Track 4A: deterministic per-scene frame validation.
    # Track 4B: optional GPT-4o per-scene structured QA (gated by ENABLE_SCENE_QA).
    # Track 4C: optional auto-fix loop (gated by ENABLE_AUTO_FIX) that revises
    #          the failed scenes and re-renders once.
    deterministic_findings = []
    scene_qa_findings = []
    try:
        from frame_validator import format_report, validate_video_against_script
        scenes_for_validation = [s.model_dump(by_alias=True) for s in script.scenes]
        deterministic_findings = validate_video_against_script(
            final_path, scenes=scenes_for_validation,
        )
        report_text = format_report(deterministic_findings)
        for line in report_text.splitlines():
            logger.info("FrameValidator: %s", line)
        (run_dir / "frame_validation.json").write_text(
            json.dumps([r.to_dict() for r in deterministic_findings], indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("Frame validation skipped: %s", e)

    if os.getenv("ENABLE_SCENE_QA", "false").strip().lower() in ("1", "true", "yes", "on"):
        try:
            logger.info("--- Step 4b: Scene QA (GPT-4o per scene) ---")
            from vision_qa import run_scene_qa
            scene_qa_findings = run_scene_qa(
                final_path,
                scenes=[s.model_dump(by_alias=True) for s in script.scenes],
                report_path=str(run_dir / "scene_qa.json"),
            )
        except Exception as e:
            logger.warning("Scene QA skipped: %s", e)

    if os.getenv("ENABLE_AUTO_FIX", "false").strip().lower() in ("1", "true", "yes", "on"):
        try:
            from auto_fix import collect_fixes, revise_failed_scenes
            scenes_dicts = [s.model_dump(by_alias=True) for s in script.scenes]
            fixes = collect_fixes(deterministic_findings, scene_qa_findings, scenes_dicts)
            if fixes:
                logger.info("--- Step 4c: Auto-fix retry (%d failed scenes) ---", len(fixes))
                script_dict = script.model_dump(by_alias=True)
                revised, revised_ids = revise_failed_scenes(script_dict, fixes)
                if revised_ids:
                    from models_semantic import EnrichedVideoScript
                    script = EnrichedVideoScript.model_validate(revised)
                    (run_dir / "script.fixed.json").write_text(
                        json.dumps(revised, indent=2), encoding="utf-8",
                    )
                    logger.info("Auto-fix revised scenes: %s", revised_ids)
                    logger.info("--- Step 4c: Re-rendering with revised script ---")
                    silent_video = render_full_semantic_video(script, output_dir=video_dir)
                    if silent_video:
                        final_out2 = str(run_dir / "final_semantic.fixed.mp4")
                        final_path = mux_video_with_audio(
                            silent_video, combined_audio, final_out2,
                        )
                        logger.info("Auto-fix render -> %s", final_path)
                        # Re-validate after the retry render.
                        deterministic_findings = validate_video_against_script(
                            final_path,
                            scenes=[s.model_dump(by_alias=True) for s in script.scenes],
                        )
                        report_text = format_report(deterministic_findings)
                        for line in report_text.splitlines():
                            logger.info("FrameValidator(post-fix): %s", line)
        except Exception as e:
            logger.warning("Auto-fix skipped: %s", e)

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

    thumb_path: Path | None = None
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
            thumb_path = None

    # Export to Youtube_Upload/videos/ for the standalone uploader script.
    try:
        from config import ENABLE_YOUTUBE_UPLOAD_EXPORT
    except Exception:
        ENABLE_YOUTUBE_UPLOAD_EXPORT = True
    if ENABLE_YOUTUBE_UPLOAD_EXPORT:
        try:
            from youtube_upload_export import export_for_youtube_upload
            export_for_youtube_upload(
                final_video=final_path,
                script=script,
                topic=topic,
                thumbnail_path=str(thumb_path) if thumb_path else None,
            )
        except Exception as e:
            logger.warning("Youtube_Upload export skipped: %s", e)

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

    return script


# ---------------------------------------------------------------------------
# Shorts pipeline (vertical 9:16 for YouTube Shorts / IG Reels / TikTok)
# ---------------------------------------------------------------------------

def _tts_and_align_scenes(scenes, audio_dir):
    """TTS each scene then Whisper-align.  Mutates ``scene.audio_path``,
    ``scene.audio_duration``, and ``scene.whisper_words`` in place.

    Shared between long-form and shorts pipelines.
    """
    from narration_processor import scrub_closing_ctas
    from tts_generator import generate_speech, speed_for_pace

    scrub_closing_ctas(scenes)

    for scene in scenes:
        audio_path = str(audio_dir / f"{scene.scene_id}.mp3")
        mood = getattr(scene, "voice_mood", "") or None
        pace = getattr(scene, "narration_pace", "normal") or "normal"
        speed = speed_for_pace(pace)
        duration = generate_speech(scene.narration, audio_path, mood=mood, speed=speed)
        scene.audio_path = audio_path
        scene.audio_duration = duration
        logger.info(
            "Scene '%s' (mood=%s, pace=%s): audio %.2fs -> %s",
            scene.scene_id, mood or "default", pace, duration, audio_path,
        )

    try:
        from config import ENABLE_SUBTITLE_ALIGNMENT
    except Exception:
        ENABLE_SUBTITLE_ALIGNMENT = False
    if ENABLE_SUBTITLE_ALIGNMENT:
        try:
            from whisper_align import align_words
            for scene in scenes:
                if not scene.audio_path:
                    continue
                try:
                    timings = align_words(scene.audio_path)
                    if timings:
                        scene.whisper_words = [
                            {"start": w.start, "end": w.end, "text": w.text}
                            for w in timings
                        ]
                except Exception as e:
                    logger.debug(
                        "Whisper alignment for %s failed: %s", scene.scene_id, e,
                    )
        except Exception as e:
            logger.warning("Whisper alignment skipped: %s", e)


def run_shorts_pipeline(
    topic: str,
    category: str = "auto",
    long_form_script=None,
    run_dir: Path | None = None,
) -> str | None:
    """Generate a viral 50s vertical short for YT Shorts / IG Reels / TikTok.

    Pipeline:
      1. LLM distills topic into a 4-scene viral script (hook / tension /
         payoff / CTA).
      2. TTS each scene; Whisper-align for subtitle precision.
      3. Render silent 1080x1920 vertical via ``ShortsSemanticVideo``.
      4. Build manifest-aligned narration audio (same AV-sync fix as long-form).
      5. Mux audio + video into ``shorts/short.mp4``.
      6. Optionally write platform-named copies (youtube_short.mp4, etc.).

    Reuses every Track 1-6 capability: theme system, ambient particles,
    subtitle scheduler, manifest-driven audio, SFX/music selective mode.
    Only the LLM prompt and the camera frame differ.
    """
    from rendering_engine.engine import render_shorts_video
    from semantic_audio import (
        build_narration_track_from_manifest,
        build_semantic_narration_track,
        mux_video_with_audio,
    )
    from semantic_repair import repair_duplicate_ids
    from shorts_orchestrator import generate_shorts_script

    if run_dir is None:
        run_dir = _make_run_dir(topic, "shorts")
    shorts_dir = run_dir / "shorts"
    audio_dir = shorts_dir / "audio"
    video_dir = shorts_dir / "video"
    for d in (shorts_dir, audio_dir, video_dir):
        d.mkdir(parents=True, exist_ok=True)

    logger.info("=== Shorts pipeline: viral 4-scene vertical ===")
    logger.info("Run directory: %s", shorts_dir)

    if category == "auto":
        from prompts import auto_detect_category
        category = auto_detect_category(topic)
        logger.info("Auto-detected category: %s", category)

    logger.info("--- Shorts step 1: distilling viral script ---")
    script = generate_shorts_script(topic, long_form_script=long_form_script, category=category)
    script = repair_duplicate_ids(script)

    if not script.scenes:
        logger.error("Shorts script has no scenes — aborting")
        return None

    total_actions = sum(len(s.actions) for s in script.scenes)
    if total_actions < len(script.scenes):
        logger.warning(
            "Shorts script has only %d actions across %d scenes — "
            "the LLM may have emitted typeless action placeholders that got "
            "stripped.  Visuals will be sparse.", total_actions, len(script.scenes),
        )

    (shorts_dir / "script.json").write_text(
        json.dumps(script.model_dump(by_alias=True), indent=2),
        encoding="utf-8",
    )
    headline = (
        getattr(script, "video_title", "")
        or getattr(script, "topic", "")
        or topic
    )
    logger.info(
        "Shorts script: %d scenes | title='%s'",
        len(script.scenes), headline,
    )

    logger.info("--- Shorts step 2: TTS + Whisper alignment ---")
    _tts_and_align_scenes(script.scenes, audio_dir)

    logger.info("--- Shorts step 3: rendering vertical video ---")
    silent_video = render_shorts_video(script, output_dir=video_dir)
    if not silent_video:
        logger.error("Shorts render failed. Aborting shorts pipeline.")
        return None

    logger.info("--- Shorts step 4: building manifest-aligned audio ---")
    scene_paths = [s.audio_path for s in script.scenes if s.audio_path]
    scene_ids = [s.scene_id for s in script.scenes if s.audio_path]
    scene_actions = [
        [a.model_dump(by_alias=True) for a in s.actions]
        for s in script.scenes if s.audio_path
    ]
    scene_moods = [getattr(s, "music_mood", "") or "" for s in script.scenes if s.audio_path]
    scene_voice_moods = [getattr(s, "voice_mood", "") or "" for s in script.scenes if s.audio_path]
    scene_pauses = [getattr(s, "pause_after", 0.0) or 0.0 for s in script.scenes if s.audio_path]

    combined_audio = str(shorts_dir / "narration.mp3")
    manifest_path = video_dir / "scene_timings.json"
    used_manifest = False
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            # Shorts force continuous music (a 40-second video can't be
            # half-silent without feeling underbaked) and stamp every scene
            # start with a mood-keyed kickoff SFX.
            build_narration_track_from_manifest(
                scene_paths, scene_ids, manifest,
                output_path=combined_audio,
                scene_actions=scene_actions,
                category=script.category,
                scene_moods=scene_moods,
                voice_moods=scene_voice_moods,
                music_playback_mode="continuous",
                shorts_kickoff_sfx=True,
            )
            used_manifest = True
        except Exception as e:
            logger.warning(
                "Shorts manifest-aligned audio failed (%s); falling back", e,
            )
    if not used_manifest:
        build_semantic_narration_track(
            scene_paths, output_path=combined_audio,
            scene_actions=scene_actions, category=script.category,
            scene_moods=scene_moods, scene_pauses=scene_pauses,
        )

    logger.info("--- Shorts step 5: muxing ---")
    final_short = str(shorts_dir / "short.mp4")
    mux_video_with_audio(silent_video, combined_audio, final_short)
    logger.info("=== Shorts complete: %s ===", final_short)

    try:
        from config import SHORTS_EMIT_PLATFORM_COPIES
    except Exception:
        SHORTS_EMIT_PLATFORM_COPIES = True
    if SHORTS_EMIT_PLATFORM_COPIES:
        import shutil as _shutil
        for name in ("youtube_short.mp4", "instagram_reel.mp4", "tiktok.mp4"):
            try:
                _shutil.copy(final_short, str(shorts_dir / name))
            except Exception as e:
                logger.debug("Platform copy %s skipped: %s", name, e)
        logger.info("Platform-named copies saved in %s", shorts_dir)

    return final_short


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
    parser.add_argument(
        "--shorts",
        action="store_true",
        help=(
            "Also generate a 50s vertical 9:16 short (YouTube Shorts / IG Reels / "
            "TikTok) alongside the long-form video.  The short uses the long-form "
            "script as context so the CTA aligns."
        ),
    )
    parser.add_argument(
        "--shorts-only",
        action="store_true",
        help=(
            "Skip the long-form video and only generate the vertical short.  "
            "Useful for fast iteration on the shorts prompt or to back-fill "
            "shorts for topics that already have long-form videos."
        ),
    )
    args = parser.parse_args()

    logger.info("=== Starting video generation pipeline ===")
    logger.info(
        "Topic: %s | Engine: %s | Category: %s | Shorts: %s",
        args.topic, args.engine, args.category,
        "only" if args.shorts_only else ("yes" if args.shorts else "no"),
    )

    if args.shorts_only:
        run_shorts_pipeline(args.topic, category=args.category)
        return

    if args.engine == "legacy":
        run_legacy_pipeline(args.topic)
        return

    long_form = run_semantic_pipeline(args.topic, category=args.category)

    if args.shorts:
        # Short pipeline reuses the run dir of the long form when possible
        # so both videos for the same topic land under one output folder.
        long_run_dir = None
        try:
            from pathlib import Path as _Path
            if long_form and getattr(long_form, "scenes", None):
                first_audio = long_form.scenes[0].audio_path
                if first_audio:
                    long_run_dir = _Path(first_audio).resolve().parent.parent
        except Exception:
            long_run_dir = None
        run_shorts_pipeline(
            args.topic,
            category=args.category,
            long_form_script=long_form,
            run_dir=long_run_dir,
        )


if __name__ == "__main__":
    main()
