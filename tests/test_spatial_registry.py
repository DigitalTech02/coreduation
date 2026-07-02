"""Tests for the BBox type and SceneState spatial registry."""

import pytest

from rendering_engine.engine import BBox, SceneState


# ---------------------------------------------------------------------------
# Mock mobject — just needs get_left/right/top/bottom for bbox computation
# ---------------------------------------------------------------------------

class MockMobject:
    """Minimal mock that satisfies SceneState._compute_bbox."""

    def __init__(self, left: float, right: float, bottom: float, top: float):
        self._left = left
        self._right = right
        self._bottom = bottom
        self._top = top

    def get_left(self):
        return [self._left, 0, 0]

    def get_right(self):
        return [self._right, 0, 0]

    def get_bottom(self):
        return [0, self._bottom, 0]

    def get_top(self):
        return [0, self._top, 0]


# ---------------------------------------------------------------------------
# BBox tests
# ---------------------------------------------------------------------------

class TestBBox:
    def test_properties(self):
        b = BBox(1.0, 5.0, 2.0, 8.0)
        assert b.width == 4.0
        assert b.height == 6.0
        assert b.center_x == 3.0
        assert b.center_y == 5.0

    def test_overlaps_true(self):
        a = BBox(0, 2, 0, 2)
        b = BBox(1, 3, 1, 3)
        assert a.overlaps(b)
        assert b.overlaps(a)

    def test_overlaps_false(self):
        a = BBox(0, 1, 0, 1)
        b = BBox(2, 3, 2, 3)
        assert not a.overlaps(b)
        assert not b.overlaps(a)

    def test_overlaps_margin(self):
        a = BBox(0, 1, 0, 1)
        b = BBox(1.1, 2, 0, 1)  # 0.1 apart
        assert not a.overlaps(b)
        assert a.overlaps(b, margin=0.2)

    def test_overlaps_edge_touching(self):
        a = BBox(0, 1, 0, 1)
        b = BBox(1, 2, 0, 1)  # sharing edge
        assert a.overlaps(b)

    def test_contains(self):
        outer = BBox(0, 10, 0, 10)
        inner = BBox(2, 4, 2, 4)
        assert outer.contains(inner)
        assert not inner.contains(outer)

    def test_contains_self(self):
        b = BBox(0, 5, 0, 5)
        assert b.contains(b)

    def test_union(self):
        a = BBox(0, 2, 0, 2)
        b = BBox(1, 5, -1, 3)
        u = a.union(b)
        assert u == BBox(0, 5, -1, 3)

    def test_union_commutative(self):
        a = BBox(0, 2, 0, 2)
        b = BBox(3, 5, 3, 5)
        assert a.union(b) == b.union(a)


# ---------------------------------------------------------------------------
# SceneState spatial registry tests
# ---------------------------------------------------------------------------

class TestSceneStateSpatial:
    def test_register_tracks_bounds(self):
        state = SceneState()
        mob = MockMobject(-2, 2, -1, 1)
        state.register("node_a", mob)
        bbox = state.bbox_of("node_a")
        assert bbox is not None
        assert bbox.left == -2
        assert bbox.right == 2
        assert bbox.bottom == -1
        assert bbox.top == 1

    def test_unregister_removes_bounds(self):
        state = SceneState()
        mob = MockMobject(0, 1, 0, 1)
        state.register("node_a", mob)
        state.unregister("node_a")
        assert state.bbox_of("node_a") is None
        assert "node_a" not in state.objects

    def test_clear_removes_all_spatial(self):
        state = SceneState()
        state.register("a", MockMobject(0, 1, 0, 1))
        state.register("b", MockMobject(2, 3, 2, 3))
        state.clear()
        assert len(state._bounds) == 0
        assert len(state._parents) == 0
        assert len(state._children) == 0

    def test_visible_bounds_excludes_hidden(self):
        state = SceneState()
        state.register("a", MockMobject(0, 1, 0, 1))
        state.register("b", MockMobject(2, 3, 2, 3))
        state._hidden.add("a")
        visible = state.visible_bounds()
        ids = [oid for oid, _ in visible]
        assert "a" not in ids
        assert "b" in ids

    def test_visible_bounds_excludes_internal(self):
        state = SceneState()
        state.register("__header", MockMobject(0, 1, 3, 4))
        state.register("node_a", MockMobject(0, 1, 0, 1))
        visible = state.visible_bounds()
        ids = [oid for oid, _ in visible]
        assert "__header" not in ids
        assert "node_a" in ids

    def test_visible_bounds_category_filter(self):
        state = SceneState()
        state.register("node_a", MockMobject(0, 1, 0, 1), category="persistent")
        state.register("text_block", MockMobject(0, 1, -2, -1), category="presentation")
        persistent = state.visible_bounds(category="persistent")
        assert len(persistent) == 1
        assert persistent[0][0] == "node_a"

    def test_overlaps_any(self):
        state = SceneState()
        state.register("a", MockMobject(0, 2, 0, 2))
        state.register("b", MockMobject(5, 7, 5, 7))
        # Query that overlaps 'a' but not 'b'
        hits = state.overlaps_any(BBox(1, 3, 1, 3))
        assert "a" in hits
        assert "b" not in hits

    def test_overlaps_any_with_exclude(self):
        state = SceneState()
        state.register("a", MockMobject(0, 2, 0, 2))
        hits = state.overlaps_any(BBox(0, 2, 0, 2), exclude={"a"})
        assert len(hits) == 0

    def test_objects_in_rect(self):
        state = SceneState()
        state.register("inner", MockMobject(1, 3, 1, 3))
        state.register("outer", MockMobject(-5, 5, -5, 5))
        contained = state.objects_in_rect(BBox(0, 4, 0, 4))
        assert "inner" in contained
        assert "outer" not in contained

    def test_find_vacant_rect_empty(self):
        state = SceneState()
        result = state.find_vacant_rect(2.0, 1.0)
        assert result is not None
        cx, cy = result
        assert isinstance(cx, float)
        assert isinstance(cy, float)

    def test_find_vacant_rect_avoids_obstacle(self):
        state = SceneState()
        # Place a wide obstacle in the center
        state.register("obstacle", MockMobject(-5, 5, -0.5, 0.5))
        result = state.find_vacant_rect(3.0, 1.0)
        assert result is not None
        _, cy = result
        # Should be above or below the obstacle, not overlapping
        assert cy > 0.5 or cy < -0.5

    def test_find_vacant_y(self):
        state = SceneState()
        state.register("top_obj", MockMobject(-3, 3, 1.5, 2.5))
        y = state.find_vacant_y(height=0.8)
        # Should find space below the object
        assert y < 1.5

    def test_persistent_bbox_uses_cached_bounds(self):
        state = SceneState()
        state.register("a", MockMobject(-2, 0, -1, 0), category="persistent")
        state.register("b", MockMobject(1, 3, 0, 2), category="persistent")
        bbox = state.persistent_bbox()
        assert bbox is not None
        left, right, bottom, top = bbox
        assert left == -2
        assert right == 3
        assert bottom == -1
        assert top == 2

    def test_persistent_bbox_excludes_presentation(self):
        state = SceneState()
        state.register("node", MockMobject(0, 1, 0, 1), category="persistent")
        state.register("text", MockMobject(-5, 5, -3, 3), category="presentation")
        left, right, bottom, top = state.persistent_bbox()
        assert left == 0
        assert right == 1


# ---------------------------------------------------------------------------
# Parent/child containment tests
# ---------------------------------------------------------------------------

class TestContainment:
    def test_parent_child_registration(self):
        state = SceneState()
        state.register("region_us", MockMobject(-4, -1, -2, 2))
        state.register("service_a", MockMobject(-3, -2, -1, 0),
                        parent_id="region_us")
        assert state.children_of("region_us") == ["service_a"]

    def test_multiple_children(self):
        state = SceneState()
        state.register("region_us", MockMobject(-4, -1, -2, 2))
        state.register("svc_a", MockMobject(-3, -2, 0, 1), parent_id="region_us")
        state.register("svc_b", MockMobject(-3, -2, -1, 0), parent_id="region_us")
        children = state.children_of("region_us")
        assert "svc_a" in children
        assert "svc_b" in children
        assert len(children) == 2

    def test_unregister_child_cleans_parent(self):
        state = SceneState()
        state.register("region", MockMobject(0, 5, 0, 5))
        state.register("svc", MockMobject(1, 2, 1, 2), parent_id="region")
        state.unregister("svc")
        assert state.children_of("region") == []
        assert "svc" not in state._parents

    def test_unregister_parent_cleans_children_refs(self):
        state = SceneState()
        state.register("region", MockMobject(0, 5, 0, 5))
        state.register("svc", MockMobject(1, 2, 1, 2), parent_id="region")
        state.unregister("region")
        assert "svc" not in state._parents

    def test_children_of_nonexistent(self):
        state = SceneState()
        assert state.children_of("nonexistent") == []


# ---------------------------------------------------------------------------
# Edge cases for vacant-rect search and persistence
# ---------------------------------------------------------------------------

class TestVacantSearchEdges:
    def test_find_vacant_rect_skips_too_small_gaps(self):
        """Request a rect taller than any gap between obstacles → fall back
        cleanly (return None or the largest-gap fallback, but never crash)."""
        state = SceneState()
        # Blanket the safe area (-2.5..2.9) with stripes leaving only thin gaps
        state.register("top", MockMobject(-6.5, 6.5, 2.5, 2.9))
        state.register("upper", MockMobject(-6.5, 6.5, 1.0, 1.5))
        state.register("mid", MockMobject(-6.5, 6.5, -0.5, 0.0))
        state.register("low", MockMobject(-6.5, 6.5, -2.0, -1.5))
        # Largest gap is ~1.5 units. Request 3.0 — should not find one.
        result = state.find_vacant_rect(2.0, 3.0)
        assert result is None

    def test_find_vacant_y_falls_back_to_center(self):
        """When fully blocked, find_vacant_y returns the safe-area center
        (the documented fallback) rather than raising."""
        state = SceneState()
        # Block the entire safe area top to bottom
        state.register("blocker", MockMobject(-6.5, 6.5, -2.5, 2.9))
        y = state.find_vacant_y(height=3.0)
        # Should be a float (the fallback midpoint)
        assert isinstance(y, float)

    def test_persistent_bbox_none_when_empty(self):
        state = SceneState()
        assert state.persistent_bbox() is None

    def test_persistent_bbox_none_when_only_presentation(self):
        state = SceneState()
        state.register("text", MockMobject(0, 5, 0, 5), category="presentation")
        assert state.persistent_bbox() is None

    def test_overlaps_any_margin_inflates_query(self):
        """A margin parameter inflates the query box — useful for collision
        avoidance with breathing room."""
        from rendering_engine.engine import BBox
        state = SceneState()
        state.register("a", MockMobject(0, 1, 0, 1))
        # Query 0.2 units away — no overlap at margin=0
        query = BBox(1.2, 2.0, 0, 1)
        assert "a" not in state.overlaps_any(query)
        # With margin=0.3 the gap closes
        assert "a" in state.overlaps_any(query, margin=0.3)


class TestDiagramZones:
    """The DIAGRAM_ZONE_TOP / _BOTTOM constants drive avoid_overlap fallbacks
    in engine.py. They're load-bearing — accidentally narrowing them would
    break overlay placement on the active branch."""

    def test_zones_are_inside_safe_area(self):
        from rendering_engine.styles import (
            DIAGRAM_ZONE_BOTTOM, DIAGRAM_ZONE_TOP,
            SAFE_AREA_BOTTOM, SAFE_AREA_TOP,
        )
        assert SAFE_AREA_BOTTOM < DIAGRAM_ZONE_BOTTOM < DIAGRAM_ZONE_TOP < SAFE_AREA_TOP

    def test_zones_leave_room_for_overlays(self):
        """avoid_overlap requires top/bottom reserved bands of at least 0.3
        units for the scaled-down overlay path to engage."""
        from rendering_engine.styles import (
            DIAGRAM_ZONE_BOTTOM, DIAGRAM_ZONE_TOP,
            SAFE_AREA_BOTTOM, SAFE_AREA_TOP,
        )
        assert SAFE_AREA_TOP - DIAGRAM_ZONE_TOP >= 0.3
        assert DIAGRAM_ZONE_BOTTOM - SAFE_AREA_BOTTOM >= 0.3
