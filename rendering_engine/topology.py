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
    SUBLABEL_FONT_SIZE,
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
    "top": (0, 2.5, 0),
    "bottom": (0, -2.5, 0),
    "top_left": (-4.5, 2.5, 0),
    "top_right": (4.5, 2.5, 0),
    "bottom_left": (-4.5, -2.5, 0),
    "bottom_right": (4.5, -2.5, 0),
}


def _parse_position(pos: str) -> tuple[float, float, float]:
    if pos in _POSITION_MAP:
        return _POSITION_MAP[pos]
    if "," in pos:
        parts = [float(p.strip()) for p in pos.split(",")]
        if len(parts) >= 2:
            return (parts[0], parts[1], 0)
    return (0, 0, 0)


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

    label = Text(action.label, font_size=LABEL_FONT_SIZE, color=default_color)
    max_label_w = NODE_WIDTH - 0.25
    if label.width > max_label_w:
        label.set_width(max_label_w)
    label.move_to(shape.get_center())

    parts = [shape, label]

    if action.sublabel:
        sub = Text(action.sublabel, font_size=SUBLABEL_FONT_SIZE, color=MUTED)
        if sub.width > max_label_w:
            sub.set_width(max_label_w)
        sub.next_to(label, DOWN, buff=0.1)
        parts.append(sub)

    group = VGroup(*parts)
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
        lbl = Text(action.label, font_size=SUBLABEL_FONT_SIZE, color=color)
        lbl.next_to(mid, UP, buff=0.15)
        conn_group.add(lbl)

    conn_id = _unique_connection_id(state, action)
    state.register(conn_id, conn_group)
    scene.play(Create(line), run_time=FADE_DURATION)
    if action.label:
        scene.play(FadeIn(conn_group[-1]), run_time=FADE_DURATION * 0.5)


def render_update_node(scene: ManimScene, state: SceneState, action) -> None:
    """Update a node's appearance with a glow highlight."""
    mob = state.get(action.id)
    if mob is None:
        return

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

    connections = _compute_topology_connections(action.layout.value, action.nodes, action.center_node_id)
    for from_id, to_id in connections:
        conn = CreateConnection(
            **{"from": from_id, "to": to_id},
            style="solid",
            bidirectional=True,
        )
        render_create_connection(scene, state, conn)


def _compute_layout_positions(
    layout: str, n: int, center_id: str | None, nodes
) -> list[tuple[float, float]]:
    if layout == "star":
        positions = []
        radius = 2.8
        outer = [nd for nd in nodes if nd.id != center_id]
        if center_id:
            positions.append((0.0, 0.0))
        for i, _ in enumerate(outer):
            angle = 2 * math.pi * i / max(len(outer), 1) + math.pi / 2
            positions.append((radius * math.cos(angle), radius * math.sin(angle)))
        if center_id:
            node_order = [center_id] + [nd.id for nd in outer]
            idx_map = {nid: i for i, nid in enumerate(node_order)}
            return [positions[idx_map.get(nd.id, i)] for i, nd in enumerate(nodes)]
        return positions

    if layout == "ring":
        radius = 2.5
        return [
            (radius * math.cos(2 * math.pi * i / n + math.pi / 2),
             radius * math.sin(2 * math.pi * i / n + math.pi / 2))
            for i in range(n)
        ]

    if layout == "bus":
        start_x = -(n - 1) * 1.5
        return [(start_x + i * 3.0, 0.0) for i in range(n)]

    if layout == "tree":
        positions = [(0.0, 2.5)]
        level_start = 1
        level = 1
        while level_start < n:
            count = min(2 ** level, n - level_start)
            width = count * 2.5
            for j in range(count):
                x = -width / 2 + j * (width / max(count - 1, 1))
                positions.append((x, 2.5 - level * 1.8))
            level_start += count
            level += 1
        return positions[:n]

    if layout == "mesh":
        cols = math.ceil(math.sqrt(n))
        return [
            (-3.0 + (i % cols) * 3.0, 2.0 - (i // cols) * 2.0)
            for i in range(n)
        ]

    return [(i * 2.5 - (n - 1) * 1.25, 0) for i in range(n)]


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
