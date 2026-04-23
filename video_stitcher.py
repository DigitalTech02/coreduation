"""Final video assembly — audio attachment and clip concatenation."""

import logging
from pathlib import Path

from moviepy import (
    AudioFileClip,
    VideoFileClip,
    concatenate_videoclips,
)

from models import Scene

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")


def _ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _attach_audio(video_path: str, audio_path: str, output_path: str) -> str:
    """Combine a video clip with an audio track."""
    video = VideoFileClip(video_path)
    audio = AudioFileClip(audio_path)

    final = video.with_audio(audio)
    final.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        logger=None,
    )

    video.close()
    audio.close()
    final.close()
    return output_path


def stitch_video(
    scenes: list[Scene], output_path: str = "output/final.mp4"
) -> str:
    """Combine rendered scene clips with their audio tracks into a final video.

    Each scene must have video_path and audio_path populated.
    Returns the path to the final .mp4 file.
    """
    out_dir = Path(output_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    combined_clips: list[str] = []

    for i, scene in enumerate(scenes):
        if not scene.video_path or not scene.audio_path:
            logger.warning("Skipping scene '%s' — missing video or audio", scene.scene_id)
            continue

        scene_output = str(out_dir / f"scene_{i}_{scene.scene_id}_combined.mp4")
        logger.info("Attaching audio to scene '%s'", scene.scene_id)
        _attach_audio(scene.video_path, scene.audio_path, scene_output)
        combined_clips.append(scene_output)

    if not combined_clips:
        raise RuntimeError("No scenes to stitch — all scenes missing video or audio")

    logger.info("Concatenating %d scene clips into final video", len(combined_clips))

    clips = [VideoFileClip(p) for p in combined_clips]
    final = concatenate_videoclips(clips, method="compose")
    final.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        logger=None,
    )

    for clip in clips:
        clip.close()
    final.close()

    logger.info("Final video written to: %s", output_path)
    return output_path
