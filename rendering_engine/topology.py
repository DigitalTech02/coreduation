"""Topology renderer — network nodes, connections, and layout generators."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from manim import (
    DOWN,
    LEFT,
    RIGHT,
    UP,
    Arrow,
    Circle,
    Create,
    DashedLine,
    Dot,
    Ellipse,
    FadeIn,
    FadeOut,
    Indicate,
    Line,
    RoundedRectangle,
    Text,
    VGroup,
)

from rendering_engine.styles import (
    BG_COLOR,
    CONNECTION_STROKE_WIDTH,
    CONNECTION_TIP_SCALE,
    DIAGRAM_ZONE_BOTTOM,
    DIAGRAM_ZONE_TOP,
    FADE_DURATION,
    GLOW_OPACITY,
    GLOW_SCALE,
    ICON_THEME,
    LABEL_FONT_SIZE,
    MUTED,
    NODE_CORNER_RADIUS,
    NODE_HEIGHT,
    NODE_STROKE_WIDTH,
    NODE_WIDTH,
    SAFE_AREA_BOTTOM,
    SAFE_AREA_LEFT,
    SAFE_AREA_RIGHT,
    SAFE_AREA_TOP,
    SUBLABEL_FONT_SIZE,
    WHITE,
    apply_sheen,
    darken_color,
    resolve_color,
)

if TYPE_CHECKING:
    from manim import Scene as ManimScene

    from rendering_engine.engine import SceneState


def _unique_connection_id(state: "SceneState", action) -> str:
    """Match semantic validation: ``conn_a_b``, ``conn_a_b__1``, … when id omitted."""
    explicit = (action.id or "").strip()
    if explicit:
        return explicit
    base = f"conn_{action.from_node}_{action.to_node}"
    cid = base
    suffix = 0
    while cid in state.objects:
        suffix += 1
        cid = f"{base}__{suffix}"
    return cid


# ---------------------------------------------------------------------------
# Position helpers
# ---------------------------------------------------------------------------

_POSITION_MAP = {
    "left": (-4.5, 0, 0),
    "right": (4.5, 0, 0),
    "center": (0, 0, 0),
    "top": (0, 1.8, 0),
    "bottom": (0, -1.4, 0),
    "top_left": (-4.5, 1.8, 0),
    "top_right": (4.5, 1.8, 0),
    "bottom_left": (-4.5, -1.4, 0),
    "bottom_right": (4.5, -1.4, 0),
}


def _parse_position(pos: str) -> tuple[float, float, float]:
    if pos in _POSITION_MAP:
        return _POSITION_MAP[pos]
    if "," in pos:
        parts = [float(p.strip()) for p in pos.split(",")]
        if len(parts) >= 2:
            return (parts[0], parts[1], 0)
    return (0, 0, 0)


def _clamp_node_into_safe_area(mob, padding: float = 0.15) -> None:
    """Shift a node so its full bounding box (label + shape) sits inside the
    safe area.  The LLM occasionally emits positions like (6,0) which place
    the centre near the right edge — half the node spills off-frame.
    """
    left = float(mob.get_left()[0])
    right = float(mob.get_right()[0])
    top = float(mob.get_top()[1])
    bottom = float(mob.get_bottom()[1])
    dx = 0.0
    dy = 0.0
    if right > SAFE_AREA_RIGHT - padding:
        dx = (SAFE_AREA_RIGHT - padding) - right
    elif left < SAFE_AREA_LEFT + padding:
        dx = (SAFE_AREA_LEFT + padding) - left
    if top > SAFE_AREA_TOP - padding:
        dy = (SAFE_AREA_TOP - padding) - top
    elif bottom < SAFE_AREA_BOTTOM + padding:
        dy = (SAFE_AREA_BOTTOM + padding) - bottom
    if dx or dy:
        mob.shift([dx, dy, 0])


# ---------------------------------------------------------------------------
# Node shape builders
# ---------------------------------------------------------------------------

def _build_node_shape(icon_type: str, color):
    shape_name, default_color = ICON_THEME.get(icon_type, ("rectangle", color))
    c = color or default_color
    dark = darken_color(c, 0.35)

    if shape_name == "circle":
        shape = Circle(radius=NODE_HEIGHT / 2, color=c, stroke_width=NODE_STROKE_WIDTH,
                        fill_color=dark, fill_opacity=0.18)
        return apply_sheen(shape)
    if shape_name == "ellipse":
        shape = Ellipse(width=NODE_WIDTH, height=NODE_HEIGHT, color=c,
                        stroke_width=NODE_STROKE_WIDTH, fill_color=dark, fill_opacity=0.18)
        return apply_sheen(shape)
    if shape_name == "diamond":
        sq = RoundedRectangle(
            width=NODE_HEIGHT, height=NODE_HEIGHT,
            corner_radius=NODE_CORNER_RADIUS, color=c, stroke_width=NODE_STROKE_WIDTH,
            fill_color=dark, fill_opacity=0.18,
        )
        sq.rotate(math.pi / 4)
        sq.set_width(NODE_WIDTH * 0.85)
        sq.set_height(NODE_HEIGHT)
        return apply_sheen(sq)
    if shape_name == "cylinder":
        body = RoundedRectangle(
            width=NODE_WIDTH * 0.7, height=NODE_HEIGHT,
            corner_radius=0.05, color=c, stroke_width=NODE_STROKE_WIDTH,
            fill_color=dark, fill_opacity=0.18,
        )
        top_ellipse = Ellipse(
            width=NODE_WIDTH * 0.7, height=0.35,
            color=c, stroke_width=NODE_STROKE_WIDTH,
            fill_color=c, fill_opacity=0.25,
        ).move_to(body.get_top())
        grp = VGroup(body, top_ellipse)
        apply_sheen(body)
        return grp

    shape = RoundedRectangle(
        width=NODE_WIDTH, height=NODE_HEIGHT,
        corner_radius=NODE_CORNER_RADIUS, color=c, stroke_width=NODE_STROKE_WIDTH,
        fill_color=dark, fill_opacity=0.18,
    )
    return apply_sheen(shape)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_create_node(scene: ManimScene, state: SceneState, action) -> None:
    """Render a create_node action."""
    pos = _parse_position(action.position)
    _, default_color = ICON_THEME.get(action.icon_type.value, ("rectangle", MUTED))

    shape = _build_node_shape(action.icon_type.value, default_color)
    shape.move_to(pos)

    label_text = action.label[:18] + "…" if len(action.label) > 18 else action.label
    label = Text(label_text, font_size=LABEL_FONT_SIZE, color=WHITE)
    label.set_opacity(1.0)
    max_label_w = NODE_WIDTH - 0.25
    if label.width > max_label_w:
        label.set_width(max_label_w)
    label.move_to(shape.get_center())

    text_parts = [label]

    if action.sublabel:
        sublabel_text = action.sublabel[:22] + "…" if len(action.sublabel) > 22 else action.sublabel
        sub = Text(sublabel_text, font_size=SUBLABEL_FONT_SIZE, color=WHITE)
        sub.set_opacity(0.85)
        if sub.width > max_label_w:
            sub.set_width(max_label_w)
        sub.next_to(label, DOWN, buff=0.1)
        text_parts.append(sub)

    # Dark pill behind text for readability over sheen
    text_group = VGroup(*text_parts)
    if text_group.width + 0.25 > shape.get_width():
        shape.stretch_to_fit_width(text_group.width + 0.3)
    text_bg = RoundedRectangle(
        width=text_group.width + 0.2,
        height=text_group.height + 0.12,
        corner_radius=0.06,
        stroke_width=0,
        fill_color=BG_COLOR,
        fill_opacity=0.55,
    )
    text_bg.move_to(text_group.get_center())

    group = VGroup(shape, text_bg, *text_parts)
    _clamp_node_into_safe_area(group)
    state.register(action.id, group)
    scene.play(FadeIn(group), run_time=FADE_DURATION)


def render_create_connection(scene: ManimScene, state: SceneState, action) -> None:
    """Render a create_connection action."""
    from_mob = state.get(action.from_node)
    to_mob = state.get(action.to_node)
    if from_mob is None or to_mob is None:
        return

    color = resolve_color(action.color) if action.color else MUTED
    start = from_mob.get_center()
    end = to_mob.get_center()

    if action.style.value == "dashed":
        line = DashedLine(
            start, end, color=color,
            stroke_width=CONNECTION_STROKE_WIDTH,
        )
    elif action.style.value == "dotted":
        line = DashedLine(
            start, end, color=color,
            stroke_width=CONNECTION_STROKE_WIDTH,
            dash_length=0.08,
        )
    else:
        if action.bidirectional:
            line = Line(
                start, end, color=color,
                stroke_width=CONNECTION_STROKE_WIDTH,
            )
        else:
            line = Arrow(
                start, end, color=color,
                stroke_width=CONNECTION_STROKE_WIDTH,
                tip_length=CONNECTION_TIP_SCALE,
                buff=0.5,
            )

    conn_group = VGroup(line)

    if action.label:
        mid = line.get_center()
        conn_label_text = action.label[:30] + "…" if len(action.label) > 30 else action.label
        lbl = Text(conn_label_text, font_size=SUBLABEL_FONT_SIZE - 2, color=WHITE)
        max_conn_label_w = 3.0
        if lbl.width > max_conn_label_w:
            lbl.set_width(max_conn_label_w)
        lbl_bg = RoundedRectangle(
            width=lbl.width + 0.2, height=lbl.height + 0.1,
            corner_radius=0.05, stroke_width=0,
            fill_color=BG_COLOR, fill_opacity=0.75,
        )
        lbl_bg.move_to(mid + UP * 0.18)
        lbl.move_to(lbl_bg.get_center())
        conn_group.add(lbl_bg, lbl)

    conn_id = _unique_connection_id(state, action)
    state.register(conn_id, conn_group)
    scene.play(Create(line), run_time=FADE_DURATION)
    if action.label:
        scene.play(FadeIn(conn_group[-1]), run_time=FADE_DURATION * 0.5)


def render_update_node(scene: ManimScene, state: SceneState, action) -> None:
    """Update a node's appearance: label/sublabel text and glow highlight."""
    from manim import Transform

    mob = state.get(action.id)
    if mob is None:
        return

    # Update label / sublabel text if provided
    if action.label or action.sublabel:
        # Find existing text submobjects (skip shape at index 0 and text_bg at index 1)
        text_subs = [sub for sub in mob if isinstance(sub, Text)]
        if action.label and len(text_subs) >= 1:
            old_label = text_subs[0]
            new_label = Text(
                action.label[:18] + "…" if len(action.label) > 18 else action.label,
                font_size=LABEL_FONT_SIZE, color=WHITE,
            )
            new_label.set_opacity(1.0)
            max_label_w = NODE_WIDTH - 0.25
            if new_label.width > max_label_w:
                new_label.set_width(max_label_w)
            new_label.move_to(old_label.get_center())
            scene.play(Transform(old_label, new_label), run_time=0.4)
        if action.sublabel and len(text_subs) >= 2:
            old_sub = text_subs[1]
            new_sub = Text(
                action.sublabel[:22] + "…" if len(action.sublabel) > 22 else action.sublabel,
                font_size=SUBLABEL_FONT_SIZE, color=WHITE,
            )
            new_sub.set_opacity(0.85)
            max_label_w = NODE_WIDTH - 0.25
            if new_sub.width > max_label_w:
                new_sub.set_width(max_label_w)
            new_sub.move_to(old_sub.get_center())
            scene.play(Transform(old_sub, new_sub), run_time=0.4)

    if action.highlight_color:
        color = resolve_color(action.highlight_color)

        glow = mob[0].copy() if len(mob) > 0 else mob.copy()
        glow.scale(GLOW_SCALE)
        glow.move_to(mob.get_center())
        glow.set_fill(color, opacity=GLOW_OPACITY)
        glow.set_stroke(color, width=0)
        scene.play(FadeIn(glow, run_time=0.25))

        scene.play(Indicate(mob, color=color), run_time=0.6)
        for sub in mob:
            if hasattr(sub, "set_color"):
                sub.set_color(color)

        mob.add_to_back(glow)


def render_remove_element(scene: ManimScene, state: SceneState, action) -> None:
    """Fade out and unregister an element."""
    mob = state.get(action.id)
    if mob is None:
        return
    scene.play(FadeOut(mob), run_time=FADE_DURATION)
    state.unregister(action.id)


def render_create_topology(scene: ManimScene, state: SceneState, action) -> None:
    """Generate a full topology layout and render all nodes + connections."""
    from models_semantic import CreateConnection, CreateNode

    n = len(action.nodes)
    if n == 0:
        return

    positions = _compute_layout_positions(action.layout.value, n, action.center_node_id, action.nodes)

    created_node_ids: list[str] = []
    for i, node_def in enumerate(action.nodes):
        x, y = positions[i]
        create = CreateNode(
            id=node_def.id,
            label=node_def.label,
            sublabel=node_def.sublabel,
            position=f"{x},{y}",
            icon_type=node_def.icon_type,
        )
        render_create_node(scene, state, create)
        created_node_ids.append(node_def.id)

    try:
        from rendering_engine.topology_3d import (
            add_orbit_drift,
            apply_pseudo_depth,
            is_enabled,
        )
        if is_enabled():
            apply_pseudo_depth([state.objects[nid] for nid in created_node_ids
                                 if nid in state.objects])
            add_orbit_drift(scene)
    except Exception:
        pass

    connections = _compute_topology_connections(action.layout.value, action.nodes, action.center_node_id)
    for from_id, to_id in connections:
        conn = CreateConnection(
            **{"from": from_id, "to": to_id},
            style="solid",
            bidirectional=True,
        )
        render_create_connection(scene, state, conn)


def _clamp_positions(positions: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Clamp layout positions to the diagram zone (inside safe area)."""
    return [
        (max(SAFE_AREA_LEFT + 0.5, min(SAFE_AREA_RIGHT - 0.5, x)),
         max(DIAGRAM_ZONE_BOTTOM + 0.3, min(DIAGRAM_ZONE_TOP - 0.3, y)))
        for x, y in positions
    ]


def _compute_layout_positions(
    layout: str, n: int, center_id: str | None, nodes
) -> list[tuple[float, float]]:
    if layout == "star":
        positions = []
        radius = min(3.2, 2.2 + 0.18 * max(n - 4, 0))
        outer = [nd for nd in nodes if nd.id != center_id]
        if center_id:
            positions.append((0.0, 0.0))
        for i, _ in enumerate(outer):
            angle = 2 * math.pi * i / max(len(outer), 1) + math.pi / 2
            positions.append((radius * math.cos(angle), radius * math.sin(angle)))
        if center_id:
            node_order = [center_id] + [nd.id for nd in outer]
            idx_map = {nid: i for i, nid in enumerate(node_order)}
            return _clamp_positions([positions[idx_map.get(nd.id, i)] for i, nd in enumerate(nodes)])
        return _clamp_positions(positions)

    if layout == "ring":
        radius = min(3.0, 2.0 + 0.15 * max(n - 4, 0))
        return _clamp_positions([
            (radius * math.cos(2 * math.pi * i / n + math.pi / 2),
             radius * math.sin(2 * math.pi * i / n + math.pi / 2))
            for i in range(n)
        ])

    if layout == "bus":
        spacing = min(3.0, 10.0 / max(n - 1, 1))
        start_x = -(n - 1) * spacing / 2
        return _clamp_positions([(start_x + i * spacing, 0.0) for i in range(n)])

    if layout == "tree":
        positions = [(0.0, 2.5)]
        level_start = 1
        level = 1
        while level_start < n:
            count = min(2 ** level, n - level_start)
            width = max(count * 2.8, 4.0)
            if width > 12.0:
                width = 12.0
            for j in range(count):
                x = -width / 2 + j * (width / max(count - 1, 1))
                positions.append((x, 2.5 - level * 1.8))
            level_start += count
            level += 1
        return _clamp_positions(positions[:n])

    if layout == "mesh":
        cols = math.ceil(math.sqrt(n))
        col_spacing = min(3.5, 11.0 / max(cols, 1))
        rows = math.ceil(n / cols)
        row_spacing = min(2.5, 6.0 / max(rows, 1))
        x_offset = -(cols - 1) * col_spacing / 2
        y_offset = (rows - 1) * row_spacing / 2
        return _clamp_positions([
            (x_offset + (i % cols) * col_spacing,
             y_offset - (i // cols) * row_spacing)
            for i in range(n)
        ])

    spacing = min(2.5, 10.0 / max(n - 1, 1))
    return _clamp_positions([(i * spacing - (n - 1) * spacing / 2, 0) for i in range(n)])


def _compute_topology_connections(
    layout: str, nodes, center_id: str | None
) -> list[tuple[str, str]]:
    ids = [n.id for n in nodes]
    if layout == "star" and center_id:
        return [(center_id, nid) for nid in ids if nid != center_id]
    if layout == "ring":
        return [(ids[i], ids[(i + 1) % len(ids)]) for i in range(len(ids))]
    if layout == "bus":
        return [(ids[i], ids[i + 1]) for i in range(len(ids) - 1)]
    if layout == "mesh":
        return [(ids[i], ids[j]) for i in range(len(ids)) for j in range(i + 1, len(ids))]
    if layout == "tree":
        conns = []
        for i in range(len(ids)):
            left = 2 * i + 1
            right = 2 * i + 2
            if left < len(ids):
                conns.append((ids[i], ids[left]))
            if right < len(ids):
                conns.append((ids[i], ids[right]))
        return conns
    return []
