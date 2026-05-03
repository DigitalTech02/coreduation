"""Tests for Track 1 layout primitives: zone constants, helpers, validator."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rendering_engine.styles import (
    CONTENT_ZONE,
    FOOTER_ZONE,
    HEADER_ZONE,
    MIN_FONT_BODY,
    MIN_FONT_LABEL,
    TITLE_ZONE,
    is_in_zone,
    zones_overlap,
)


class TestZoneConstants:
    def test_zones_are_well_ordered(self):
        # Top to bottom: HEADER > TITLE > CONTENT > FOOTER
        assert HEADER_ZONE[0] > TITLE_ZONE[1]
        assert TITLE_ZONE[0] >= CONTENT_ZONE[1]
        assert CONTENT_ZONE[0] > FOOTER_ZONE[1]

    def test_zones_dont_overlap(self):
        for a, b in [
            (HEADER_ZONE, TITLE_ZONE),
            (TITLE_ZONE, CONTENT_ZONE),
            (CONTENT_ZONE, FOOTER_ZONE),
            (HEADER_ZONE, CONTENT_ZONE),
            (HEADER_ZONE, FOOTER_ZONE),
        ]:
            assert not zones_overlap(a, b), f"{a} overlaps {b}"

    def test_min_fonts_meet_youtube_floor(self):
        # 22px floor for body (per CLAUDE.md / video review).
        assert MIN_FONT_BODY >= 22
        assert MIN_FONT_LABEL >= 16


class TestIsInZone:
    def test_inside(self):
        assert is_in_zone(0.0, 1.0, CONTENT_ZONE) is True

    def test_top_escape(self):
        # Y above CONTENT_ZONE top
        assert is_in_zone(2.0, 5.0, CONTENT_ZONE) is False

    def test_bottom_escape(self):
        assert is_in_zone(-5.0, 0.0, CONTENT_ZONE) is False


class TestValidateLayout:
    """validate_layout warns on risky patterns; never raises."""

    def _make_script(self, scene_actions):
        from models_semantic import EnrichedScene, EnrichedVideoScript
        from semantic_validation import parse_actions_from_dicts

        scenes = [
            EnrichedScene(
                scene_id=f"s{i}",
                title=f"Scene {i}",
                type="content",
                narration="x",
                visual_description="vd",
                actions=parse_actions_from_dicts(actions),
                estimated_duration=10.0,
            )
            for i, actions in enumerate(scene_actions)
        ]
        return EnrichedVideoScript(
            topic="t", category="networking", scenes=scenes,
        )

    def test_mixed_slide_and_diagram_warns(self, caplog):
        from semantic_validation import validate_layout
        import logging

        actions = [
            {"type": "create_node", "id": "a", "label": "A", "node_type": "server"},
            {"type": "show_text_block", "title": "Hi", "body": "Body."},
        ]
        script = self._make_script([actions])
        with caplog.at_level(logging.WARNING, logger="semantic_validation"):
            warnings = validate_layout(script)
        assert any("text-through-box" in w for w in warnings)

    def test_oversized_bullet_list_warns(self):
        from semantic_validation import validate_layout

        actions = [{
            "type": "show_bullet_list",
            "title": "Many",
            "items": [f"item {i}" for i in range(10)],
        }]
        script = self._make_script([actions])
        warnings = validate_layout(script)
        assert any("show_bullet_list" in w and "10 items" in w for w in warnings)

    def test_clean_scene_no_warnings(self):
        from semantic_validation import validate_layout

        actions = [{"type": "show_text_block", "title": "T", "body": "Short."}]
        script = self._make_script([actions])
        warnings = validate_layout(script)
        assert warnings == []

    def test_never_raises(self):
        from semantic_validation import validate_layout
        # Empty scenes — should not crash.
        script = self._make_script([])
        validate_layout(script)
