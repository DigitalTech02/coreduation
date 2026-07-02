"""Tests for llm_orchestrator_semantic._sanitize_script_dict.

The LLM occasionally hallucinates action types that the rendering engine
doesn't know about. The sanitizer strips them so Pydantic validation
doesn't crash the whole pipeline.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm_orchestrator_semantic import _VALID_ACTION_TYPES, _sanitize_script_dict


class TestValidActionRegistry:
    def test_registry_is_non_empty(self):
        assert len(_VALID_ACTION_TYPES) > 20

    def test_registry_includes_core_actions(self):
        for required in [
            "create_node", "create_connection", "send_packet",
            "show_text_block", "show_table", "show_code_block",
        ]:
            assert required in _VALID_ACTION_TYPES, f"core action missing: {required}"

    def test_registry_includes_retention_actions(self):
        for required in ["pulse_element", "shake_element", "dim_except", "focus_camera"]:
            assert required in _VALID_ACTION_TYPES


class TestSanitizeScriptDict:
    def test_keeps_known_actions(self):
        data = {
            "scenes": [
                {
                    "scene_id": "s1",
                    "actions": [
                        {"type": "create_node", "id": "n1", "label": "N"},
                        {"type": "send_packet", "from": "a", "to": "b"},
                    ],
                }
            ]
        }
        out = _sanitize_script_dict(data)
        assert len(out["scenes"][0]["actions"]) == 2

    def test_strips_unknown_actions(self, caplog):
        data = {
            "scenes": [
                {
                    "scene_id": "s1",
                    "actions": [
                        {"type": "create_node", "id": "n1", "label": "N"},
                        {"type": "overlay", "text": "bad"},
                        {"type": "annotate", "text": "also bad"},
                        {"type": "show_table", "headers": ["A"], "rows": []},
                    ],
                }
            ]
        }
        with caplog.at_level(logging.WARNING, logger="llm_orchestrator_semantic"):
            out = _sanitize_script_dict(data)

        kept_types = [a["type"] for a in out["scenes"][0]["actions"]]
        assert kept_types == ["create_node", "show_table"]
        assert any("overlay" in r.message for r in caplog.records)
        assert any("annotate" in r.message for r in caplog.records)
        assert any("s1" in r.message for r in caplog.records)

    def test_handles_missing_actions_key(self):
        data = {"scenes": [{"scene_id": "s1"}]}
        out = _sanitize_script_dict(data)
        assert out["scenes"][0]["actions"] == []

    def test_handles_missing_type_key(self, caplog):
        data = {
            "scenes": [
                {
                    "scene_id": "s1",
                    "actions": [
                        {"id": "n1"},  # no "type" key
                        {"type": "create_node", "id": "n2", "label": "N"},
                    ],
                }
            ]
        }
        with caplog.at_level(logging.WARNING, logger="llm_orchestrator_semantic"):
            out = _sanitize_script_dict(data)
        kept = out["scenes"][0]["actions"]
        assert len(kept) == 1
        assert kept[0]["type"] == "create_node"

    def test_handles_missing_scenes_key(self):
        # No scenes at all — should not raise
        out = _sanitize_script_dict({"topic": "test"})
        assert out == {"topic": "test"}

    def test_empty_actions_list_unchanged(self):
        data = {"scenes": [{"scene_id": "s1", "actions": []}]}
        out = _sanitize_script_dict(data)
        assert out["scenes"][0]["actions"] == []

    def test_multiple_scenes_independent(self, caplog):
        data = {
            "scenes": [
                {"scene_id": "s1", "actions": [{"type": "bogus"}]},
                {"scene_id": "s2", "actions": [{"type": "create_node", "id": "n", "label": "L"}]},
            ]
        }
        with caplog.at_level(logging.WARNING, logger="llm_orchestrator_semantic"):
            out = _sanitize_script_dict(data)

        assert out["scenes"][0]["actions"] == []
        assert len(out["scenes"][1]["actions"]) == 1
        # Warning cited s1 specifically, not s2
        warned = " ".join(r.message for r in caplog.records)
        assert "'s1'" in warned
        assert "'s2'" not in warned

    def test_unknown_scene_id_in_warning_falls_back(self, caplog):
        data = {"scenes": [{"actions": [{"type": "bogus"}]}]}
        with caplog.at_level(logging.WARNING, logger="llm_orchestrator_semantic"):
            _sanitize_script_dict(data)
        # Falls back to "?" placeholder so warning still lands
        assert any("'?'" in r.message for r in caplog.records)

    def test_returns_same_dict_object(self):
        """Mutates in place — callers rely on this for cache replay."""
        data = {"scenes": [{"actions": [{"type": "create_node", "id": "n", "label": "L"}]}]}
        out = _sanitize_script_dict(data)
        assert out is data
