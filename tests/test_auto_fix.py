"""Tests for auto_fix.collect_fixes and revise_failed_scenes.

LLM call is patched out — we only verify the orchestration logic
(merging findings, calling the LLM hook, applying the result).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import auto_fix
from auto_fix import SceneFix, collect_fixes, revise_failed_scenes


class _Fake4AFinding:
    """Mirror frame_validator.SceneValidation.to_dict shape."""

    def __init__(self, scene_id, severity, finding_types):
        self.scene_id = scene_id
        self.severity = severity
        self.finding_types = finding_types

    def to_dict(self):
        # Inner finding severities match the outer (mirrors how
        # frame_validator computes outer = max(inner severities)).
        inner_sev = self.severity if self.severity != "ok" else "warn"
        return {
            "scene_id": self.scene_id,
            "severity": self.severity,
            "findings": [
                {"type": t, "severity": inner_sev, "detail": f"{t} detail"}
                for t in self.finding_types
            ],
        }


class _Fake4BFinding:
    """Mirror vision_qa.SceneQAFinding.to_dict shape."""

    def __init__(self, scene_id, severity, issues, suggestion):
        self.scene_id = scene_id
        self.severity = severity
        self.issues = issues
        self.suggestion = suggestion

    def to_dict(self):
        return {
            "scene_id": self.scene_id,
            "severity": self.severity,
            "issues": self.issues,
            "description": "x",
            "suggestion": self.suggestion,
        }


SCENES = [
    {"scene_id": "intro", "actions": [{"type": "show_text_block", "title": "T"}]},
    {"scene_id": "broken", "actions": [{"type": "show_text_block", "title": "Broken"}]},
    {"scene_id": "outro", "actions": [{"type": "show_text_block", "title": "Bye"}]},
]


class TestCollectFixes:
    def test_no_failures_no_fixes(self):
        det = [_Fake4AFinding("intro", "ok", [])]
        qa = [_Fake4BFinding("intro", "ok", [], "")]
        assert collect_fixes(det, qa, SCENES) == []

    def test_4a_failure_produces_fix(self):
        det = [_Fake4AFinding("broken", "fail", ["blank"])]
        fixes = collect_fixes(det, [], SCENES)
        assert len(fixes) == 1
        assert fixes[0].scene_id == "broken"
        assert fixes[0].original_actions == SCENES[1]["actions"]
        assert any(f["type"] == "blank" for f in fixes[0].findings)

    def test_4b_failure_produces_fix(self):
        qa = [_Fake4BFinding("broken", "fail", ["overlap"], "move text up")]
        fixes = collect_fixes([], qa, SCENES)
        assert len(fixes) == 1
        assert fixes[0].findings[0]["suggestion"] == "move text up"

    def test_combined_findings_merge(self):
        det = [_Fake4AFinding("broken", "fail", ["blank"])]
        qa = [_Fake4BFinding("broken", "fail", ["misaligned"], "shrink list")]
        fixes = collect_fixes(det, qa, SCENES)
        assert len(fixes) == 1
        # Both findings present in the merged fix
        types = {f.get("type") or f.get("issues", [None])[0] for f in fixes[0].findings}
        assert "blank" in types

    def test_warn_severity_does_not_produce_fix(self):
        # warn-only findings are observability — auto-fix only retries on FAIL.
        det = [_Fake4AFinding("broken", "warn", ["edge_clip"])]
        assert collect_fixes(det, [], SCENES) == []

    def test_unknown_scene_id_dropped(self):
        det = [_Fake4AFinding("ghost", "fail", ["blank"])]
        # ghost isn't in SCENES → dropped (no original_actions to operate on)
        assert collect_fixes(det, [], SCENES) == []


class TestReviseFailedScenes:
    def test_disabled_returns_unchanged(self, monkeypatch):
        monkeypatch.delenv("ENABLE_AUTO_FIX", raising=False)
        script = {"scenes": list(SCENES)}
        fixes = [SceneFix("broken", [{"type": "blank"}], SCENES[1]["actions"])]
        out, ids = revise_failed_scenes(script, fixes)
        assert ids == []
        assert out["scenes"] == list(SCENES)

    def test_enabled_calls_llm_and_applies(self, monkeypatch):
        monkeypatch.setenv("ENABLE_AUTO_FIX", "true")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        new_actions = [
            {"type": "create_node", "id": "n1", "label": "Cast",
             "icon_type": "computer", "position": "center"},
            {"type": "show_text_block", "title": "Broken (fixed)"},
        ]

        def fake_revise(client, model, fix):
            assert fix.scene_id == "broken"
            return new_actions

        monkeypatch.setattr(auto_fix, "_revise_scene_actions", fake_revise)
        monkeypatch.setattr(
            "openai.OpenAI",
            lambda **kwargs: object(),  # client is unused since _revise_scene_actions is faked
        )

        script = {"scenes": [dict(s) for s in SCENES]}
        fixes = [SceneFix("broken", [{"type": "blank"}], SCENES[1]["actions"])]
        out, ids = revise_failed_scenes(script, fixes)
        assert ids == ["broken"]
        assert out["scenes"][1]["actions"] == new_actions
        # Other scenes untouched
        assert out["scenes"][0]["actions"] == SCENES[0]["actions"]
        assert out["scenes"][2]["actions"] == SCENES[2]["actions"]

    def test_revision_failure_keeps_original(self, monkeypatch):
        monkeypatch.setenv("ENABLE_AUTO_FIX", "true")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setattr(auto_fix, "_revise_scene_actions",
                            lambda *a, **k: None)
        monkeypatch.setattr("openai.OpenAI", lambda **kwargs: object())

        script = {"scenes": [dict(s) for s in SCENES]}
        fixes = [SceneFix("broken", [{"type": "blank"}], SCENES[1]["actions"])]
        out, ids = revise_failed_scenes(script, fixes)
        assert ids == []
        assert out["scenes"][1]["actions"] == SCENES[1]["actions"]
