"""Tests for the shorts orchestrator's sanitization layer.

These guard the contract that the shorts pipeline never lets a wide-canvas
action (topology, sequence diagram, comparison, table) reach the vertical
renderer — and never ships more than 4 scenes regardless of LLM behavior.

No real LLM calls; we exercise the helper functions directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shorts_orchestrator import (
    _filter_to_vertical_actions,
    _truncate_scenes,
    _MAX_SHORTS_SCENES,
)
from prompts.shorts import VERTICAL_ACTION_WHITELIST


class TestVerticalActionFilter:
    def test_keeps_whitelisted_actions(self):
        data = {
            "scenes": [
                {
                    "scene_id": "hook",
                    "actions": [
                        {"type": "show_text_block", "text": "..."},
                        {"type": "emphasize_text", "ref_id": "x"},
                        {"type": "flash_cut"},
                    ],
                },
            ],
        }
        cleaned = _filter_to_vertical_actions(data)
        kept = [a["type"] for a in cleaned["scenes"][0]["actions"]]
        assert kept == ["show_text_block", "emphasize_text", "flash_cut"]

    def test_strips_horizontal_actions(self, caplog):
        """Wide-canvas actions must be removed before reaching the
        vertical renderer."""
        data = {
            "scenes": [
                {
                    "scene_id": "tension",
                    "actions": [
                        {"type": "create_topology", "topology": "star"},
                        {"type": "show_text_block", "text": "..."},
                        {"type": "show_sequence_diagram"},
                        {"type": "show_comparison"},
                        {"type": "show_table"},
                        {"type": "create_node", "id": "a"},
                        {"type": "send_packet", "from_id": "a", "to_id": "b"},
                        {"type": "show_chart"},
                        {"type": "show_layer_stack"},
                        {"type": "create_cloud_region"},
                        {"type": "emphasize_text"},
                    ],
                },
            ],
        }
        with caplog.at_level("WARNING"):
            cleaned = _filter_to_vertical_actions(data)

        kept = [a["type"] for a in cleaned["scenes"][0]["actions"]]
        # Only the two whitelisted actions survive
        assert kept == ["show_text_block", "emphasize_text"]
        # Each stripped action logs a warning
        warnings = [r for r in caplog.records if "Stripping non-vertical" in r.message]
        assert len(warnings) >= 8

    def test_handles_empty_scenes(self):
        data = {"scenes": []}
        assert _filter_to_vertical_actions(data) == data

    def test_handles_scene_without_actions(self):
        data = {"scenes": [{"scene_id": "x"}]}
        result = _filter_to_vertical_actions(data)
        assert result["scenes"][0]["actions"] == []

    def test_whitelist_matches_documented_set(self):
        """Sanity check: whitelist contains exactly the actions documented
        in the shorts prompt as ALLOWED."""
        expected = {
            "show_text_block",
            "show_bullet_list",
            "emphasize_text",
            "pulse_element",
            "shake_element",
            "flash_cut",
            "zoom_punch",
            "glitch_transition",
            "scene_transition",
            "show_image",
            "show_code_block",
        }
        assert VERTICAL_ACTION_WHITELIST == expected


class TestSceneTruncation:
    def test_caps_at_four_scenes(self, caplog):
        data = {"scenes": [{"scene_id": f"s{i}"} for i in range(7)]}
        with caplog.at_level("WARNING"):
            result = _truncate_scenes(data)
        assert len(result["scenes"]) == _MAX_SHORTS_SCENES == 4
        assert [s["scene_id"] for s in result["scenes"]] == ["s0", "s1", "s2", "s3"]
        assert any("truncating to 4" in r.message for r in caplog.records)

    def test_passthrough_when_under_cap(self):
        data = {"scenes": [{"scene_id": f"s{i}"} for i in range(3)]}
        result = _truncate_scenes(data)
        assert len(result["scenes"]) == 3

    def test_passthrough_at_exact_cap(self):
        data = {"scenes": [{"scene_id": f"s{i}"} for i in range(4)]}
        result = _truncate_scenes(data)
        assert len(result["scenes"]) == 4

    def test_handles_empty(self):
        assert _truncate_scenes({"scenes": []}) == {"scenes": []}


class TestVerticalRunnerCanvas:
    def test_runner_module_sets_vertical_frame(self):
        """Importing shorts_runner must reshape Manim's global config to
        9:16 BEFORE the Scene class is created.  This is the one cross-cutting
        invariant that, if broken, would silently render a wide short."""
        import rendering_engine.shorts_runner  # noqa: F401
        from manim import config as mc

        # Allow tiny float rounding
        assert abs(mc.frame_width - 8.0) < 0.01
        assert abs(mc.frame_height - 14.222) < 0.01
        assert mc.frame_height > mc.frame_width  # taller than wide
