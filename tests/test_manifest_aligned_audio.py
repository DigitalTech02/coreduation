"""Tests for ``build_narration_track_from_manifest`` — the AV-sync fix.

The manifest-based audio builder is the structural fix for the cross-scene
drift that was causing narration/subtitles to fall behind visuals after
~1:30 in long videos.  These tests verify the invariants that prevent that
class of bug from coming back, regardless of how scene actions are timed:

1. Total audio length always equals manifest.total_video_duration.
2. Each scene's TTS lands at exactly its declared video_start_seconds —
   even when the renderer's per-scene budget is irregular (i.e. action
   animations overshot, which is the root cause of the original bug).
3. Audio that would overflow a scene's rendered slot gets trimmed.
4. Mismatched scene_ids fall back gracefully.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydub import AudioSegment

import semantic_audio


@pytest.fixture
def stub_pydub(monkeypatch, tmp_path):
    """Stub pydub I/O so tests run without ffmpeg or real MP3 files.

    Each scene file is treated as a fixed-duration silent segment whose
    length is derived from the file's stem (s0.mp3 -> 0, s1.mp3 -> 1, ...)
    so we can assert each scene was placed at the right offset.
    """
    captured: dict = {"overlays": [], "exported_length_ms": None, "exported_path": None}

    SCENE_LEN_MS = 4000  # 4s — shorter than typical rendered slot

    def fake_from_file(path, *_, **__):
        return AudioSegment.silent(SCENE_LEN_MS)

    real_overlay = AudioSegment.overlay

    def tracking_overlay(self, seg, position=0, **kwargs):
        captured["overlays"].append(
            {"len_ms": len(seg), "position_ms": int(position)},
        )
        return real_overlay(self, seg, position=position, **kwargs)

    def fake_export(self, out_path, format="mp3", **__):
        captured["exported_length_ms"] = len(self)
        captured["exported_path"] = str(out_path)
        Path(out_path).write_bytes(b"")
        return self

    monkeypatch.setattr(AudioSegment, "from_file", staticmethod(fake_from_file))
    monkeypatch.setattr(AudioSegment, "overlay", tracking_overlay)
    monkeypatch.setattr(AudioSegment, "export", fake_export)

    import config
    monkeypatch.setattr(config, "ENABLE_SFX", False, raising=False)
    monkeypatch.setattr(config, "ENABLE_BACKGROUND_MUSIC", False, raising=False)

    return {"scene_len_ms": SCENE_LEN_MS, "captured": captured}


def _make_paths(tmp_path: Path, n: int) -> list[str]:
    paths = [str(tmp_path / f"s{i}.mp3") for i in range(n)]
    for p in paths:
        Path(p).write_bytes(b"")
    return paths


class TestManifestAlignedNarration:
    def test_output_length_equals_manifest_total(self, stub_pydub, tmp_path):
        """Output mp3 length must exactly match the silent video's length."""
        scene_paths = _make_paths(tmp_path, 3)
        scene_ids = ["a", "b", "c"]

        manifest = {
            "total_video_duration": 60.0,
            "scenes": [
                {"scene_id": "a", "video_start_seconds": 5.0, "video_end_seconds": 15.0},
                {"scene_id": "b", "video_start_seconds": 20.0, "video_end_seconds": 35.0},
                {"scene_id": "c", "video_start_seconds": 40.0, "video_end_seconds": 60.0},
            ],
        }

        out = str(tmp_path / "out.mp3")
        semantic_audio.build_narration_track_from_manifest(
            scene_paths, scene_ids, manifest, out,
        )

        assert stub_pydub["captured"]["exported_length_ms"] == 60_000

    def test_each_scene_lands_at_declared_video_start(self, stub_pydub, tmp_path):
        """Narration overlay positions must equal the manifest's video_start
        for each scene — independent of what audio_dur or pause_after say.

        This is the AV-sync invariant: if action animations overshot in
        scene 1, scene 2 starts at a different absolute video time than
        the legacy builder would compute, but the manifest reports the
        actual time and we MUST trust it.
        """
        scene_paths = _make_paths(tmp_path, 3)
        scene_ids = ["a", "b", "c"]

        # Irregular scene boundaries — what would happen if scene 0 overshot
        # by 4s and scene 1 by 2s in a real render.  Cumulative drift from
        # the legacy estimated builder would be 6s; the manifest builder
        # must place audio at the correct absolute times regardless.
        manifest = {
            "total_video_duration": 100.0,
            "scenes": [
                {"scene_id": "a", "video_start_seconds": 5.0,  "video_end_seconds": 19.0},
                {"scene_id": "b", "video_start_seconds": 22.0, "video_end_seconds": 40.0},
                {"scene_id": "c", "video_start_seconds": 45.0, "video_end_seconds": 95.0},
            ],
        }

        out = str(tmp_path / "out.mp3")
        semantic_audio.build_narration_track_from_manifest(
            scene_paths, scene_ids, manifest, out,
        )

        positions = sorted(
            o["position_ms"] for o in stub_pydub["captured"]["overlays"]
        )
        assert positions == [5000, 22000, 45000]

    def test_scene_id_match_uses_id_not_index(self, stub_pydub, tmp_path):
        """Scenes are matched by scene_id, so the order of manifest entries
        doesn't have to match the order of scene_audio_paths.  Robust to
        future changes that might reorder the manifest."""
        scene_paths = _make_paths(tmp_path, 2)
        scene_ids = ["alpha", "beta"]

        # Manifest in REVERSED order
        manifest = {
            "total_video_duration": 50.0,
            "scenes": [
                {"scene_id": "beta",  "video_start_seconds": 30.0, "video_end_seconds": 45.0},
                {"scene_id": "alpha", "video_start_seconds": 5.0,  "video_end_seconds": 25.0},
            ],
        }

        out = str(tmp_path / "out.mp3")
        semantic_audio.build_narration_track_from_manifest(
            scene_paths, scene_ids, manifest, out,
        )

        # First overlay (alpha at index 0) should land at 5s; second (beta
        # at index 1) at 30s — proves we matched by id, not by position.
        positions = [o["position_ms"] for o in stub_pydub["captured"]["overlays"]]
        assert positions == [5000, 30000]

    def test_missing_scene_id_falls_back_to_position(self, stub_pydub, tmp_path, caplog):
        """If a scene_id is missing from the manifest, the builder falls back
        to positional matching and warns — never crashes."""
        scene_paths = _make_paths(tmp_path, 2)
        scene_ids = ["x", "y"]  # neither matches manifest

        manifest = {
            "total_video_duration": 30.0,
            "scenes": [
                {"scene_id": "different_id_1", "video_start_seconds": 2.0, "video_end_seconds": 10.0},
                {"scene_id": "different_id_2", "video_start_seconds": 15.0, "video_end_seconds": 28.0},
            ],
        }

        out = str(tmp_path / "out.mp3")
        with caplog.at_level("WARNING"):
            semantic_audio.build_narration_track_from_manifest(
                scene_paths, scene_ids, manifest, out,
            )

        positions = sorted(
            o["position_ms"] for o in stub_pydub["captured"]["overlays"]
        )
        assert positions == [2000, 15000]
        assert any("not in manifest" in rec.message for rec in caplog.records)

    def test_scene_not_in_manifest_at_all_is_skipped(self, stub_pydub, tmp_path, caplog):
        """A scene that has no manifest entry AND no positional fallback
        (because manifest has fewer entries than scene_audio_paths) is
        skipped with a warning rather than crashing the run."""
        scene_paths = _make_paths(tmp_path, 3)
        scene_ids = ["a", "b", "c"]

        manifest = {
            "total_video_duration": 30.0,
            "scenes": [
                {"scene_id": "a", "video_start_seconds": 1.0, "video_end_seconds": 10.0},
                {"scene_id": "b", "video_start_seconds": 12.0, "video_end_seconds": 25.0},
                # No entry for c
            ],
        }

        out = str(tmp_path / "out.mp3")
        with caplog.at_level("WARNING"):
            semantic_audio.build_narration_track_from_manifest(
                scene_paths, scene_ids, manifest, out,
            )

        # Only 2 overlays — c is skipped
        positions = sorted(
            o["position_ms"] for o in stub_pydub["captured"]["overlays"]
        )
        assert positions == [1000, 12000]

    def test_audio_overrun_gets_trimmed(self, stub_pydub, tmp_path, caplog):
        """If a scene's TTS mp3 is longer than its rendered slot in the
        manifest, the audio is trimmed so it cannot bleed into the next
        scene's window.  Symptomatic protection — should be rare since the
        renderer reserves audio_duration up front."""
        scene_paths = _make_paths(tmp_path, 2)
        scene_ids = ["a", "b"]

        # Slot 'a' is only 2s but stub_pydub generates 4s mp3s
        manifest = {
            "total_video_duration": 20.0,
            "scenes": [
                {"scene_id": "a", "video_start_seconds": 1.0, "video_end_seconds": 3.0},
                {"scene_id": "b", "video_start_seconds": 10.0, "video_end_seconds": 18.0},
            ],
        }

        out = str(tmp_path / "out.mp3")
        with caplog.at_level("WARNING"):
            semantic_audio.build_narration_track_from_manifest(
                scene_paths, scene_ids, manifest, out,
            )

        # 'a' should be trimmed to 2000ms (slot length); 'b' fits naturally
        overlays_by_pos = {
            o["position_ms"]: o for o in stub_pydub["captured"]["overlays"]
        }
        assert overlays_by_pos[1000]["len_ms"] == 2000
        assert overlays_by_pos[10000]["len_ms"] == 4000
        assert any("longer than rendered slot" in rec.message for rec in caplog.records)

    def test_invalid_total_duration_raises(self, stub_pydub, tmp_path):
        """A manifest without a usable total_video_duration is a fatal error;
        caller must fall back to the legacy builder."""
        scene_paths = _make_paths(tmp_path, 1)
        scene_ids = ["a"]

        manifest = {"total_video_duration": 0.0, "scenes": []}

        out = str(tmp_path / "out.mp3")
        with pytest.raises(ValueError, match="total_video_duration"):
            semantic_audio.build_narration_track_from_manifest(
                scene_paths, scene_ids, manifest, out,
            )

    def test_id_path_length_mismatch_raises(self, stub_pydub, tmp_path):
        scene_paths = _make_paths(tmp_path, 2)

        manifest = {
            "total_video_duration": 10.0,
            "scenes": [
                {"scene_id": "a", "video_start_seconds": 1.0, "video_end_seconds": 5.0},
            ],
        }

        out = str(tmp_path / "out.mp3")
        with pytest.raises(ValueError, match="same length"):
            semantic_audio.build_narration_track_from_manifest(
                scene_paths, ["a"], manifest, out,
            )

    def test_empty_paths_raises(self, stub_pydub, tmp_path):
        manifest = {"total_video_duration": 10.0, "scenes": []}
        out = str(tmp_path / "out.mp3")
        with pytest.raises(ValueError, match="scene_audio_paths"):
            semantic_audio.build_narration_track_from_manifest(
                [], [], manifest, out,
            )

    def test_drift_invariant_across_arbitrary_overshoots(self, stub_pydub, tmp_path):
        """Property-style: regardless of how irregular the manifest's per-scene
        boundaries are, narration is always at the right absolute time and
        the output never exceeds the silent video length.

        This is the regression guard: if a future change reverts to
        cumulative-estimate placement, this will fail because the cumulative
        estimate can't reproduce arbitrary overshoots.
        """
        # 5 scenes at irregular positions simulating various overshoots
        scene_paths = _make_paths(tmp_path, 5)
        scene_ids = [f"sc{i}" for i in range(5)]

        manifest = {
            "total_video_duration": 200.0,
            "scenes": [
                {"scene_id": "sc0", "video_start_seconds": 5.13,   "video_end_seconds": 18.0},
                {"scene_id": "sc1", "video_start_seconds": 21.7,   "video_end_seconds": 40.0},
                {"scene_id": "sc2", "video_start_seconds": 44.55,  "video_end_seconds": 70.0},
                {"scene_id": "sc3", "video_start_seconds": 78.91,  "video_end_seconds": 110.0},
                {"scene_id": "sc4", "video_start_seconds": 117.42, "video_end_seconds": 195.0},
            ],
        }

        out = str(tmp_path / "out.mp3")
        semantic_audio.build_narration_track_from_manifest(
            scene_paths, scene_ids, manifest, out,
        )

        positions = sorted(
            o["position_ms"] for o in stub_pydub["captured"]["overlays"]
        )
        assert positions == [5130, 21700, 44550, 78910, 117420]
        assert stub_pydub["captured"]["exported_length_ms"] == 200_000
