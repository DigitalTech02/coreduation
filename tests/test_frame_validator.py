"""Tests for frame_validator (Track 4A)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from frame_validator import (
    SceneValidation,
    _check_blank,
    _check_edge_clip,
    _check_no_readable_text,
    _compute_scene_starts,
    _luminance,
    _validate_frame,
    format_report,
)


def _make_frame(h: int = 720, w: int = 1280, bg_rgb=(20, 20, 28)) -> np.ndarray:
    """Build a uniform-background frame at 720p by default."""
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[..., 0] = bg_rgb[0]
    arr[..., 1] = bg_rgb[1]
    arr[..., 2] = bg_rgb[2]
    return arr


class TestLuminance:
    def test_white_max(self):
        arr = np.full((10, 10, 3), 255, dtype=np.uint8)
        assert _luminance(arr).mean() == pytest.approx(255.0)

    def test_black_zero(self):
        arr = np.zeros((10, 10, 3), dtype=np.uint8)
        assert _luminance(arr).mean() == pytest.approx(0.0)


class TestCheckBlank:
    def test_blank_bg_only(self):
        arr = _make_frame()
        finding = _check_blank(_luminance(arr) >= 60)
        assert finding is not None
        assert finding.type == "blank"
        assert finding.severity == "fail"

    def test_with_content_passes(self):
        arr = _make_frame()
        # Plant a 200×200 white square in the middle (~4% of canvas)
        arr[260:460, 540:740] = (240, 240, 240)
        finding = _check_blank(_luminance(arr) >= 60)
        assert finding is None


class TestCheckEdgeClip:
    def test_clean_center_passes(self):
        arr = _make_frame()
        arr[300:420, 540:740] = (220, 220, 220)
        finding = _check_edge_clip(_luminance(arr) >= 60)
        assert finding is None

    def test_top_edge_clip_flagged(self):
        arr = _make_frame()
        # Bright band of pixels at the very top edge
        arr[:8, :] = (240, 240, 240)
        finding = _check_edge_clip(_luminance(arr) >= 60)
        assert finding is not None
        assert finding.type == "edge_clip"


class TestCheckNoReadableText:
    def test_no_bright_pixels_warns(self):
        arr = _make_frame()
        finding = _check_no_readable_text(_luminance(arr))
        assert finding is not None
        assert finding.type == "no_readable_text"

    def test_some_bright_text_passes(self):
        arr = _make_frame()
        # Plant bright pixels mimicking text
        arr[300:340, 500:780] = (250, 250, 250)
        finding = _check_no_readable_text(_luminance(arr))
        assert finding is None


class TestValidateFrame:
    def test_blank_frame_one_finding(self):
        arr = _make_frame()
        findings = _validate_frame(arr)
        # Blank scene also has no readable text — both should fire
        types = {f.type for f in findings}
        assert "blank" in types

    def test_clean_content_no_findings(self):
        arr = _make_frame()
        arr[300:420, 500:780] = (240, 240, 240)
        findings = _validate_frame(arr)
        assert findings == []


class TestSceneStarts:
    def test_uses_audio_duration_when_present(self):
        scenes = [
            {"audio_duration": 10.0, "pause_after": 0.5},
            {"audio_duration": 12.0, "pause_after": 0.0},
        ]
        starts = _compute_scene_starts(scenes, intro_offset=2.5)
        # First scene starts at intro_offset
        assert starts[0] == pytest.approx(2.5)
        # Second starts after first scene + gap (0.15) + pause_after (0.5)
        assert starts[1] == pytest.approx(2.5 + 10.0 + 0.15 + 0.5)

    def test_falls_back_to_estimated_duration(self):
        scenes = [{"estimated_duration": 8.0}]
        starts = _compute_scene_starts(scenes)
        assert starts[0] == pytest.approx(2.5)


class TestFormatReport:
    def test_empty(self):
        assert "no results" in format_report([])

    def test_summary_counts(self):
        results = [
            SceneValidation(scene_id="a", timestamp=1.0, severity="ok"),
            SceneValidation(scene_id="b", timestamp=2.0, severity="warn"),
            SceneValidation(scene_id="c", timestamp=3.0, severity="fail"),
        ]
        report = format_report(results)
        assert "1 fail" in report
        assert "1 warn" in report
        assert "1 ok" in report
