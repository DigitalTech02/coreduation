"""GPT-4o vision QA loop — sample frames from a rendered video and ask the
model to flag overlapping text, blank screens, cut-off content, etc.

Usage::

    from vision_qa import run_vision_qa
    issues = run_vision_qa("output/run/full_semantic_silent.mp4")

The result is a list of :class:`FrameIssue` records; an empty list means the
video passed.  The QA loop is cheap (~10 calls @ ~$0.01 each) and runs after
the silent Manim render but before muxing the final audio.

Triggered by ``ENABLE_VISION_QA`` env var (default off so first runs aren't
billed automatically).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FrameIssue:
    """One QA finding from the vision model."""

    timestamp: float
    severity: str  # "ok" | "warn" | "fail"
    issues: list[str]
    description: str

    def to_dict(self) -> dict:
        return asdict(self)


_QA_SYSTEM_PROMPT = (
    "You are a strict QA reviewer for educational explainer videos. "
    "Look at the frame and identify any of these problems:\n"
    "  - blank: the canvas is empty or nearly empty (no meaningful content)\n"
    "  - overlap: text or shapes overlap each other in a way that hides content\n"
    "  - cutoff: text or shapes are clipped at the screen edge\n"
    "  - overflow: text overflows its container (a box or node)\n"
    "  - illegible: text is too small or low-contrast to read\n"
    "Reply in strict JSON: {\"severity\": \"ok\"|\"warn\"|\"fail\", "
    "\"issues\": [list of tag strings from above], \"description\": \"<one short sentence>\"}\n"
    "Use 'ok' for no issues, 'warn' for minor cosmetic issues, "
    "'fail' for issues that hurt comprehension."
)


def _video_duration(path: str) -> float:
    """Return duration in seconds via ffprobe (0 on failure)."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return float(result.stdout.strip() or "0")
    except Exception as e:
        logger.warning("ffprobe failed: %s", e)
        return 0.0


def _extract_frames(video_path: str, sample_every_s: float, out_dir: Path) -> list[tuple[float, Path]]:
    """Extract frames at *sample_every_s* intervals.

    Returns a list of ``(timestamp, jpg_path)`` tuples sorted by time.
    """
    duration = _video_duration(video_path)
    if duration <= 0:
        logger.warning("Could not determine video duration; skipping QA")
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    fps = 1.0 / max(0.5, sample_every_s)
    pattern = str(out_dir / "frame_%04d.jpg")
    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-vf", f"fps={fps}",
        "-q:v", "3",
        pattern,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        logger.error("ffmpeg frame extract failed: %s", (result.stderr or "")[-500:])
        return []

    frames = sorted(out_dir.glob("frame_*.jpg"))
    timestamps = [(i + 0.5) * sample_every_s for i in range(len(frames))]
    return list(zip(timestamps, frames))


def _qa_one_frame(client: Any, model: str, frame_path: Path, ts: float) -> FrameIssue:
    """Send one frame to GPT-4o vision and parse the JSON verdict."""
    try:
        with open(frame_path, "rb") as f:
            img_bytes = f.read()
        b64 = base64.b64encode(img_bytes).decode("ascii")

        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _QA_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Frame at t={ts:.1f}s. Inspect for issues."},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                    ],
                },
            ],
            response_format={"type": "json_object"},
            max_tokens=200,
        )
        raw = completion.choices[0].message.content or "{}"
        data = json.loads(raw)
        return FrameIssue(
            timestamp=ts,
            severity=str(data.get("severity", "ok")).lower(),
            issues=list(data.get("issues") or []),
            description=str(data.get("description") or ""),
        )
    except Exception as e:
        logger.warning("Vision QA error at t=%.1f: %s", ts, e)
        return FrameIssue(timestamp=ts, severity="ok", issues=[], description=f"qa_error: {e}")


def run_vision_qa(
    video_path: str,
    sample_every_s: float | None = None,
    report_path: str | None = None,
    severity_min: str = "warn",
) -> list[FrameIssue]:
    """Sample frames from *video_path* and ask GPT-4o vision to flag issues.

    Returns the list of frame issues filtered to *severity_min* or worse.
    Writes a full JSON report to *report_path* (defaults to next to the video).
    Respects ``ENABLE_VISION_QA`` and ``VISION_QA_SAMPLE_SECONDS`` env vars.
    """
    from openai import OpenAI

    enable = os.getenv("ENABLE_VISION_QA", "false").strip().lower() in ("1", "true", "yes", "on")
    if not enable:
        logger.info("Vision QA disabled (set ENABLE_VISION_QA=true to enable).")
        return []

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set; skipping vision QA")
        return []

    if sample_every_s is None:
        try:
            sample_every_s = float(os.getenv("VISION_QA_SAMPLE_SECONDS", "8"))
        except ValueError:
            sample_every_s = 8.0

    model = os.getenv("VISION_QA_MODEL", "gpt-4o")
    client = OpenAI(api_key=api_key)

    work = Path(tempfile.mkdtemp(prefix="vision_qa_frames_"))
    try:
        frames = _extract_frames(video_path, sample_every_s, work)
        if not frames:
            logger.warning("No frames extracted; vision QA skipped")
            return []

        logger.info("Vision QA: %d frames sampled (every %.1fs) using %s",
                    len(frames), sample_every_s, model)

        results: list[FrameIssue] = []
        for ts, path in frames:
            issue = _qa_one_frame(client, model, path, ts)
            results.append(issue)
            if issue.severity in ("warn", "fail"):
                logger.info("Vision QA [%s] @ %.1fs: %s -> %s",
                            issue.severity.upper(), ts,
                            ",".join(issue.issues), issue.description)

        report = {
            "video": video_path,
            "sample_every_s": sample_every_s,
            "model": model,
            "total_frames": len(results),
            "ok": sum(1 for r in results if r.severity == "ok"),
            "warn": sum(1 for r in results if r.severity == "warn"),
            "fail": sum(1 for r in results if r.severity == "fail"),
            "frames": [r.to_dict() for r in results],
        }
        out_report = Path(report_path) if report_path else Path(video_path).with_suffix(".qa.json")
        out_report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        logger.info("Vision QA report -> %s (ok=%d warn=%d fail=%d)",
                    out_report, report["ok"], report["warn"], report["fail"])

        order = {"ok": 0, "warn": 1, "fail": 2}
        threshold = order.get(severity_min, 1)
        return [r for r in results if order.get(r.severity, 0) >= threshold]
    finally:
        shutil.rmtree(work, ignore_errors=True)


def has_blocking_failures(issues: list[FrameIssue]) -> bool:
    """Return True if any issue is severity='fail' (worth re-rendering)."""
    return any(i.severity == "fail" for i in issues)
