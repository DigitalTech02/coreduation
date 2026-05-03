"""Validate semantic scripts before rendering — reference checks in action order.

Duplicate **implicit** connection ids (same endpoints, no explicit ``id``) are
allocated as ``conn_a_b``, ``conn_a_b__1``, … in :func:`_reserve_implicit_connection_id`
(rendering uses the same scheme in ``topology._unique_connection_id``).

Duplicate **explicit** ids should be repaired by :func:`semantic_repair.repair_duplicate_ids`
before this validator runs.

Retention actions (``pulse_element``, ``shake_element``, ``focus_camera``,
``add_callout``, ``dim_except``) log warnings for unknown target IDs instead
of failing hard, because the renderers already handle missing targets gracefully
and the LLM sometimes references presentation objects (tables, text blocks) that
don't have stable user-assigned IDs.
"""

from __future__ import annotations

import logging

from pydantic import TypeAdapter

from models_semantic import EnrichedVideoScript, VisualAction

logger = logging.getLogger(__name__)


def _reserve_implicit_connection_id(from_node: str, to_node: str, known: set[str]) -> str:
    """Auto id ``conn_{a}_{b}``, ``conn_{a}_{b}__1``, … so duplicate edges validate."""
    base = f"conn_{from_node}_{to_node}"
    cid = base
    suffix = 0
    while cid in known:
        suffix += 1
        cid = f"{base}__{suffix}"
    known.add(cid)
    return cid


# Retention actions reference target_id(s) that may point at presentation objects
# (tables, code blocks, etc.) whose internal keys are auto-generated and unknown
# to the LLM.  We warn instead of failing so the video still renders — the
# renderers already skip gracefully when a target is missing.
_SOFT_REF_TYPES = frozenset({
    "pulse_element", "shake_element", "focus_camera", "add_callout", "dim_except",
})


def validate_semantic_script(script: EnrichedVideoScript) -> list[str]:
    """Process every action in script order. Raises ValueError if core references break.

    Sequence diagram participants are names, not topology node IDs: we do not
    require them to appear in ``known``.

    Retention actions (pulse, shake, focus, callout, dim) that reference unknown
    IDs emit warnings but do **not** cause validation failure — the renderers
    handle missing targets gracefully at render time.
    """
    known: set[str] = set()
    issues: list[str] = []
    warnings: list[str] = []

    def add_id(obj_id: str, scene_id: str, ctx: str) -> None:
        if obj_id in known:
            issues.append(f"scene {scene_id} {ctx}: duplicate id {obj_id!r}")
        known.add(obj_id)

    def need(ref: str, scene_id: str, ctx: str) -> None:
        if ref and ref not in known:
            issues.append(f"scene {scene_id} {ctx}: unknown id {ref!r}")

    def soft_need(ref: str, scene_id: str, ctx: str) -> None:
        """Warn (don't fail) for retention action targets that may be auto-keyed."""
        if ref and ref not in known:
            warnings.append(f"scene {scene_id} {ctx}: unknown id {ref!r} (will skip at render)")

    for scene in script.scenes:
        sid = scene.scene_id
        for action in scene.actions:
            t = action.type

            if t == "create_node":
                add_id(action.id, sid, "create_node")

            elif t == "create_topology":
                for n in action.nodes:
                    add_id(n.id, sid, "create_topology")

            elif t == "create_connection":
                need(action.from_node, sid, "create_connection from")
                need(action.to_node, sid, "create_connection to")
                explicit = (action.id or "").strip()
                if explicit:
                    if explicit in known:
                        issues.append(f"scene {sid}: duplicate connection id {explicit!r}")
                    known.add(explicit)
                else:
                    _reserve_implicit_connection_id(
                        action.from_node, action.to_node, known
                    )

            elif t == "update_node":
                need(action.id, sid, "update_node")

            elif t == "remove_element":
                need(action.id, sid, "remove_element")

            elif t == "send_packet":
                need(action.from_node, sid, "send_packet from")
                need(action.to_node, sid, "send_packet to")

            elif t == "send_broadcast":
                need(action.from_node, sid, "send_broadcast")

            elif t == "show_sequence_diagram":
                pass

            elif t == "create_cloud_region":
                add_id(action.id, sid, "create_cloud_region")
                if action.parent_id:
                    need(action.parent_id, sid, "create_cloud_region parent")

            elif t == "create_cloud_service":
                add_id(action.id, sid, "create_cloud_service")

            elif t == "show_data_flow":
                for hop in action.hops:
                    need(hop.node_id, sid, "show_data_flow")

            elif t == "pulse_element":
                soft_need(action.target_id, sid, "pulse_element")

            elif t == "shake_element":
                soft_need(action.target_id, sid, "shake_element")

            elif t == "focus_camera":
                if action.target_id:
                    soft_need(action.target_id, sid, "focus_camera")

            elif t == "add_callout":
                soft_need(action.target_id, sid, "add_callout")

            elif t == "dim_except":
                for tid in action.target_ids:
                    soft_need(tid, sid, "dim_except")

            elif t in (
                "reset_camera", "show_progress", "update_progress",
                "emphasize_text", "restore_opacity", "scene_transition",
            ):
                pass

    if warnings:
        for w in warnings:
            logger.warning("Validation (soft): %s", w)

    if issues:
        msg = "Semantic validation failed:\n" + "\n".join(f"  - {i}" for i in issues)
        raise ValueError(msg)

    return warnings


def parse_actions_from_dicts(raw: list[dict]) -> list:
    adapter = TypeAdapter(list[VisualAction])
    return adapter.validate_python(raw)


# ---------------------------------------------------------------------------
# Layout validation — structural pre-render check
#
# Cheap heuristics on the action list. We can't compute exact BBoxes without
# rendering, but we can flag patterns that consistently produce visual bugs:
# slide content + diagram nodes in the same scene, oversized bullet lists,
# overly dense text blocks, and explicit positions outside the safe area.
#
# All findings are warnings (logged) — runtime safeguards (_avoid_collision,
# clamp_to_zone, _clamp_node_into_safe_area) handle the actual fix.
# ---------------------------------------------------------------------------

_DIAGRAM_CREATING_TYPES = frozenset({
    "create_node",
    "create_topology",
    "create_cloud_region",
    "create_cloud_service",
})

_SLIDE_TYPES = frozenset({
    "show_text_block",
    "show_bullet_list",
    "show_comparison",
    "show_table",
    "show_code_block",
    "show_chart",
    "show_layer_stack",
    "show_header_breakdown",
    "show_sequence_diagram",
})

_MAX_BULLETS_PER_LIST = 7
_MAX_TEXT_BODY_CHARS = 320
_MAX_NODES_PER_SCENE = 8


def validate_layout(script: EnrichedVideoScript) -> list[str]:
    """Walk scenes, emit warnings on layout patterns that risk visual bugs.

    Returns the list of warning strings (also logged at WARNING level).
    Never raises — runtime renderers fall back gracefully.
    """
    from rendering_engine.styles import (
        SAFE_AREA_BOTTOM, SAFE_AREA_LEFT, SAFE_AREA_RIGHT, SAFE_AREA_TOP,
    )

    warnings: list[str] = []

    for scene in script.scenes:
        sid = scene.scene_id
        actions = scene.actions
        types = [a.type for a in actions]

        slide_count = sum(1 for t in types if t in _SLIDE_TYPES)
        diagram_count = sum(1 for t in types if t in _DIAGRAM_CREATING_TYPES)

        # Pattern 1: slide content + new diagram nodes in same scene.
        # The slide content will compete with the boxes for canvas. Runtime
        # collision avoidance helps but flagging is still useful.
        if slide_count > 0 and diagram_count > 0:
            warnings.append(
                f"scene {sid}: mixes {slide_count} slide-style action(s) "
                f"with {diagram_count} diagram-creating action(s) — risk of "
                f"text-through-box collision"
            )

        # Pattern 2: explicit node positions outside safe area.
        # ``position`` is a string — either a hint ("center", "left") or
        # "x,y" coords. Only validate when coords parse to floats.
        for a in actions:
            if a.type == "create_node":
                pos = getattr(a, "position", "") or ""
                parts = [p.strip() for p in pos.split(",")]
                if len(parts) == 2:
                    try:
                        x, y = float(parts[0]), float(parts[1])
                    except ValueError:
                        continue
                    if not (SAFE_AREA_LEFT <= x <= SAFE_AREA_RIGHT
                            and SAFE_AREA_BOTTOM <= y <= SAFE_AREA_TOP):
                        warnings.append(
                            f"scene {sid} create_node {a.id!r}: position "
                            f"({x:.2f}, {y:.2f}) outside safe area"
                        )

        # Pattern 3: too many nodes on screen at once.
        if diagram_count > _MAX_NODES_PER_SCENE:
            warnings.append(
                f"scene {sid}: {diagram_count} diagram objects (max recommended "
                f"{_MAX_NODES_PER_SCENE}) — likely overcrowded"
            )

        # Pattern 4: oversized bullet lists.
        for a in actions:
            if a.type == "show_bullet_list":
                n = len(a.items)
                if n > _MAX_BULLETS_PER_LIST:
                    warnings.append(
                        f"scene {sid} show_bullet_list: {n} items (max "
                        f"recommended {_MAX_BULLETS_PER_LIST}) — won't fit "
                        f"at minimum readable font"
                    )

        # Pattern 5: dense text body.
        for a in actions:
            if a.type == "show_text_block":
                body_len = len(a.body or "")
                if body_len > _MAX_TEXT_BODY_CHARS:
                    warnings.append(
                        f"scene {sid} show_text_block: body is {body_len} "
                        f"chars (max recommended {_MAX_TEXT_BODY_CHARS}) — "
                        f"consider splitting"
                    )

    for w in warnings:
        logger.warning("Layout: %s", w)

    return warnings
