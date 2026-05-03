"""Deterministic per-scene frame validator (Track 4A).

Sample one mid-scene frame from a rendered MP4 and run cheap pixel checks
to flag obvious visual failures BEFORE invoking expensive LLM vision QA.

Checks (each emits a structured ``FrameFinding``):
  - blank: scene is mostly background — content failed to render
  - edge_clip: non-background pixels touch the canvas border
  - low_contrast: foreground pixels are too close in brightness to background

Returns a list of ``SceneValidation`` records, one per scene. Severity is
"ok" / "warn" / "fail". The pipeline can choose to fail the build, log
warnings, or hand the structured errors to an auto-fix loop (Track 4C).

No LLM calls. Uses ffmpeg for frame extraction + Pillow/numpy for analysis.
Runs in seconds for a 17-scene video.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# The dark theme has a gradient background that varies in shade — matching
# a single BG color produces too many false positives. Instead, we detect
# CONTENT pixels by luminance: text and node fills are 80-255 brightness
# while the background gradient stays under ~50.
_CONTENT_LUMA_MIN = 60          # luminance threshold for "this is content"
_BRIGHT_LUMA_MIN = 140          # luminance threshold for "this is text or highlight"

# Edge band width — pixels within this many of any canvas edge count as "border".
_EDGE_BAND_PX = 6

# Thresholds (calibrated to 720p, dark theme). Tunable.
_BLANK_CONTENT_RATIO_MAX = 0.008     # under 0.8% content pixels → blank scene
_EDGE_CLIP_RATIO_MIN = 0.04          # over 4% content in border bands → clipping
_BRIGHT_RATIO_MIN_FOR_READABLE = 0.002  # at least 0.2% bright pixels → has readable content


@dataclass
class FrameFinding:
    type: str  # "blank" | "edge_clip" | "low_contrast"
    severity: str  # "warn" | "fail"
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SceneValidation:
    scene_id: str
    timestamp: float
    severity: str  # "ok" | "warn" | "fail"
    findings: list[FrameFinding] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scene_id": self.scene_id,
            "timestamp": self.timestamp,
            "severity": self.severity,
            "findings": [f.to_dict() for f in self.findings],
        }


def _check_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _extract_frame(video_path: str, timestamp: float, out_path: str) -> bool:
    """Extract a single PNG frame at ``timestamp`` seconds. Returns success."""
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{timestamp:.2f}", "-i", video_path,
             "-frames:v", "1", out_path],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return Path(out_path).exists()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _luminance(arr: np.ndarray) -> np.ndarray:
    """Per-pixel luminance using ITU-R BT.601 weights (R*0.299 + G*0.587 + B*0.114)."""
    a = arr.astype(np.float32)
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


def _border_mask(shape: tuple[int, int]) -> np.ndarray:
    """Boolean mask: True for pixels within EDGE_BAND_PX of any canvas edge."""
    h, w = shape
    band = _EDGE_BAND_PX
    mask = np.zeros((h, w), dtype=bool)
    mask[:band, :] = True
    mask[-band:, :] = True
    mask[:, :band] = True
    mask[:, -band:] = True
    return mask


def _check_blank(content_mask: np.ndarray) -> FrameFinding | None:
    ratio = content_mask.mean()
    if ratio < _BLANK_CONTENT_RATIO_MAX:
        return FrameFinding(
            type="blank",
            severity="fail",
            detail=(
                f"only {ratio:.2%} content pixels (threshold "
                f"{_BLANK_CONTENT_RATIO_MAX:.2%}) — scene rendered nothing meaningful"
            ),
        )
    return None


def _check_edge_clip(content_mask: np.ndarray) -> FrameFinding | None:
    border = _border_mask(content_mask.shape)
    border_content = content_mask & border
    ratio = border_content.sum() / max(1, border.sum())
    if ratio > _EDGE_CLIP_RATIO_MIN:
        return FrameFinding(
            type="edge_clip",
            severity="warn",
            detail=(
                f"{ratio:.1%} of border pixels are content (threshold "
                f"{_EDGE_CLIP_RATIO_MIN:.1%}) — content likely clipped at edges"
            ),
        )
    return None


def _check_no_readable_text(luma: np.ndarray) -> FrameFinding | None:
    """If almost no pixels exceed BRIGHT_LUMA_MIN, the scene has no readable text."""
    bright_ratio = (luma >= _BRIGHT_LUMA_MIN).mean()
    if bright_ratio < _BRIGHT_RATIO_MIN_FOR_READABLE:
        return FrameFinding(
            type="no_readable_text",
            severity="warn",
            detail=(
                f"only {bright_ratio:.2%} bright pixels (threshold "
                f"{_BRIGHT_RATIO_MIN_FOR_READABLE:.2%}) — no readable text or highlights"
            ),
        )
    return None


def _validate_frame(arr: np.ndarray) -> list[FrameFinding]:
    """Run all checks on a single frame array. Returns findings (may be empty)."""
    luma = _luminance(arr)
    content_mask = luma >= _CONTENT_LUMA_MIN
    findings: list[FrameFinding] = []
    for check in (
        _check_blank(content_mask),
        _check_edge_clip(content_mask),
        _check_no_readable_text(luma),
    ):
        if check is not None:
            findings.append(check)
    return findings


def _scene_sample_times(
    scene_starts: list[float], i: int, video_duration: float,
) -> list[float]:
    """Pick three sample timestamps inside scene *i* — early, mid, late.

    Slide-style scenes have sequential title → bullet reveals. Chapter
    transition cards add fixed overhead between sections. Single-frame
    sampling produces false positives at either extreme. We sample three
    frames and require ALL of them to fail before flagging a scene.
    """
    start = scene_starts[i]
    end = scene_starts[i + 1] if i + 1 < len(scene_starts) else video_duration
    span = end - start
    if span < 1.5:
        return [start + span * 0.5]
    return [
        start + max(1.0, span * 0.30),
        start + max(1.5, span * 0.55),
        start + max(2.0, span * 0.80),
    ]


def _compute_scene_starts(scenes: list[dict], intro_offset: float = 2.5) -> list[float]:
    """Compute approximate start times based on audio_duration / pause_after.

    Mirrors the arithmetic in semantic_audio.build_semantic_narration_track:
    each scene gets its audio duration + SCENE_GAP_SECONDS + pause_after.
    """
    SCENE_GAP_SECONDS = 0.15
    starts: list[float] = []
    cursor = intro_offset
    for s in scenes:
        starts.append(cursor)
        dur = float(s.get("audio_duration") or s.get("estimated_duration") or 10.0)
        pause = float(s.get("pause_after") or 0.0)
        cursor += dur + SCENE_GAP_SECONDS + pause
    return starts


def validate_video_against_script(
    video_path: str,
    script_path: str | None = None,
    scenes: list[dict] | None = None,
) -> list[SceneValidation]:
    """Validate a rendered video by sampling one frame per scene.

    Provide either ``script_path`` (path to script.json) OR ``scenes`` (already
    loaded list of scene dicts). Returns one ``SceneValidation`` per scene.
    """
    if not _check_ffmpeg():
        logger.warning("ffmpeg not available — frame validation skipped")
        return []

    if scenes is None:
        if script_path is None:
            raise ValueError("Provide either script_path or scenes")
        with open(script_path, encoding="utf-8") as f:
            scenes = json.load(f).get("scenes", [])

    # Probe video duration so we don't sample past EOF.
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            check=True, capture_output=True, text=True,
        )
        video_duration = float(out.stdout.strip())
    except Exception:
        video_duration = 600.0

    scene_starts = _compute_scene_starts(scenes)
    results: list[SceneValidation] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        for i, scene in enumerate(scenes):
            sample_times = _scene_sample_times(scene_starts, i, video_duration)
            in_range_times = [t for t in sample_times if t < video_duration]

            if not in_range_times:
                results.append(SceneValidation(
                    scene_id=scene.get("scene_id", f"scene_{i}"),
                    timestamp=sample_times[0],
                    severity="warn",
                    findings=[FrameFinding(
                        type="missing",
                        severity="warn",
                        detail=(
                            f"scene start {sample_times[0]:.1f}s past video end "
                            f"{video_duration:.1f}s"
                        ),
                    )],
                ))
                continue

            # Sample multiple frames; only flag a scene if ALL samples agree.
            per_sample_findings: list[list[FrameFinding]] = []
            for j, ts in enumerate(in_range_times):
                frame_path = str(Path(tmpdir) / f"frame_{i}_{j}.png")
                if not _extract_frame(video_path, ts, frame_path):
                    continue
                try:
                    img = Image.open(frame_path).convert("RGB")
                    arr = np.array(img)
                except Exception as e:
                    logger.warning("Failed to load frame %s: %s", frame_path, e)
                    continue
                per_sample_findings.append(_validate_frame(arr))

            if not per_sample_findings:
                continue

            # Aggregate: only flag a finding TYPE if it appears in EVERY sample.
            common_types: set[str] | None = None
            for sample in per_sample_findings:
                types = {f.type for f in sample}
                common_types = types if common_types is None else (common_types & types)
            common_types = common_types or set()

            agg_findings = [
                f for f in per_sample_findings[len(per_sample_findings) // 2]
                if f.type in common_types
            ]

            if not agg_findings:
                severity = "ok"
            elif any(f.severity == "fail" for f in agg_findings):
                severity = "fail"
            else:
                severity = "warn"

            results.append(SceneValidation(
                scene_id=scene.get("scene_id", f"scene_{i}"),
                timestamp=in_range_times[len(in_range_times) // 2],
                severity=severity,
                findings=agg_findings,
            ))

    return results


def format_report(results: list[SceneValidation]) -> str:
    """Render validation results as a compact human-readable report."""
    if not results:
        return "Frame validation: no results."
    fails = [r for r in results if r.severity == "fail"]
    warns = [r for r in results if r.severity == "warn"]
    lines = [
        f"Frame validation: {len(results)} scenes  "
        f"({len(fails)} fail, {len(warns)} warn, "
        f"{len(results) - len(fails) - len(warns)} ok)",
    ]
    for r in results:
        if r.severity == "ok":
            continue
        lines.append(f"  [{r.severity.upper()}] {r.scene_id} @ t={r.timestamp:.1f}s")
        for f in r.findings:
            lines.append(f"      - {f.type}: {f.detail}")
    return "\n".join(lines)
