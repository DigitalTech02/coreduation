"""Bridge to the Remotion chrome project — render and composite intro/outro/lower-thirds.

The chrome layer is rendered as standalone MP4 clips by the ``chrome/``
Remotion project, then concatenated to the Manim video via FFmpeg.

This module is **optional**: if Node, npm, or the Remotion project aren't
available, it returns ``None`` and the pipeline falls back to the
Manim-rendered branding in :mod:`rendering_engine.branding`.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

CHROME_DIR = Path("chrome")


def _enabled() -> bool:
    return os.getenv("ENABLE_REMOTION_CHROME", "false").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _find_npx() -> str | None:
    """Resolve the npx executable (Windows often needs ``npx.cmd`` explicitly)."""
    for name in ("npx", "npx.cmd"):
        p = shutil.which(name)
        if p:
            return p
    node = shutil.which("node")
    if node and os.name == "nt":
        npm_dir = Path(node).resolve().parent
        for candidate in (npm_dir / "npx.cmd", npm_dir / "npx"):
            if candidate.is_file():
                return str(candidate)
    return None


def _has_node() -> bool:
    return _find_npx() is not None and shutil.which("node") is not None


def _has_chrome_project() -> bool:
    return (CHROME_DIR / "package.json").is_file()


def _accent_for(category: str) -> str:
    palette = {
        "networking":         "#3FB6FF",
        "data-structures":    "#B388FF",
        "programming":        "#86E27A",
        "cloud-architecture": "#4FC3F7",
        "system-design":      "#FFA94D",
        "databases":          "#FFD93D",
        "security":           "#FF6B6B",
        "business-analysis":  "#4DD0E1",
    }
    return palette.get((category or "").lower(), "#3FB6FF")


def render_chrome_clip(
    composition_id: str,
    out_path: str | Path,
    props: dict,
) -> str | None:
    """Render a single Remotion composition.  Returns the MP4 path or None."""
    if not _enabled():
        return None
    npx = _find_npx()
    if not npx:
        logger.warning(
            "Remotion chrome skipped: Node.js not found on PATH. "
            "Install from https://nodejs.org/ and ensure `node` / `npx` work in a new terminal, "
            "then run: cd chrome && npm install",
        )
        return None
    if not _has_chrome_project():
        logger.debug("No chrome/ project found — skipping Remotion chrome")
        return None

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        npx,
        "remotion",
        "render",
        "src/index.ts",
        composition_id,
        str(out_path.resolve()),
        "--props=" + json.dumps(props),
    ]
    logger.info("Remotion render: %s", composition_id)
    try:
        result = subprocess.run(
            cmd, cwd=CHROME_DIR, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=600,
            shell=False,
        )
    except FileNotFoundError as e:
        logger.warning(
            "Remotion chrome skipped: could not execute %r (%s). On Windows, install Node LTS and reopen the terminal.",
            npx, e,
        )
        return None
    if result.returncode != 0:
        err = (result.stderr or "") + ("\n" + (result.stdout or "") if result.stdout else "")
        # esbuild/Remotion often print the real error at the *start* of stderr
        if len(err) > 4000:
            err_snip = f"{err[:2500]}\n\n... [middle truncated] ...\n\n{err[-1200:]}"
        else:
            err_snip = err
        logger.warning("Remotion render failed for %s:\n%s", composition_id, err_snip)
        return None
    return str(out_path)


def render_intro(channel_name: str, tagline: str, category: str, out_dir: Path) -> str | None:
    return render_chrome_clip(
        "Intro",
        out_dir / "remotion_intro.mp4",
        {"channelName": channel_name, "tagline": tagline, "accent": _accent_for(category)},
    )


def render_outro(channel_name: str, message: str, category: str, out_dir: Path) -> str | None:
    return render_chrome_clip(
        "Outro",
        out_dir / "remotion_outro.mp4",
        {"channelName": channel_name, "message": message, "accent": _accent_for(category)},
    )


def render_lower_third(
    title: str, subtitle: str, category: str, out_dir: Path, idx: int = 0,
) -> str | None:
    return render_chrome_clip(
        "LowerThird",
        out_dir / f"remotion_lower_third_{idx:03d}.mp4",
        {"title": title, "subtitle": subtitle, "accent": _accent_for(category)},
    )


def concat_with_chrome(
    main_video: str,
    intro: str | None,
    outro: str | None,
    output_path: str,
) -> str:
    """Concatenate ``intro`` + ``main_video`` + ``outro`` into one MP4.

    Skips any segment that is None.  Falls back to ``main_video`` unchanged
    when neither intro nor outro is present.
    """
    parts = [p for p in (intro, main_video, outro) if p]
    if len(parts) <= 1:
        return main_video

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    list_file = out.with_suffix(".concat.txt")
    list_file.write_text(
        "\n".join(f"file '{Path(p).resolve().as_posix()}'" for p in parts),
        encoding="utf-8",
    )

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy", str(out),
    ]
    logger.info("Chrome concat: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=300)
    list_file.unlink(missing_ok=True)
    if result.returncode != 0:
        logger.warning("Chrome concat failed (continuing without):\n%s",
                       (result.stderr or "")[-1500:])
        return main_video
    return str(out)
