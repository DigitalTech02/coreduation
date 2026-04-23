"""Cloud architecture renderer — regions, services, and data flow animations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from manim import (
    DOWN,
    UP,
    Arrow,
    Create,
    DashedLine,
    FadeIn,
    FadeOut,
    Indicate,
    Line,
    MoveAlongPath,
    RoundedRectangle,
    Text,
    VGroup,
)

from rendering_engine.styles import (
    ACCENT,
    BG_COLOR,
    FADE_DURATION,
    LABEL_FONT_SIZE,
    MEDIUM_PAUSE,
    MUTED,
    NODE_CORNER_RADIUS,
    NODE_HEIGHT,
    NODE_STROKE_WIDTH,
    NODE_WIDTH,
    PACKET_HEIGHT,
    PACKET_WIDTH,
    PRIMARY,
    REGION_CORNER_RADIUS,
    REGION_PADDING,
    REGION_STROKE_WIDTH,
    SECONDARY,
    SHORT_PAUSE,
    SUBLABEL_FONT_SIZE,
    resolve_color,
)
from rendering_engine.topology import _parse_position

if TYPE_CHECKING:
    from manim import Scene as ManimScene

    from rendering_engine.engine import SceneState


# ---------------------------------------------------------------------------
# Cloud service visual theme (shape hints + colors)
# ---------------------------------------------------------------------------

_SERVICE_THEME: dict[str, tuple[str, str]] = {
    "compute": ("#e67e22", "rectangle"),
    "storage": ("#3498db", "rectangle"),
    "database": ("#2ecc71", "rectangle"),
    "serverless": ("#9b59b6", "rectangle"),
    "api_gateway": ("#e74c3c", "rectangle"),
    "cdn": ("#1abc9c", "rectangle"),
    "load_balancer": ("#f39c12", "rectangle"),
    "queue": ("#e67e22", "rectangle"),
    "cache": ("#e74c3c", "rectangle"),
    "dns": ("#3498db", "rectangle"),
    "generic": ("#95a5a6", "rectangle"),
}


# ---------------------------------------------------------------------------
# Cloud region / VPC / subnet
# ---------------------------------------------------------------------------

def render_create_cloud_region(scene: ManimScene, state: SceneState, action) -> None:
    """Draw a labeled bounding box representing a cloud region, VPC, or AZ."""
    pos = _parse_position(action.position)

    width = 5.0
    height = 3.5

    border = RoundedRectangle(
        width=width, height=height,
        corner_radius=REGION_CORNER_RADIUS,
        color=MUTED,
        stroke_width=REGION_STROKE_WIDTH,
        fill_color=BG_COLOR,
        fill_opacity=0.3,
    ).move_to(pos)

    label = Text(
        action.label, font_size=SUBLABEL_FONT_SIZE,
        color=MUTED,
    )
    label.next_to(border, UP, buff=0.1).align_to(border, direction=UP)
    label.shift(DOWN * 0.3)

    group = VGroup(border, label)

    if action.parent_id:
        parent = state.get(action.parent_id)
        if parent is not None:
            group.move_to(parent.get_center())
            group.set_width(parent.width - REGION_PADDING)
            group.set_height(parent.height - REGION_PADDING)

    state.register(action.id, group)
    scene.play(FadeIn(group), run_time=FADE_DURATION)


# ---------------------------------------------------------------------------
# Cloud service node
# ---------------------------------------------------------------------------

def render_create_cloud_service(scene: ManimScene, state: SceneState, action) -> None:
    """Place a cloud service node, optionally inside a region."""
    color_hex, _ = _SERVICE_THEME.get(action.service_type.value, ("#95a5a6", "rectangle"))

    box = RoundedRectangle(
        width=NODE_WIDTH * 0.9,
        height=NODE_HEIGHT * 0.9,
        corner_radius=NODE_CORNER_RADIUS,
        color=color_hex,
        stroke_width=NODE_STROKE_WIDTH,
        fill_color=color_hex,
        fill_opacity=0.15,
    )

    svc_type_label = Text(
        action.service_type.value.replace("_", " ").title(),
        font_size=SUBLABEL_FONT_SIZE * 0.85,
        color=color_hex,
    )
    name_label = Text(action.label, font_size=LABEL_FONT_SIZE, color=color_hex)

    inner = VGroup(name_label, svc_type_label).arrange(DOWN, buff=0.1)
    inner.move_to(box.get_center())
    node = VGroup(box, inner)

    pos = _parse_position(action.position)
    node.move_to(pos)

    if action.region_id:
        region = state.get(action.region_id)
        if region is not None:
            node.move_to(pos)

    state.register(action.id, node)
    scene.play(FadeIn(node), run_time=FADE_DURATION)


# ---------------------------------------------------------------------------
# Data flow — animated hop-by-hop request traversal
# ---------------------------------------------------------------------------

def render_show_data_flow(scene: ManimScene, state: SceneState, action) -> None:
    """Animate a request flowing through a chain of nodes, highlighting each hop."""
    color = resolve_color(action.color)
    hops = action.hops
    if len(hops) < 2:
        return

    packet_box = RoundedRectangle(
        width=PACKET_WIDTH, height=PACKET_HEIGHT,
        corner_radius=0.1, color=color,
        fill_color=color, fill_opacity=0.85,
        stroke_width=1.5,
    )
    packet_label = Text(
        action.label or "request", font_size=SUBLABEL_FONT_SIZE,
        color="#0f1117",
    )
    packet_label.move_to(packet_box.get_center())
    packet = VGroup(packet_box, packet_label)

    first_mob = state.get(hops[0].node_id)
    if first_mob is None:
        return
    packet.move_to(first_mob.get_center())
    scene.play(FadeIn(packet), run_time=FADE_DURATION * 0.5)

    for i in range(len(hops) - 1):
        src_mob = state.get(hops[i].node_id)
        dst_mob = state.get(hops[i + 1].node_id)
        if src_mob is None or dst_mob is None:
            continue

        path = Line(src_mob.get_center(), dst_mob.get_center())
        distance = path.get_length()
        duration = max(0.4, distance / 3.0)

        scene.play(MoveAlongPath(packet, path), run_time=duration)

        hop_label = hops[i + 1].label
        if hop_label:
            lbl = Text(hop_label, font_size=SUBLABEL_FONT_SIZE, color=color)
            lbl.next_to(dst_mob, UP, buff=0.25)
            scene.play(FadeIn(lbl), run_time=0.3)
            scene.wait(SHORT_PAUSE)
            scene.play(FadeOut(lbl), run_time=0.2)

        scene.play(Indicate(dst_mob, color=color, scale_factor=1.05), run_time=0.4)

    scene.play(FadeOut(packet), run_time=FADE_DURATION * 0.5)
