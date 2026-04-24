"""Central rendering engine — stateful scene manager and full-video Manim run."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from manim import FadeOut, VGroup

from models_semantic import EnrichedScene, EnrichedVideoScript

logger = logging.getLogger(__name__)

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
})


class SceneState:
    """Tracks mobjects for cross-action use within a segment.

    Objects are tagged with a *category*:
    - ``"persistent"`` — spatial / topology items that should stay on-screen
      until explicitly removed or the scene ends (nodes, connections, regions).
    - ``"presentation"`` — full-screen slide content (text blocks, tables,
      bullet lists, diagrams).  Auto-cleared before the next presentation
      action so they don't pile up.
    """

    def __init__(self) -> None:
        self.objects: dict[str, Any] = {}
        self._categories: dict[str, str] = {}

    def register(self, obj_id: str, mobject, category: str = "persistent") -> None:
        self.objects[obj_id] = mobject
        self._categories[obj_id] = category

    def get(self, obj_id: str):
        return self.objects.get(obj_id)

    def unregister(self, obj_id: str) -> None:
        self.objects.pop(obj_id, None)
        self._categories.pop(obj_id, None)

    def clear(self) -> None:
        self.objects.clear()
        self._categories.clear()

    # -- category helpers --------------------------------------------------

    def clear_presentation(self, scene) -> None:
        """Fade-out and remove all *presentation* mobjects."""
        pres = [(k, v) for k, v in self.objects.items()
                if self._categories.get(k) == "presentation"]
        if not pres:
            return
        scene.play(*[FadeOut(mob) for _, mob in pres], run_time=0.35)
        for k, _ in pres:
            self.objects.pop(k, None)
            self._categories.pop(k, None)

    def has_persistent(self) -> bool:
        return any(c == "persistent" for c in self._categories.values())

    def persistent_bbox(self) -> tuple[float, float, float, float] | None:
        """Return (left_x, right_x, bottom_y, top_y) of persistent objects."""
        mobs = [v for k, v in self.objects.items()
                if self._categories.get(k) == "persistent"]
        if not mobs:
            return None
        lefts  = [m.get_left()[0]   for m in mobs]
        rights = [m.get_right()[0]  for m in mobs]
        bots   = [m.get_bottom()[1] for m in mobs]
        tops   = [m.get_top()[1]    for m in mobs]
        return min(lefts), max(rights), min(bots), max(tops)


def _avoid_persistent_overlap(state: SceneState, new_ids: set[str]) -> None:
    """Shift newly-added presentation content below persistent objects."""
    bbox = state.persistent_bbox()
    if bbox is None:
        return

    new_mobs = [state.objects[k] for k in new_ids if k in state.objects]
    if not new_mobs:
        return

    group = VGroup(*new_mobs)
    g_top = group.get_top()[1]
    g_bot = group.get_bottom()[1]
    _, _, p_bot, p_top = bbox

    if g_bot > p_top + 0.15 or g_top < p_bot - 0.15:
        return

    target_top = p_bot - 0.45
    shift_y = target_top - g_top
    group.shift([0, shift_y, 0])

    if group.get_bottom()[1] < -3.7:
        available = target_top - (-3.7)
        if available > 0.4 and group.height > available:
            group.scale(available / group.height)
            group.move_to([group.get_center()[0], target_top - group.height / 2, 0])


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
    from rendering_engine.sequence import render_show_sequence_diagram
    from rendering_engine.topology import (
        render_create_connection,
        render_create_node,
        render_create_topology,
        render_remove_element,
        render_update_node,
    )

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
    }

    handler = dispatch.get(action.type)
    if handler is None:
        logger.warning("Unknown action type: %s — skipping", action.type)
        return

    is_pres = action.type in _PRESENTATION_TYPES

    if is_pres:
        state.clear_presentation(scene)

    pre_ids = set(state.objects)
    try:
        handler(scene, state, action)
    except Exception:
        logger.exception("Action '%s' crashed — skipping", action.type)
        return
    new_ids = set(state.objects) - pre_ids

    category = "presentation" if is_pres else "persistent"
    for nid in new_ids:
        state._categories[nid] = category

    if is_pres and new_ids:
        _avoid_persistent_overlap(state, new_ids)


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
        "scenes": [
            {
                "scene_id": s.scene_id,
                "actions": [a.model_dump(by_alias=True) for a in s.actions],
                "audio_duration": s.audio_duration or s.estimated_duration,
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

    env = os.environ.copy()
    env["SEMANTIC_DATA_JSON"] = json_path

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
    return str(out)
