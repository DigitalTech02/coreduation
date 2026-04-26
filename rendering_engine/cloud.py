"""Cloud architecture renderer — regions, services, and data flow animations."""

from __future__ import annotations

import re
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
    WHITE,
    apply_sheen,
    darken_color,
    resolve_color,
)
from rendering_engine.topology import _parse_position

if TYPE_CHECKING:
    from manim import Scene as ManimScene

    from rendering_engine.engine import SceneState


def _clean_label(s: str, max_len: int = 48) -> str:
    """Single-line label: no accidental line breaks, collapsed whitespace."""
    t = re.sub(r"\s+", " ", (s or "").replace("\n", " ").replace("\r", " ")).strip()
    if len(t) > max_len:
        t = t[: max_len - 1].rstrip() + "…"
    return t


def _position_within_region(region, position: str) -> tuple[float, float, float]:
    """Map named / numeric positions to coordinates *inside* a region mobject.

    Services with ``region_id`` used to use global ``_parse_position("center")``
    → (0,0,0) for every node, piling them on top of each other. This places
    each service inside the parent region's bounding box instead.
    """
    from rendering_engine.topology import _parse_position

    cx, cy, _ = region.get_center()
    w = max(region.get_width() * 0.32, 0.55)
    h = max(region.get_height() * 0.32, 0.4)
    pos = (position or "center").strip()

    if "," in pos:
        try:
            parts = [float(p.strip()) for p in pos.split(",")]
            if len(parts) >= 2:
                return (cx + parts[0], cy + parts[1], 0.0)
        except Exception:
            pass

    p_low = pos.lower()
    slots = {
        "center": (cx, cy),
        "left": (cx - w, cy),
        "right": (cx + w, cy),
        "top": (cx, cy + h),
        "bottom": (cx, cy - h),
        "top_left": (cx - w * 0.9, cy + h * 0.9),
        "top_right": (cx + w * 0.9, cy + h * 0.9),
        "bottom_left": (cx - w * 0.9, cy - h * 0.9),
        "bottom_right": (cx + w * 0.9, cy - h * 0.9),
    }
    for key, (px, py) in slots.items():
        if p_low == key or p_low.replace("_", " ") == key.replace("_", " "):
            return (px, py, 0.0)

    return (cx, cy, 0.0)


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

    width = 3.0 if not action.parent_id else 3.2
    height = 2.2 if not action.parent_id else 2.4

    border = RoundedRectangle(
        width=width, height=height,
        corner_radius=REGION_CORNER_RADIUS,
        color=MUTED,
        stroke_width=REGION_STROKE_WIDTH,
        fill_color=darken_color(MUTED, 0.5),
        fill_opacity=0.1,
    ).move_to(pos)
    apply_sheen(border, factor=0.2)

    clean = _clean_label(action.label, max_len=36)
    label = Text(
        clean, font_size=SUBLABEL_FONT_SIZE * 0.95,
        color=WHITE,
    )
    label.set_opacity(0.92)
    if label.width > width + 0.2:
        label.set_width(width + 0.2)
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

    dark_hex = darken_color(color_hex, 0.35)
    box = RoundedRectangle(
        width=NODE_WIDTH * 0.9,
        height=NODE_HEIGHT * 0.9,
        corner_radius=NODE_CORNER_RADIUS,
        color=color_hex,
        stroke_width=NODE_STROKE_WIDTH,
        fill_color=dark_hex,
        fill_opacity=0.2,
    )
    apply_sheen(box, factor=0.3)

    clean_name = _clean_label(action.label, max_len=32)
    svc_type_label = Text(
        action.service_type.value.replace("_", " ").title(),
        font_size=SUBLABEL_FONT_SIZE * 0.78,
        color=WHITE,
    )
    svc_type_label.set_opacity(0.75)
    name_label = Text(clean_name, font_size=LABEL_FONT_SIZE * 0.9, color=WHITE)
    if name_label.width > NODE_WIDTH * 0.85:
        name_label.set_width(NODE_WIDTH * 0.85)

    inner = VGroup(name_label, svc_type_label).arrange(DOWN, buff=0.08)
    inner.move_to(box.get_center())
    node = VGroup(box, inner)

    if action.region_id:
        region = state.get(action.region_id)
        if region is not None:
            node.move_to(_position_within_region(region, action.position))
        else:
            node.move_to(_parse_position(action.position))
    else:
        node.move_to(_parse_position(action.position))

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
    apply_sheen(packet_box, factor=0.35)
    plab = _clean_label(action.label or "request", max_len=22)
    packet_label = Text(
        plab, font_size=max(12, int(SUBLABEL_FONT_SIZE) - 2),
        color="#0f1117",
    )
    if packet_label.width > PACKET_WIDTH * 0.9:
        packet_label.set_width(PACKET_WIDTH * 0.88)
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
            short = _clean_label(hop_label, max_len=36)
            lbl = Text(short, font_size=SUBLABEL_FONT_SIZE - 2, color=WHITE)
            mid = path.get_center() + UP * 0.35
            pill = RoundedRectangle(
                width=min(lbl.width + 0.35, 5.5), height=lbl.height + 0.14,
                corner_radius=0.06, stroke_width=0,
                fill_color=BG_COLOR, fill_opacity=0.88,
            )
            lbl.move_to(mid)
            pill.move_to(mid)
            hop_grp = VGroup(pill, lbl)
            scene.play(FadeIn(hop_grp), run_time=0.25)
            scene.wait(SHORT_PAUSE)
            scene.play(FadeOut(hop_grp), run_time=0.2)

        scene.play(Indicate(dst_mob, color=color, scale_factor=1.05), run_time=0.4)

    scene.play(FadeOut(packet), run_time=FADE_DURATION * 0.5)
