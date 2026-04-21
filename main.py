"""AI Video Generation Pipeline — entry point.

Orchestrates the full pipeline: script generation -> TTS -> animation -> stitching.
"""

import logging
import sys
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

AUDIO_DIR = Path("output/audio")
VIDEO_DIR = Path("output/video")


def main() -> None:
    topic = "Binary Search Algorithm"

    logger.info("=== Starting video generation pipeline for: %s ===", topic)

    # Step 1: Generate structured script via LLM
    from llm_orchestrator import generate_video_script

    logger.info("--- Step 1: Generating script ---")
    script = generate_video_script(topic)
    logger.info("Script generated with %d scenes", len(script.scenes))

    # Step 2: Generate TTS audio for each scene
    from tts_generator import generate_speech

    logger.info("--- Step 2: Generating TTS audio ---")
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    for scene in script.scenes:
        audio_path = str(AUDIO_DIR / f"{scene.scene_id}.mp3")
        duration = generate_speech(scene.narration, audio_path)
        scene.audio_path = audio_path
        scene.audio_duration = duration
        logger.info("Scene '%s': audio %.2fs -> %s", scene.scene_id, duration, audio_path)

    # Step 3: Render Manim animations for each scene
    from animation_renderer import render_scene

    logger.info("--- Step 3: Rendering animations ---")
    for scene in script.scenes:
        video_path = render_scene(
            manim_code=scene.manim_code,
            scene_id=scene.scene_id,
            target_duration=scene.audio_duration,
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

    # Step 4: Stitch with title card + crossfade transitions
    from video_stitcher import stitch_video

    logger.info("--- Step 4: Stitching final video with transitions ---")
    title_narration = (
        f"Welcome to this deep dive into {topic}. "
        f"In the next few minutes, we'll build a clear, visual understanding "
        f"of how it works, why it matters, and how to implement it in code."
    )
    final_path = stitch_video(
        renderable,
        output_path="output/final.mp4",
        title_topic=topic,
        title_narration=title_narration,
    )

    logger.info("=== Pipeline complete! Final video: %s ===", final_path)


if __name__ == "__main__":
    main()
