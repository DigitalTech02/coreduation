"""Tests for the retention upgrade: new actions, validation, subtitles, config, backward compat."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter

# Ensure project root is importable
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models_semantic import (
    AddCallout,
    DimExcept,
    EmphasizeText,
    EnrichedScene,
    EnrichedVideoScript,
    FocusCamera,
    PulseElement,
    ResetCamera,
    RestoreOpacity,
    SceneTransition,
    SemanticVideoScript,
    ShakeElement,
    ShowProgress,
    UpdateProgress,
    VisualAction,
)
from semantic_validation import validate_semantic_script


# ---------------------------------------------------------------------------
# Pydantic parsing of new actions
# ---------------------------------------------------------------------------

adapter = TypeAdapter(VisualAction)


class TestNewActionParsing:
    def test_pulse_element(self):
        a = adapter.validate_python({"type": "pulse_element", "target_id": "node1"})
        assert isinstance(a, PulseElement)
        assert a.target_id == "node1"
        assert a.intensity == 1.15
        assert a.duration == 0.5

    def test_focus_camera(self):
        a = adapter.validate_python({"type": "focus_camera", "target_id": "srv", "zoom": 1.3})
        assert isinstance(a, FocusCamera)
        assert a.zoom == 1.3

    def test_focus_camera_coords(self):
        a = adapter.validate_python({"type": "focus_camera", "x": 2.0, "y": -1.0, "zoom": 1.15})
        assert isinstance(a, FocusCamera)
        assert a.target_id is None
        assert a.x == 2.0

    def test_reset_camera(self):
        a = adapter.validate_python({"type": "reset_camera"})
        assert isinstance(a, ResetCamera)
        assert a.duration == 1.0

    def test_show_progress(self):
        a = adapter.validate_python({
            "type": "show_progress", "label": "Step 1", "current_step": 1, "total_steps": 5
        })
        assert isinstance(a, ShowProgress)
        assert a.total_steps == 5

    def test_update_progress(self):
        a = adapter.validate_python({
            "type": "update_progress", "label": "Step 3", "current_step": 3, "total_steps": 5
        })
        assert isinstance(a, UpdateProgress)

    def test_emphasize_text(self):
        a = adapter.validate_python({"type": "emphasize_text", "text": "O(log n)!"})
        assert isinstance(a, EmphasizeText)
        assert a.emphasis_type == "pop"

    def test_shake_element(self):
        a = adapter.validate_python({"type": "shake_element", "target_id": "table1"})
        assert isinstance(a, ShakeElement)
        assert a.intensity == 0.15

    def test_dim_except(self):
        a = adapter.validate_python({
            "type": "dim_except", "target_ids": ["a", "b"], "opacity": 0.2
        })
        assert isinstance(a, DimExcept)
        assert len(a.target_ids) == 2

    def test_restore_opacity(self):
        a = adapter.validate_python({"type": "restore_opacity", "duration": 0.3})
        assert isinstance(a, RestoreOpacity)

    def test_add_callout(self):
        a = adapter.validate_python({
            "type": "add_callout", "target_id": "node1", "text": "middle = 4"
        })
        assert isinstance(a, AddCallout)
        assert a.position == "auto"

    def test_scene_transition(self):
        a = adapter.validate_python({
            "type": "scene_transition", "transition_type": "wipe", "label": "Next"
        })
        assert isinstance(a, SceneTransition)


# ---------------------------------------------------------------------------
# Validation of target references for new actions
# ---------------------------------------------------------------------------

class TestValidationNewActions:
    def _make_script(self, actions: list[dict]) -> EnrichedVideoScript:
        return EnrichedVideoScript(
            topic="test",
            scenes=[
                EnrichedScene(
                    scene_id="s1", title="T", type="concept",
                    narration="N", visual_description="V",
                    actions=[adapter.validate_python(a) for a in actions],
                    estimated_duration=10,
                ),
            ],
        )

    def test_pulse_valid_target(self):
        script = self._make_script([
            {"type": "create_node", "id": "n1", "label": "N1"},
            {"type": "pulse_element", "target_id": "n1"},
        ])
        validate_semantic_script(script)

    def test_pulse_invalid_target_warns(self):
        """Retention actions with unknown targets warn but do not crash."""
        script = self._make_script([
            {"type": "pulse_element", "target_id": "missing"},
        ])
        warnings = validate_semantic_script(script)
        assert any("missing" in w for w in warnings)

    def test_shake_invalid_target_warns(self):
        script = self._make_script([
            {"type": "shake_element", "target_id": "gone"},
        ])
        warnings = validate_semantic_script(script)
        assert any("gone" in w for w in warnings)

    def test_dim_except_invalid_target_warns(self):
        script = self._make_script([
            {"type": "dim_except", "target_ids": ["missing"]},
        ])
        warnings = validate_semantic_script(script)
        assert any("missing" in w for w in warnings)

    def test_focus_camera_valid(self):
        script = self._make_script([
            {"type": "create_node", "id": "srv", "label": "Server"},
            {"type": "focus_camera", "target_id": "srv", "zoom": 1.2},
        ])
        validate_semantic_script(script)

    def test_focus_camera_no_target(self):
        script = self._make_script([
            {"type": "focus_camera", "x": 0, "y": 0},
        ])
        validate_semantic_script(script)

    def test_callout_invalid_warns(self):
        script = self._make_script([
            {"type": "add_callout", "target_id": "nope", "text": "hi"},
        ])
        warnings = validate_semantic_script(script)
        assert any("nope" in w for w in warnings)

    def test_core_actions_still_hard_fail(self):
        """Core topology/packet actions still raise on unknown refs."""
        script = self._make_script([
            {"type": "send_packet", "from": "ghost_a", "to": "ghost_b"},
        ])
        with pytest.raises(ValueError, match="unknown id"):
            validate_semantic_script(script)

    def test_no_validation_needed(self):
        script = self._make_script([
            {"type": "show_progress", "label": "Step", "current_step": 1, "total_steps": 3},
            {"type": "emphasize_text", "text": "Wow"},
            {"type": "restore_opacity"},
            {"type": "reset_camera"},
            {"type": "scene_transition", "label": "Next"},
        ])
        validate_semantic_script(script)


# ---------------------------------------------------------------------------
# Backward compatibility: old scripts still parse
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_old_script_no_metadata(self):
        raw = {
            "topic": "TCP Handshake",
            "scenes": [
                {
                    "scene_id": "s1",
                    "title": "Hook",
                    "type": "concept",
                    "narration": "Hello",
                    "visual_description": "Text",
                    "actions": [
                        {"type": "show_text_block", "title": "Hi", "body": "World"}
                    ],
                    "estimated_duration": 10,
                },
            ],
        }
        script = SemanticVideoScript.model_validate(raw)
        assert script.video_title == ""
        assert script.retention_beats == []

    def test_enriched_from_llm_preserves_metadata(self):
        raw = {
            "topic": "Test",
            "video_title": "My Title",
            "suggested_youtube_title": "YT Title",
            "scenes": [],
        }
        llm = SemanticVideoScript.model_validate(raw)
        enriched = EnrichedVideoScript.from_llm_output(llm)
        assert enriched.video_title == "My Title"
        assert enriched.suggested_youtube_title == "YT Title"

    def test_old_actions_still_parse(self):
        for action_type in [
            "create_node", "show_text_block", "show_table",
            "send_packet", "show_code_block",
        ]:
            if action_type == "create_node":
                data = {"type": action_type, "id": "n1", "label": "N"}
            elif action_type == "send_packet":
                data = {"type": action_type, "from": "a", "to": "b"}
            elif action_type == "show_table":
                data = {"type": action_type, "headers": ["A"], "rows": []}
            elif action_type == "show_code_block":
                data = {"type": action_type, "lines": ["x = 1"]}
            else:
                data = {"type": action_type}
            adapter.validate_python(data)


# ---------------------------------------------------------------------------
# Subtitle chunking
# ---------------------------------------------------------------------------

class TestSubtitleChunking:
    def test_basic_chunking(self):
        from rendering_engine.subtitles import chunk_narration
        text = "Binary search is a fast algorithm. It finds elements in sorted arrays."
        chunks = chunk_narration(text, max_words=7)
        assert len(chunks) >= 2
        for chunk in chunks:
            assert len(chunk.split()) <= 7

    def test_empty_text(self):
        from rendering_engine.subtitles import chunk_narration
        assert chunk_narration("") == []

    def test_long_sentence(self):
        from rendering_engine.subtitles import chunk_narration
        text = "This is a very long sentence that should be split into multiple chunks of at most five words each."
        chunks = chunk_narration(text, max_words=5)
        for chunk in chunks:
            assert len(chunk.split()) <= 5


# ---------------------------------------------------------------------------
# Config module
# ---------------------------------------------------------------------------

class TestConfig:
    def test_defaults(self):
        from config import (
            CAMERA_DEFAULT_ZOOM,
            CAMERA_MAX_ZOOM,
            ENABLE_BACKGROUND_MUSIC,
            ENABLE_CAMERA_MOTION,
            ENABLE_PROGRESS_UI,
            ENABLE_SFX,
            ENABLE_SUBTITLES,
            MAX_IDLE_VISUAL_SECONDS,
            RETENTION_MODE,
        )
        assert RETENTION_MODE is True
        assert MAX_IDLE_VISUAL_SECONDS == 3.0
        assert ENABLE_CAMERA_MOTION is True
        assert ENABLE_PROGRESS_UI is True
        assert ENABLE_SUBTITLES is True
        assert ENABLE_SFX is True
        assert ENABLE_BACKGROUND_MUSIC is True
        assert 1.0 <= CAMERA_DEFAULT_ZOOM <= 2.0
        assert CAMERA_MAX_ZOOM >= CAMERA_DEFAULT_ZOOM


# ---------------------------------------------------------------------------
# Sample script loads
# ---------------------------------------------------------------------------

class TestSampleScript:
    def test_sample_binary_search_parses(self):
        sample_path = Path(__file__).resolve().parent.parent / "samples" / "binary_search_sample.json"
        if not sample_path.is_file():
            pytest.skip("Sample file not found")
        raw = json.loads(sample_path.read_text(encoding="utf-8"))
        script = SemanticVideoScript.model_validate(raw)
        assert len(script.scenes) >= 10
        assert script.video_title != ""
        assert script.open_loop_question != ""

        enriched = EnrichedVideoScript.from_llm_output(script)
        validate_semantic_script(enriched)


# ---------------------------------------------------------------------------
# Retention enrichment
# ---------------------------------------------------------------------------

class TestRetentionEnrichment:
    def test_ensure_retention_beats_adds_pulse(self):
        from retention import ensure_retention_beats
        script = EnrichedVideoScript(
            topic="test",
            scenes=[
                EnrichedScene(
                    scene_id="s1", title="T", type="concept",
                    narration="A long narration that takes many seconds to say.",
                    visual_description="V",
                    actions=[adapter.validate_python(
                        {"type": "create_node", "id": "n1", "label": "N"}
                    )],
                    estimated_duration=30,
                    audio_duration=30,
                ),
            ],
        )
        result = ensure_retention_beats(script, max_idle_seconds=3.0)
        action_types = [a.type for a in result.scenes[0].actions]
        assert "pulse_element" in action_types
