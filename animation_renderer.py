"""Manim animation rendering from LLM-generated scene code.

Writes each scene to a temp .py file, renders it via subprocess,
and enforces target duration by padding or trimming.
"""

import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path

from moviepy import VideoFileClip, concatenate_videoclips

from error_healer import heal_manim_code

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output/video")
MANIM_QUALITY = os.getenv("MANIM_QUALITY", "m")


def _ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _extract_error_message(raw_output: str) -> str:
    """Strip Rich box-drawing chars from Manim's traceback and extract the useful error."""
    lines = raw_output.splitlines()
    cleaned = []
    for line in lines:
        stripped = re.sub(r"[│┃|+\-─┬┴┤├╭╮╰╯]+", "", line).strip()
        if stripped:
            cleaned.append(stripped)
    return "\n".join(cleaned[-40:])


def _find_rendered_file(media_dir: Path, scene_class_name: str) -> Path | None:
    """Locate the rendered .mp4 in Manim's media output tree.

    Manim outputs to: media/videos/{ScriptName}/{quality}/{ClassName}.mp4
    """
    for mp4 in media_dir.rglob(f"{scene_class_name}.mp4"):
        if "partial_movie_files" not in str(mp4):
            return mp4
    return None


def _render_manim_code(
    code: str, scene_class_name: str, work_dir: Path
) -> tuple[str | None, str | None]:
    """Write code to a temp file and invoke Manim. Returns (video_path, error_msg)."""
    script_path = work_dir / f"{scene_class_name}.py"
    script_path.write_text(code, encoding="utf-8")

    media_dir = work_dir / "media"

    cmd = [
        "python", "-m", "manim", "render",
        "-q", MANIM_QUALITY,
        "--media_dir", str(media_dir),
        "--disable_caching",
        str(script_path),
        scene_class_name,
    ]

    logger.info("Running Manim: %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:
        error_msg = (result.stderr or "") + (result.stdout or "")
        clean_error = _extract_error_message(error_msg)
        logger.error("Manim render failed for %s:\n%s", scene_class_name, clean_error[:1000])
        return None, clean_error

    rendered = _find_rendered_file(media_dir, scene_class_name)
    if rendered is None:
        return None, "Render succeeded but output .mp4 not found in media directory"

    return str(rendered), None


def _scene_id_to_class_name(scene_id: str) -> str:
    """Convert scene_id slug to PascalCase class name (e.g. 'step-1' -> 'Step1')."""
    return "".join(
        part.capitalize() for part in scene_id.replace("-", " ").replace("_", " ").split()
    )


def _enforce_duration(video_path: str, target_duration: float, output_path: str) -> str:
    """Pad or trim a video clip to match the target audio duration."""
    clip = VideoFileClip(video_path)
    clip_duration = clip.duration

    if clip_duration >= target_duration:
        final = clip.subclipped(0, target_duration)
    else:
        padding_needed = target_duration - clip_duration
        freeze = clip.subclipped(clip_duration - 0.1, clip_duration).with_duration(padding_needed)
        final = concatenate_videoclips([clip, freeze])

    final.write_videofile(
        output_path,
        codec="libx264",
        audio=False,
        logger=None,
    )
    clip.close()
    final.close()
    return output_path


def render_scene(
    manim_code: str,
    scene_id: str,
    target_duration: float | None = None,
    max_heal_retries: int = 3,
    output_dir: Path | str | None = None,
) -> str | None:
    """Render a Manim scene and return the path to the output video file.

    If rendering fails, attempts to heal the code via LLM up to max_heal_retries times.
    If target_duration is provided, pads/trims the clip to match.
    Returns None if all attempts fail (pipeline can skip the scene).
    """
    dest_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    class_name = _scene_id_to_class_name(scene_id)
    current_code = manim_code

    work_dir = Path(tempfile.mkdtemp(prefix=f"manim_{scene_id}_"))

    for attempt in range(1, max_heal_retries + 2):
        video_path, error = _render_manim_code(current_code, class_name, work_dir)

        if video_path is not None:
            logger.info("Scene '%s' rendered successfully: %s", scene_id, video_path)

            if target_duration is not None:
                output_path = str(dest_dir / f"{scene_id}.mp4")
                video_path = _enforce_duration(video_path, target_duration, output_path)
                logger.info("Scene '%s' duration enforced to %.2fs", scene_id, target_duration)

            return video_path

        if attempt > max_heal_retries:
            break

        logger.warning("Scene '%s' failed (attempt %d), sending to healer", scene_id, attempt)
        current_code = heal_manim_code(current_code, error or "Unknown error", max_retries=1)

    logger.error("Failed to render scene '%s' after %d heal attempts — skipping", scene_id, max_heal_retries)
    return None
