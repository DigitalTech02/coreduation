"""Central rendering engine — stateful scene manager and full-video Manim run."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, NamedTuple

from manim import FadeOut, VGroup

from models_semantic import EnrichedScene, EnrichedVideoScript

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Spatial bounding box
# ---------------------------------------------------------------------------

class BBox(NamedTuple):
    """Axis-aligned bounding box: left, right, bottom, top."""

    left: float
    right: float
    bottom: float
    top: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.top - self.bottom

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2

    @property
    def center_y(self) -> float:
        return (self.bottom + self.top) / 2

    def overlaps(self, other: BBox, margin: float = 0.0) -> bool:
        """True if this bbox overlaps *other* (with optional margin)."""
        return not (
            self.right + margin < other.left
            or other.right + margin < self.left
            or self.top + margin < other.bottom
            or other.top + margin < self.bottom
        )

    def contains(self, other: BBox) -> bool:
        return (
            self.left <= other.left
            and self.right >= other.right
            and self.bottom <= other.bottom
            and self.top >= other.top
        )

    def union(self, other: BBox) -> BBox:
        return BBox(
            min(self.left, other.left),
            max(self.right, other.right),
            min(self.bottom, other.bottom),
            max(self.top, other.top),
        )

OUTPUT_DIR = Path("output/video")
MANIM_QUALITY = os.getenv("MANIM_QUALITY", "m")

RUNNER = Path(__file__).resolve().parent / "full_video_runner.py"
RUNNER_CLASS = "FullSemanticVideo"

# Actions that produce full-screen "slide" content — only one should be
# visible at a time.  Before rendering a new presentation action the engine
# auto-clears any previous presentation mobjects.
_PRESENTATION_TYPES = frozenset({
    "show_text_block",
    "show_bullet_list",
    "show_code_block",
    "show_comparison",
    "show_table",
    "show_layer_stack",
    "show_header_breakdown",
    "show_math",
    "show_sequence_diagram",
    "show_image",
    "show_chart",
})

# Overlay actions that should be categorised as "presentation" (cleaned up
# at scene end or when the next _PRESENTATION_TYPE fires) but should NOT
# themselves trigger clear_presentation — they're overlays on existing content.
_SOFT_PRESENTATION_TYPES = frozenset({
    "emphasize_text",
})


class SceneState:
    """Tracks mobjects for cross-action use within a segment.

    Objects are tagged with a *category*:
    - ``"persistent"`` — spatial / topology items that should stay on-screen
      until explicitly removed or the scene ends (nodes, connections, regions).
    - ``"presentation"`` — full-screen slide content (text blocks, tables,
      bullet lists, diagrams).  Auto-cleared before the next presentation
      action so they don't pile up.

    Includes a **spatial registry** that caches bounding boxes and supports
    overlap queries, vacant-space searches, and parent/child containment.
    """

    def __init__(self) -> None:
        self.objects: dict[str, Any] = {}
        self._categories: dict[str, str] = {}
        self._hidden: set[str] = set()
        # --- Spatial registry ---
        self._bounds: dict[str, BBox] = {}
        self._parents: dict[str, str] = {}        # child_id → parent_id
        self._children: dict[str, list[str]] = {}  # parent_id → [child_ids]

    # -- registration ------------------------------------------------------

    def register(self, obj_id: str, mobject, category: str = "persistent",
                 *, parent_id: str | None = None) -> None:
        self.objects[obj_id] = mobject
        self._categories[obj_id] = category
        self._hidden.discard(obj_id)
        # Spatial: cache bbox
        self._bounds[obj_id] = self._compute_bbox(mobject)
        # Containment hierarchy
        if parent_id:
            self._parents[obj_id] = parent_id
            self._children.setdefault(parent_id, []).append(obj_id)

    def get(self, obj_id: str):
        return self.objects.get(obj_id)

    def is_hidden(self, obj_id: str) -> bool:
        return obj_id in self._hidden

    def unregister(self, obj_id: str) -> None:
        self.objects.pop(obj_id, None)
        self._categories.pop(obj_id, None)
        self._hidden.discard(obj_id)
        self._bounds.pop(obj_id, None)
        # Clean parent/child links
        parent = self._parents.pop(obj_id, None)
        if parent and parent in self._children:
            children = self._children[parent]
            if obj_id in children:
                children.remove(obj_id)
        for child_id in self._children.pop(obj_id, []):
            self._parents.pop(child_id, None)

    def clear(self) -> None:
        self.objects.clear()
        self._categories.clear()
        self._hidden.clear()
        self._bounds.clear()
        self._parents.clear()
        self._children.clear()

    # -- spatial helpers ---------------------------------------------------

    @staticmethod
    def _compute_bbox(mobject) -> BBox:
        """Extract an axis-aligned bounding box from a Manim mobject."""
        return BBox(
            left=float(mobject.get_left()[0]),
            right=float(mobject.get_right()[0]),
            bottom=float(mobject.get_bottom()[1]),
            top=float(mobject.get_top()[1]),
        )

    def refresh_bounds(self, obj_id: str) -> None:
        """Re-compute cached bbox after an object moves/resizes."""
        mob = self.objects.get(obj_id)
        if mob is not None:
            self._bounds[obj_id] = self._compute_bbox(mob)

    def refresh_all_bounds(self) -> None:
        """Re-compute all cached bboxes (call after batch moves)."""
        for obj_id, mob in self.objects.items():
            self._bounds[obj_id] = self._compute_bbox(mob)

    def bbox_of(self, obj_id: str) -> BBox | None:
        """Return cached bbox for a single object."""
        return self._bounds.get(obj_id)

    def visible_bounds(self, category: str | None = None,
                       exclude_internal: bool = True) -> list[tuple[str, BBox]]:
        """Return (id, bbox) pairs for all visible (non-hidden) objects."""
        results = []
        for obj_id, bbox in self._bounds.items():
            if obj_id in self._hidden:
                continue
            if exclude_internal and obj_id.startswith("__"):
                continue
            if category and self._categories.get(obj_id) != category:
                continue
            results.append((obj_id, bbox))
        return results

    def overlaps_any(self, bbox: BBox, margin: float = 0.15,
                     exclude: set[str] | None = None) -> list[str]:
        """Return IDs of visible objects whose bbox overlaps the given bbox."""
        exclude = exclude or set()
        return [
            obj_id for obj_id, obj_bbox in self.visible_bounds()
            if obj_id not in exclude and bbox.overlaps(obj_bbox, margin)
        ]

    def objects_in_rect(self, bbox: BBox) -> list[str]:
        """Return IDs of visible objects fully contained within bbox."""
        return [
            obj_id for obj_id, obj_bbox in self.visible_bounds()
            if bbox.contains(obj_bbox)
        ]

    def children_of(self, parent_id: str) -> list[str]:
        """Return child object IDs contained by parent_id."""
        return list(self._children.get(parent_id, []))

    def find_vacant_rect(self, width: float, height: float) -> tuple[float, float] | None:
        """Find a (center_x, center_y) for a rect of given size with no overlap.

        Scans vertical gaps between occupied bands within the safe area.
        Returns None if no space is available.
        """
        from rendering_engine.styles import (
            SAFE_AREA_BOTTOM, SAFE_AREA_LEFT, SAFE_AREA_RIGHT, SAFE_AREA_TOP,
        )

        occupied = [b for _, b in self.visible_bounds()]
        safe = BBox(SAFE_AREA_LEFT, SAFE_AREA_RIGHT, SAFE_AREA_BOTTOM, SAFE_AREA_TOP)

        if not occupied:
            return (safe.center_x, safe.center_y)

        # Merge overlapping vertical bands
        bands = sorted([(b.bottom, b.top) for b in occupied], key=lambda x: x[0])
        merged = [list(bands[0])]
        for bot, top in bands[1:]:
            if bot <= merged[-1][1] + 0.05:
                merged[-1][1] = max(merged[-1][1], top)
            else:
                merged.append([bot, top])

        # Collect vertical gaps within safe area
        candidates: list[tuple[float, float]] = []
        gap_bot = safe.bottom
        for m_bot, m_top in merged:
            if m_bot - gap_bot >= height:
                candidates.append((gap_bot, m_bot))
            gap_bot = m_top
        if safe.top - gap_bot >= height:
            candidates.append((gap_bot, safe.top))

        if not candidates:
            return None

        # Pick largest gap
        candidates.sort(key=lambda g: g[1] - g[0], reverse=True)
        best_bot, best_top = candidates[0]
        cy = (best_bot + best_top) / 2
        cx = safe.center_x

        # Verify no overlap, try horizontal shifts if needed
        for dx in [0, -1.5, 1.5, -3.0, 3.0]:
            test_cx = cx + dx
            if test_cx - width / 2 < safe.left or test_cx + width / 2 > safe.right:
                continue
            test = BBox(test_cx - width / 2, test_cx + width / 2,
                        cy - height / 2, cy + height / 2)
            if not self.overlaps_any(test):
                return (test_cx, cy)

        # Fallback: return center of best gap even with overlap
        return (cx, cy)

    def find_vacant_y(self, height: float = 1.5) -> float:
        """Find the best Y center for an overlay of given height.

        Replacement for the old module-level ``_find_vacant_y()``.
        """
        result = self.find_vacant_rect(width=10.0, height=height)
        if result is not None:
            return result[1]
        from rendering_engine.styles import SAFE_AREA_BOTTOM, SAFE_AREA_TOP
        return (SAFE_AREA_TOP + SAFE_AREA_BOTTOM) / 2

    # -- visibility helpers ------------------------------------------------

    def hide_persistent(self, scene) -> None:
        """Fade persistent objects to invisible (keep in state for later restore)."""
        to_hide = [
            (k, v) for k, v in self.objects.items()
            if self._categories.get(k) == "persistent"
            and k not in self._hidden
            and not k.startswith("__")
        ]
        if not to_hide:
            return
        scene.play(
            *[mob.animate.set_opacity(0) for _, mob in to_hide],
            run_time=0.3,
        )
        for k, _ in to_hide:
            self._hidden.add(k)

    def restore_persistent(self, scene) -> None:
        """Restore hidden persistent objects to full visibility."""
        to_show = [
            (k, self.objects[k]) for k in list(self._hidden)
            if k in self.objects
        ]
        if not to_show:
            return
        scene.play(
            *[mob.animate.set_opacity(1) for _, mob in to_show],
            run_time=0.3,
        )
        self._hidden.clear()

    def find_largest_vacant_region(
        self, min_width: float = 2.0, min_height: float = 1.0,
    ) -> BBox | None:
        """Return the biggest vacant axis-aligned rectangle in the safe area.

        Tries four candidate regions: above all occupied content, below it,
        and the left/right strips beside it. Returns the BBox with the
        largest area that meets the minimum dimensions, or None if no
        region qualifies. Callers then scale their content to fit and
        center it inside.
        """
        from rendering_engine.styles import (
            SAFE_AREA_BOTTOM, SAFE_AREA_LEFT, SAFE_AREA_RIGHT, SAFE_AREA_TOP,
        )

        occupied = [b for _, b in self.visible_bounds()]
        safe = BBox(SAFE_AREA_LEFT, SAFE_AREA_RIGHT, SAFE_AREA_BOTTOM, SAFE_AREA_TOP)
        if not occupied:
            return safe

        # Union extents of all visible content.
        u_left = min(b.left for b in occupied)
        u_right = max(b.right for b in occupied)
        u_bottom = min(b.bottom for b in occupied)
        u_top = max(b.top for b in occupied)

        margin = 0.25
        candidates: list[BBox] = []

        # ABOVE the union
        if safe.top - (u_top + margin) >= min_height:
            candidates.append(BBox(safe.left, safe.right, u_top + margin, safe.top))
        # BELOW the union
        if (u_bottom - margin) - safe.bottom >= min_height:
            candidates.append(BBox(safe.left, safe.right, safe.bottom, u_bottom - margin))
        # LEFT strip (full height, left of union)
        if (u_left - margin) - safe.left >= min_width:
            candidates.append(BBox(safe.left, u_left - margin, safe.bottom, safe.top))
        # RIGHT strip
        if safe.right - (u_right + margin) >= min_width:
            candidates.append(BBox(u_right + margin, safe.right, safe.bottom, safe.top))

        if not candidates:
            return None
        # Largest area wins
        return max(candidates,
                   key=lambda b: (b.right - b.left) * (b.top - b.bottom))

    # -- category helpers --------------------------------------------------

    def clear_presentation(self, scene) -> None:
        """Fade-out and remove all *presentation* mobjects."""
        pres = [(k, v) for k, v in self.objects.items()
                if self._categories.get(k) == "presentation"]
        if not pres:
            return
        scene.play(*[FadeOut(mob) for _, mob in pres], run_time=0.35)
        for k, _ in pres:
            self.unregister(k)

    def has_persistent(self) -> bool:
        return any(
            c == "persistent" and k not in self._hidden
            for k, c in self._categories.items()
        )

    def persistent_bbox(self) -> tuple[float, float, float, float] | None:
        """Return (left_x, right_x, bottom_y, top_y) of visible persistent objects."""
        bboxes = [b for _, b in self.visible_bounds(category="persistent")]
        if not bboxes:
            return None
        result = bboxes[0]
        for b in bboxes[1:]:
            result = result.union(b)
        return result.left, result.right, result.bottom, result.top

    # -- overlap avoidance -------------------------------------------------

    def avoid_overlap(self, new_ids: set[str]) -> None:
        """Shift newly-added presentation content to avoid ALL visible objects.

        Strategy (in order):
        1. Full-size ``find_vacant_rect`` (top / bottom / between bands)
        2. Scale to 70% and retry ``find_vacant_rect``
        3. Try dedicated top reserved zone (above ``DIAGRAM_ZONE_TOP``) with scaling
        4. Try dedicated bottom reserved zone (below ``DIAGRAM_ZONE_BOTTOM``) with scaling
        5. Final fallback: shift below lowest persistent object & scale
        """
        from rendering_engine.styles import (
            DIAGRAM_ZONE_BOTTOM,
            DIAGRAM_ZONE_TOP,
            SAFE_AREA_BOTTOM,
            SAFE_AREA_LEFT,
            SAFE_AREA_RIGHT,
            SAFE_AREA_TOP,
        )

        new_mobs = [self.objects[k] for k in new_ids if k in self.objects]
        if not new_mobs:
            return

        group = VGroup(*new_mobs)
        g_top = group.get_top()[1]

        # Clamp below safe area top (topic header zone)
        if g_top > SAFE_AREA_TOP:
            group.shift([0, SAFE_AREA_TOP - g_top, 0])
            g_top = group.get_top()[1]

        # -- helper: check overlap with existing objects -------------------
        def _overlaps() -> list[str]:
            gb = BBox(
                float(group.get_left()[0]), float(group.get_right()[0]),
                float(group.get_bottom()[1]), float(group.get_top()[1]),
            )
            return [
                oid for oid, bbox in self.visible_bounds()
                if gb.overlaps(bbox, margin=0.15) and oid not in new_ids
            ]

        hits = _overlaps()
        if not hits:
            for nid in new_ids:
                self.refresh_bounds(nid)
            return

        # --- 1. Full-size vacant rect search ------------------------------
        vacant = self.find_vacant_rect(group.width + 0.3, group.height + 0.3)
        if vacant is not None:
            group.move_to([vacant[0], vacant[1], 0])
            if not _overlaps():
                self._clamp_and_finish(group, new_ids, SAFE_AREA_TOP, SAFE_AREA_BOTTOM)
                return

        # --- 2. Scale to 70% and retry -----------------------------------
        original_height = group.height
        group.scale(0.7)
        vacant = self.find_vacant_rect(group.width + 0.3, group.height + 0.3)
        if vacant is not None:
            group.move_to([vacant[0], vacant[1], 0])
            if not _overlaps():
                self._clamp_and_finish(group, new_ids, SAFE_AREA_TOP, SAFE_AREA_BOTTOM)
                return
        # Restore scale for zone attempts
        group.scale(1.0 / 0.7)

        # --- 3. Try top reserved zone (above diagram, below header) ------
        top_zone_h = SAFE_AREA_TOP - DIAGRAM_ZONE_TOP  # ~0.8 units
        if top_zone_h > 0.3:
            scale = min(1.0, top_zone_h / group.height)
            if scale >= 0.35:
                group.scale(scale)
                zone_cy = (DIAGRAM_ZONE_TOP + SAFE_AREA_TOP) / 2
                group.move_to([0, zone_cy, 0])
                if not _overlaps():
                    self._clamp_and_finish(group, new_ids, SAFE_AREA_TOP, SAFE_AREA_BOTTOM)
                    return
                group.scale(1.0 / scale)

        # --- 4. Try bottom reserved zone (below diagram, above subtitle) -
        bot_zone_h = DIAGRAM_ZONE_BOTTOM - SAFE_AREA_BOTTOM  # ~0.8 units
        if bot_zone_h > 0.3:
            scale = min(1.0, bot_zone_h / group.height)
            if scale >= 0.35:
                group.scale(scale)
                zone_cy = (SAFE_AREA_BOTTOM + DIAGRAM_ZONE_BOTTOM) / 2
                group.move_to([0, zone_cy, 0])
                if not _overlaps():
                    self._clamp_and_finish(group, new_ids, SAFE_AREA_TOP, SAFE_AREA_BOTTOM)
                    return
                group.scale(1.0 / scale)

        # --- 5. Final fallback: shift below lowest persistent & scale -----
        hit_bounds = [self._bounds[pid] for pid in hits if pid in self._bounds]
        if hit_bounds:
            p_bot = min(b.bottom for b in hit_bounds)
            target_top = p_bot - 0.35
            group.shift([0, target_top - group.get_top()[1], 0])

            if group.get_bottom()[1] < SAFE_AREA_BOTTOM:
                available = target_top - SAFE_AREA_BOTTOM
                if available > 0.3 and group.height > available:
                    group.scale(available / group.height)
                    group.move_to([group.get_center()[0],
                                   target_top - group.height / 2, 0])

        self._clamp_and_finish(group, new_ids, SAFE_AREA_TOP, SAFE_AREA_BOTTOM)

    def _clamp_and_finish(self, group, new_ids: set[str],
                          sa_top: float, sa_bot: float) -> None:
        """Clamp group to safe area and refresh cached bounds."""
        if group.get_top()[1] > sa_top:
            group.shift([0, sa_top - group.get_top()[1], 0])
        if group.get_bottom()[1] < sa_bot:
            group.shift([0, sa_bot - group.get_bottom()[1], 0])
        for nid in new_ids:
            self.refresh_bounds(nid)


def _dispatch_action(scene, state: SceneState, action) -> None:
    """Route a single VisualAction to its renderer function."""
    from rendering_engine.cloud import (
        render_create_cloud_region,
        render_create_cloud_service,
        render_show_data_flow,
    )
    from rendering_engine.data_display import (
        render_show_header_breakdown,
        render_show_layer_stack,
        render_show_math,
        render_show_table,
    )
    from rendering_engine.packets import render_send_broadcast, render_send_packet
    from rendering_engine.presentation import (
        render_show_bullet_list,
        render_show_code_block,
        render_show_comparison,
        render_show_text_block,
    )
    from rendering_engine.retention import (
        render_add_callout,
        render_dim_except,
        render_emphasize_text,
        render_focus_camera,
        render_pulse_element,
        render_reset_camera,
        render_restore_opacity,
        render_scene_transition,
        render_shake_element,
        render_show_progress,
        render_update_progress,
    )
    from rendering_engine.sequence import render_show_sequence_diagram
    from rendering_engine.topology import (
        render_create_connection,
        render_create_node,
        render_create_topology,
        render_remove_element,
        render_update_node,
    )
    from rendering_engine.broll import render_show_image
    from rendering_engine.effects import (
        render_flash_cut,
        render_glitch_transition,
        render_zoom_punch,
    )
    from rendering_engine.charts import render_show_chart

    dispatch = {
        "create_node": render_create_node,
        "create_connection": render_create_connection,
        "update_node": render_update_node,
        "remove_element": render_remove_element,
        "create_topology": render_create_topology,
        "send_packet": render_send_packet,
        "send_broadcast": render_send_broadcast,
        "show_sequence_diagram": render_show_sequence_diagram,
        "show_layer_stack": render_show_layer_stack,
        "show_header_breakdown": render_show_header_breakdown,
        "show_table": render_show_table,
        "show_math": render_show_math,
        "show_text_block": render_show_text_block,
        "show_code_block": render_show_code_block,
        "show_comparison": render_show_comparison,
        "show_bullet_list": render_show_bullet_list,
        "create_cloud_region": render_create_cloud_region,
        "create_cloud_service": render_create_cloud_service,
        "show_data_flow": render_show_data_flow,
        "pulse_element": render_pulse_element,
        "focus_camera": render_focus_camera,
        "reset_camera": render_reset_camera,
        "show_progress": render_show_progress,
        "update_progress": render_update_progress,
        "emphasize_text": render_emphasize_text,
        "shake_element": render_shake_element,
        "dim_except": render_dim_except,
        "restore_opacity": render_restore_opacity,
        "add_callout": render_add_callout,
        "scene_transition": render_scene_transition,
        "show_image": render_show_image,
        "flash_cut": render_flash_cut,
        "zoom_punch": render_zoom_punch,
        "glitch_transition": render_glitch_transition,
        "show_chart": render_show_chart,
    }

    handler = dispatch.get(action.type)
    if handler is None:
        logger.warning("Unknown action type: %s — skipping", action.type)
        return

    is_pres = action.type in _PRESENTATION_TYPES
    is_soft_pres = action.type in _SOFT_PRESENTATION_TYPES

    if is_pres:
        state.clear_presentation(scene)

    pre_ids = set(state.objects)
    try:
        handler(scene, state, action)
    except Exception:
        logger.exception("Action '%s' crashed — skipping", action.type)
        return
    new_ids = set(state.objects) - pre_ids

    category = "presentation" if (is_pres or is_soft_pres) else "persistent"
    for nid in new_ids:
        state._categories[nid] = category

    if (is_pres or is_soft_pres) and new_ids:
        state.avoid_overlap(new_ids)


def _rebuild_action(action_dict: dict):
    """Reconstruct a typed VisualAction from a raw dict."""
    from models_semantic import VisualAction
    from pydantic import TypeAdapter

    adapter = TypeAdapter(VisualAction)
    try:
        return adapter.validate_python(action_dict)
    except Exception as e:
        logger.warning("Failed to rebuild action %s: %s", action_dict.get("type"), e)
        return None


def _serialize_script(script: EnrichedVideoScript) -> dict:
    return {
        "topic": script.topic,
        "title_card_subtitle": script.title_card_subtitle or "",
        "category": script.category or "",
        "video_title": script.video_title or "",
        "video_hook": script.video_hook or "",
        "emotional_tone": script.emotional_tone or "",
        "scenes": [
            {
                "scene_id": s.scene_id,
                "title": s.title,
                "narration": s.narration,
                "actions": [a.model_dump(by_alias=True) for a in s.actions],
                "audio_duration": s.audio_duration or s.estimated_duration,
                "audio_path": s.audio_path,
                # Critical for subtitle pacing: pause_after extends the
                # subtitle window past raw audio, whisper_words drives
                # exact subtitle-to-narration alignment.
                "pause_after": s.pause_after or 0.0,
                "whisper_words": list(getattr(s, "whisper_words", None) or []),
            }
            for s in script.scenes
        ],
    }


def render_full_semantic_video(
    script: EnrichedVideoScript,
    output_dir: Path | str | None = None,
) -> str | None:
    """Single Manim pass: ``FullSemanticVideo`` in ``full_video_runner.py``.

    Returns path to the rendered silent ``.mp4``, or ``None`` on failure.
    """
    dest_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    data = _serialize_script(script)
    fd, json_path = tempfile.mkstemp(suffix=".json", prefix="semantic_data_")
    os.close(fd)
    Path(json_path).write_text(json.dumps(data), encoding="utf-8")

    work_dir = Path(tempfile.mkdtemp(prefix="semantic_render_"))
    media_dir = work_dir / "media"
    manifest_path = work_dir / "scene_timings.json"

    env = os.environ.copy()
    env["SEMANTIC_DATA_JSON"] = json_path
    env["SEMANTIC_TIMING_MANIFEST"] = str(manifest_path)

    cmd = [
        "python",
        "-m",
        "manim",
        "render",
        "-q",
        MANIM_QUALITY,
        "--media_dir",
        str(media_dir),
        "--disable_caching",
        str(RUNNER),
        RUNNER_CLASS,
    ]

    logger.info("Full semantic render: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,
            encoding="utf-8",
            errors="replace",
            env=env,
            cwd=str(Path.cwd()),
        )
    finally:
        Path(json_path).unlink(missing_ok=True)

    if result.returncode != 0:
        err = (result.stderr or "") + (result.stdout or "")
        logger.error("Full semantic render failed:\n%s", err[-6000:])
        return None

    for mp4 in media_dir.rglob(f"{RUNNER_CLASS}.mp4"):
        if "partial_movie_files" not in str(mp4):
            rendered = mp4
            break
    else:
        logger.error("Render finished but %s.mp4 not found under %s", RUNNER_CLASS, media_dir)
        return None

    out = dest_dir / "full_semantic_silent.mp4"
    out.unlink(missing_ok=True)
    shutil.move(str(rendered), str(out))
    logger.info("Silent full video: %s", out)

    # Copy the timing manifest next to the silent video so the audio mux
    # can rebuild narration with per-scene boundaries that match the
    # actual rendered timeline (eliminates accumulated AV drift).
    if manifest_path.exists():
        try:
            shutil.copy(str(manifest_path), str(dest_dir / "scene_timings.json"))
            logger.info("Scene timing manifest: %s", dest_dir / "scene_timings.json")
        except Exception as e:
            logger.warning("Could not copy scene timing manifest: %s", e)

    return str(out)
