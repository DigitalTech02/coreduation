"""Export final video + metadata + thumbnail to ``Youtube_Upload/videos/``.

The standalone ``Youtube_Upload/youtubeupload4.py`` uploader scans that
folder for ``stitched_video_set_<N>.mp4`` + ``stitched_video_set_<N>.txt``
+ ``thumbnail_<N>.png`` triples and uploads each to YouTube.  This module
copies the pipeline's output into that convention so the existing manual
uploader keeps working without changes.

The set number auto-increments based on what's already in the folder.
Gated by ``ENABLE_YOUTUBE_UPLOAD_EXPORT`` in :mod:`config`.
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SET_NUMBER_RE = re.compile(r"stitched_video_set_(\d+)\.(?:mp4|txt)$", re.IGNORECASE)


def _next_set_number(target_dir: Path) -> int:
    """Find the next free ``stitched_video_set_<N>`` index in *target_dir*."""
    if not target_dir.is_dir():
        return 1
    used: set[int] = set()
    for child in target_dir.iterdir():
        m = _SET_NUMBER_RE.search(child.name)
        if m:
            try:
                used.add(int(m.group(1)))
            except ValueError:
                pass
    if not used:
        return 1
    return max(used) + 1


def _build_metadata(script: Any, topic: str, idea: str = "") -> str:
    """Render the metadata text file in the format ``youtubeupload4.py`` expects.

    The parser there only needs:
      - a line starting with ``Title:`` followed by a quoted string
      - a line starting with ``Description:`` followed by content up to ``---``
    The leading ``Idea:`` line is preserved for human readability.
    """
    title = (
        getattr(script, "suggested_youtube_title", "")
        or getattr(script, "video_title", "")
        or topic
    ).strip()

    description = (
        getattr(script, "suggested_youtube_description", "") or ""
    ).strip()
    if not description:
        # Fallback: a short auto-description built from the topic + hook.
        hook = (getattr(script, "video_hook", "") or "").strip()
        description = (
            f"{topic}\n\n{hook}".strip()
            if hook else topic
        )

    tags = getattr(script, "suggested_youtube_tags", []) or []
    if tags:
        tag_line = " ".join(f"#{t.strip().lstrip('#').replace(' ', '')}" for t in tags if t)
        if tag_line:
            description = f"{description}\n\n{tag_line}"

    idea_line = (idea or topic).strip().splitlines()[0]

    parts = [
        f"Idea: {idea_line}",
        f'Title: "{title}"',
        "Description:",
        description,
        "---",
    ]
    return "\n".join(parts) + "\n"


def export_for_youtube_upload(
    final_video: str | Path,
    script: Any,
    topic: str,
    *,
    thumbnail_path: str | Path | None = None,
    target_dir: str | Path = "Youtube_Upload/videos",
) -> Path | None:
    """Copy the final video, metadata, and thumbnail into ``target_dir``.

    Returns the path to the copied .mp4 on success, ``None`` if disabled
    or on failure.  Failures are logged but never raise — this is an
    optional convenience export, not a critical pipeline step.
    """
    try:
        from config import ENABLE_YOUTUBE_UPLOAD_EXPORT
    except Exception:
        ENABLE_YOUTUBE_UPLOAD_EXPORT = True
    if not ENABLE_YOUTUBE_UPLOAD_EXPORT:
        return None

    final_video = Path(final_video)
    if not final_video.is_file():
        logger.warning("YouTube export: final video not found at %s", final_video)
        return None

    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    n = _next_set_number(target_dir)

    video_dest = target_dir / f"stitched_video_set_{n}.mp4"
    meta_dest = target_dir / f"stitched_video_set_{n}.txt"
    thumb_dest = target_dir / f"thumbnail_{n}.png"

    try:
        shutil.copy2(final_video, video_dest)
    except Exception as e:
        logger.warning("YouTube export: failed to copy video: %s", e)
        return None

    try:
        meta_dest.write_text(
            _build_metadata(script, topic), encoding="utf-8",
        )
    except Exception as e:
        logger.warning("YouTube export: failed to write metadata: %s", e)

    if thumbnail_path:
        thumbnail_path = Path(thumbnail_path)
        if thumbnail_path.is_file():
            try:
                # Convert to PNG if source is .jpg — the uploader expects .png.
                if thumbnail_path.suffix.lower() in (".jpg", ".jpeg"):
                    try:
                        from PIL import Image
                        img = Image.open(thumbnail_path)
                        img.save(thumb_dest, format="PNG")
                    except Exception as e:
                        logger.debug("PIL conversion failed (%s); copying raw", e)
                        shutil.copy2(thumbnail_path, thumb_dest.with_suffix(thumbnail_path.suffix))
                else:
                    shutil.copy2(thumbnail_path, thumb_dest)
            except Exception as e:
                logger.warning("YouTube export: failed to copy thumbnail: %s", e)

    logger.info(
        "YouTube export -> %s (set #%d, metadata + thumbnail in %s)",
        video_dest, n, target_dir,
    )
    return video_dest
