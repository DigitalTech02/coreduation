"""Tests for pause_after threading through semantic_audio.

These tests stub pydub's file I/O so they run without ffmpeg or real MP3s.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydub import AudioSegment

import semantic_audio
from rendering_engine.styles import SCENE_GAP_SECONDS, TITLE_CARD_SECONDS


@pytest.fixture
def stub_pydub(monkeypatch, tmp_path):
    """Replace AudioSegment.from_file and .export with no-disk stubs.

    Each fake scene file is treated as 5.0s of silence (5000ms), so total
    track length is fully determined by the function's internal arithmetic.
    """
    SCENE_LEN_MS = 5000

    def fake_from_file(_path, *_, **__):
        return AudioSegment.silent(SCENE_LEN_MS)

    captured = {}

    def fake_export(self, out_path, format="mp3", **__):
        captured["length_ms"] = len(self)
        captured["out_path"] = str(out_path)
        Path(out_path).write_bytes(b"")  # touch so callers don't blow up
        return self

    monkeypatch.setattr(AudioSegment, "from_file", staticmethod(fake_from_file))
    monkeypatch.setattr(AudioSegment, "export", fake_export)
    # Disable SFX, music, intro, and outro padding so the math is purely the
    # narration body + inter-scene gaps.
    monkeypatch.setattr(semantic_audio, "_intro_seconds", lambda: 0.0)
    monkeypatch.setattr(semantic_audio, "_outro_seconds", lambda: 0.0)

    # Force-disable optional features
    import config
    monkeypatch.setattr(config, "ENABLE_SFX", False, raising=False)
    monkeypatch.setattr(config, "ENABLE_BACKGROUND_MUSIC", False, raising=False)

    return {"scene_len_ms": SCENE_LEN_MS, "captured": captured}


def _expected_total_ms(scene_count: int, pauses: list[float] | None, scene_len_ms: int = 5000) -> int:
    """Mirror the arithmetic in build_semantic_narration_track."""
    intro_ms = int(TITLE_CARD_SECONDS * 1000)
    body_ms = scene_count * scene_len_ms
    gaps_ms = 0
    for i in range(scene_count - 1):
        pause_s = pauses[i] if pauses and i < len(pauses) else 0.0
        gaps_ms += int((SCENE_GAP_SECONDS + pause_s) * 1000)
    return intro_ms + body_ms + gaps_ms


class TestBuildSemanticNarrationTrack:
    def test_no_pauses_baseline(self, stub_pydub, tmp_path):
        scene_paths = [str(tmp_path / f"s{i}.mp3") for i in range(3)]
        for p in scene_paths:
            Path(p).write_bytes(b"")
        out_path = str(tmp_path / "out.mp3")

        semantic_audio.build_semantic_narration_track(
            scene_paths, output_path=out_path
        )

        expected = _expected_total_ms(3, pauses=None)
        assert stub_pydub["captured"]["length_ms"] == expected

    def test_pause_after_extends_silence(self, stub_pydub, tmp_path):
        scene_paths = [str(tmp_path / f"s{i}.mp3") for i in range(3)]
        for p in scene_paths:
            Path(p).write_bytes(b"")
        out_path = str(tmp_path / "out.mp3")

        pauses = [1.5, 0.8, 0.0]  # last one ignored (no gap after final scene)
        semantic_audio.build_semantic_narration_track(
            scene_paths, output_path=out_path, scene_pauses=pauses
        )

        expected = _expected_total_ms(3, pauses=pauses)
        assert stub_pydub["captured"]["length_ms"] == expected

    def test_last_scene_pause_is_ignored(self, stub_pydub, tmp_path):
        """A pause on the final scene should not extend the track — there's no
        next scene to gap towards."""
        scene_paths = [str(tmp_path / f"s{i}.mp3") for i in range(2)]
        for p in scene_paths:
            Path(p).write_bytes(b"")
        out_path = str(tmp_path / "out.mp3")

        # Pause only on the last scene
        semantic_audio.build_semantic_narration_track(
            scene_paths, output_path=out_path, scene_pauses=[0.0, 5.0]
        )

        # Should match no-pauses length
        no_pause_expected = _expected_total_ms(2, pauses=None)
        assert stub_pydub["captured"]["length_ms"] == no_pause_expected

    def test_shorter_pauses_list_is_tolerated(self, stub_pydub, tmp_path):
        """If scene_pauses is shorter than scene count, extra scenes get 0.0."""
        scene_paths = [str(tmp_path / f"s{i}.mp3") for i in range(4)]
        for p in scene_paths:
            Path(p).write_bytes(b"")
        out_path = str(tmp_path / "out.mp3")

        # Only first scene has a pause
        pauses = [2.0]
        semantic_audio.build_semantic_narration_track(
            scene_paths, output_path=out_path, scene_pauses=pauses
        )

        expected = _expected_total_ms(4, pauses=pauses)
        assert stub_pydub["captured"]["length_ms"] == expected

    def test_empty_paths_raises(self, stub_pydub):
        with pytest.raises(ValueError, match="scene_audio_paths"):
            semantic_audio.build_semantic_narration_track([])

    def test_outro_tail_silence_added(self, monkeypatch, stub_pydub, tmp_path):
        """When the outro card is enabled, build_semantic_narration_track
        appends OUTRO_DURATION + 0.6s of silence so ffmpeg -shortest doesn't
        crop the outro."""
        monkeypatch.setattr(semantic_audio, "_outro_seconds", lambda: 3.5)

        scene_paths = [str(tmp_path / f"s{i}.mp3") for i in range(2)]
        for p in scene_paths:
            Path(p).write_bytes(b"")
        out_path = str(tmp_path / "out.mp3")

        semantic_audio.build_semantic_narration_track(
            scene_paths, output_path=out_path
        )

        baseline = _expected_total_ms(2, pauses=None)
        expected_with_outro = baseline + int((3.5 + 0.6) * 1000)
        assert stub_pydub["captured"]["length_ms"] == expected_with_outro


class TestBuildSfxTrackPauses:
    """build_sfx_track also computes a timeline that must include pauses."""

    def test_total_ms_matches_narration_when_pauses_added(self, monkeypatch):
        # Stub _load_sfx so missing assets don't matter
        monkeypatch.setattr(semantic_audio, "_load_sfx", lambda _t: None)
        monkeypatch.setattr(semantic_audio, "_intro_seconds", lambda: 0.0)

        scene_durations = [5.0, 5.0, 5.0]
        scene_actions = [[], [], []]  # no actions -> any_sfx=False -> returns None
        pauses = [1.0, 0.5, 0.0]

        result = semantic_audio.build_sfx_track(
            scene_actions, scene_durations, scene_pauses=pauses
        )
        # No SFX assets -> returns None; we're only verifying the call
        # accepts scene_pauses without crashing.
        assert result is None
