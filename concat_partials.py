"""
Concatenate Manim's per-animation partial mp4s into a single silent video,
bypassing Manim's broken combine_files step (PyAV/Python 3.12 bug).

Manim renders each animation as a separate mp4 in:
    <work_dir>/media/videos/full_video_runner/720p30/partial_movie_files/FullSemanticVideo/

After it finishes rendering all of them it tries to concat them via PyAV,
and on certain WSL/Python combos that step explodes looking for a
partial_movie_file_list.txt that was never written.

This script:
  1. Globs all partial mp4s from the most recent /tmp/semantic_render_*
  2. Sorts them numerically (uncached_00000.mp4, uncached_00001.mp4, ...)
  3. Writes a concat list and runs ffmpeg concat
  4. Moves the resulting mp4 + scene_timings.json into the run folder

Usage:
    python concat_partials.py output/20260507_002239_semantic_tcp-three-way-handshake
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("concat")


def find_latest_work_dir() -> Path | None:
    candidates = sorted(
        Path("/tmp").glob("semantic_render_*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def main(run_dir_arg: str) -> int:
    run_dir = Path(run_dir_arg).resolve()
    if not run_dir.is_dir():
        logger.error("Run dir not found: %s", run_dir)
        return 1

    video_dir = run_dir / "video"
    video_dir.mkdir(exist_ok=True)

    work_dir = find_latest_work_dir()
    if not work_dir:
        logger.error("No /tmp/semantic_render_* directory found.")
        return 1
    logger.info("Using work dir: %s", work_dir)

    partial_dir = (
        work_dir
        / "media" / "videos" / "full_video_runner" / "720p30"
        / "partial_movie_files" / "FullSemanticVideo"
    )
    if not partial_dir.is_dir():
        logger.error("Partial movie dir not found: %s", partial_dir)
        return 1

    # Glob ALL .mp4 files (uncached + cached/hash-named like intro/title/
    # outro cards) ordered by mtime.  Globbing only `uncached_*` drops the
    # cached intro/title/outro partials and the resulting video is several
    # seconds shorter than the manifest claims, which makes Track 6 audio
    # placement land on the wrong frames.
    partials = sorted(
        (p for p in partial_dir.glob("*.mp4") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
    )
    if not partials:
        logger.error("No partial movie files in %s", partial_dir)
        return 1
    logger.info("Found %d partial movie files", len(partials))

    # Manifest first — fail loudly if it isn't there.
    manifest_src = work_dir / "scene_timings.json"
    if not manifest_src.is_file():
        logger.error("scene_timings.json missing at %s", manifest_src)
        return 1
    # copyfile (not copy) — copy() tries to chmod which fails on /mnt/c
    shutil.copyfile(str(manifest_src), str(video_dir / "scene_timings.json"))
    logger.info("Copied manifest -> %s", video_dir / "scene_timings.json")

    # Build concat list and run ffmpeg.
    with tempfile.NamedTemporaryFile(
        "w", suffix=".txt", delete=False, encoding="utf-8"
    ) as listf:
        for p in partials:
            # Single-quote the path; escape any embedded single quote.
            safe = str(p).replace("'", "'\\''")
            listf.write(f"file '{safe}'\n")
        list_path = listf.name

    silent_out = video_dir / "full_semantic_silent.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_path,
        "-c", "copy",
        "-movflags", "+faststart",
        str(silent_out),
    ]
    logger.info("Running: %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    finally:
        Path(list_path).unlink(missing_ok=True)

    if result.returncode != 0:
        logger.error("ffmpeg concat failed:\n%s", result.stderr[-4000:])
        return 1

    logger.info("Silent video written: %s (%d bytes)",
                silent_out, silent_out.stat().st_size)
    logger.info("Now run: python salvage_run.py %s", run_dir)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python concat_partials.py <run-dir>")
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
