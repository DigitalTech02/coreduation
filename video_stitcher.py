"""Final video assembly — audio attachment, crossfade transitions, and concatenation."""

import logging
import os
import subprocess
import tempfile
from pathlib import Path

from moviepy import (
    AudioFileClip,
    CompositeVideoClip,
    VideoFileClip,
    concatenate_videoclips,
)
from moviepy.video.fx import CrossFadeIn, CrossFadeOut

from models import Scene

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")
CROSSFADE_DURATION = float(os.getenv("CROSSFADE_DURATION", "0.8"))


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


def generate_title_card(
    topic: str, narration: str, duration: float = 5.0
) -> tuple[str, str]:
    """Generate a title card video + TTS audio using Manim and the TTS provider.

    Returns (video_path, audio_path).
    """
    from animation_renderer import render_scene
    from tts_generator import generate_speech

    _ensure_output_dir()

    title_code = f'''from manim import *

class TitleCard(Scene):
    def construct(self):
        self.camera.background_color = "#1a1a2e"

        title = Text("{topic}", font_size=52, color=WHITE, weight=BOLD)
        subtitle = Text("A Visual Explanation", font_size=28, color=GRAY_B)
        divider = Line(LEFT * 3, RIGHT * 3, color=BLUE, stroke_width=2)

        group = VGroup(title, divider, subtitle).arrange(DOWN, buff=0.5)
        group.move_to(ORIGIN)

        self.play(FadeIn(title, shift=UP * 0.5), run_time=1.0)
        self.wait(0.3)
        self.play(Create(divider), run_time=0.6)
        self.wait(0.3)
        self.play(FadeIn(subtitle, shift=UP * 0.3), run_time=0.8)
        self.wait(0.5)
        self.play(
            title.animate.scale(1.05).set_color(BLUE_B),
            run_time=0.8,
        )
        self.wait(0.5)
        self.play(title.animate.scale(1 / 1.05).set_color(WHITE), run_time=0.6)
        self.wait(1.0)
'''

    audio_path = str(OUTPUT_DIR / "audio" / "title-card.mp3")
    Path(audio_path).parent.mkdir(parents=True, exist_ok=True)
    audio_duration = generate_speech(narration, audio_path)

    video_path = render_scene(
        manim_code=title_code,
        scene_id="title-card",
        target_duration=audio_duration,
    )

    return video_path, audio_path


def stitch_video(
    scenes: list[Scene],
    output_path: str = "output/final.mp4",
    title_topic: str | None = None,
    title_narration: str | None = None,
) -> str:
    """Combine rendered scene clips with their audio into a final video with crossfades.

    Optionally prepends a title card if title_topic is provided.
    """
    _ensure_output_dir()

    combined_clips: list[str] = []

    if title_topic and title_narration:
        logger.info("Generating title card for: %s", title_topic)
        title_video, title_audio = generate_title_card(title_topic, title_narration)
        if title_video:
            title_output = str(OUTPUT_DIR / "title_card_combined.mp4")
            _attach_audio(title_video, title_audio, title_output)
            combined_clips.append(title_output)

    for i, scene in enumerate(scenes):
        if not scene.video_path or not scene.audio_path:
            logger.warning("Skipping scene '%s' — missing video or audio", scene.scene_id)
            continue

        scene_output = str(OUTPUT_DIR / f"scene_{i}_{scene.scene_id}_combined.mp4")
        logger.info("Attaching audio to scene '%s'", scene.scene_id)
        _attach_audio(scene.video_path, scene.audio_path, scene_output)
        combined_clips.append(scene_output)

    if not combined_clips:
        raise RuntimeError("No scenes to stitch — all scenes missing video or audio")

    logger.info(
        "Concatenating %d clips with %.1fs crossfade transitions",
        len(combined_clips),
        CROSSFADE_DURATION,
    )

    clips = [VideoFileClip(p) for p in combined_clips]
    fade = CROSSFADE_DURATION

    if len(clips) == 1:
        final = clips[0]
    else:
        transitioned = [clips[0].with_effects([CrossFadeOut(fade)])]
        for clip in clips[1:-1]:
            transitioned.append(
                clip.with_effects([CrossFadeIn(fade), CrossFadeOut(fade)])
            )
        transitioned.append(clips[-1].with_effects([CrossFadeIn(fade)]))

        final = concatenate_videoclips(
            transitioned, padding=-fade, method="compose"
        )

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
