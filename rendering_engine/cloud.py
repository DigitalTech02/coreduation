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
    DIAGRAM_ZONE_BOTTOM,
    DIAGRAM_ZONE_TOP,
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
    SAFE_AREA_BOTTOM,
    SAFE_AREA_LEFT,
    SAFE_AREA_RIGHT,
    SAFE_AREA_TOP,
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
    w = max(region.get_width() * 0.75, 0.8)
    h = max(region.get_height() * 0.65, 0.6)
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


def _grid_position_within_region(state, region_id: str, region, position: str) -> tuple[float, float, float]:
    """Place a service on a grid inside *region*, avoiding sibling overlap.

    Counts existing children of *region_id* and computes the next available
    grid cell center using 75% of region width and 65% of region height
    (minus the top 15% reserved for the region label).
    """
    import math as _math

    siblings = state.children_of(region_id)
    n = len(siblings)  # already-placed children; we are placing n-th (0-indexed)

    cx, cy, _ = region.get_center()
    rw = max(region.get_width() * 0.75, 0.8)
    rh = max(region.get_height() * 0.65, 0.6)
    # Shift grid centre down slightly to avoid region label at top
    grid_cy = cy - region.get_height() * 0.07

    cols = _math.ceil(_math.sqrt(n + 1))
    rows = _math.ceil((n + 1) / cols)

    cell_w = rw / max(cols, 1)
    cell_h = rh / max(rows, 1)

    col = n % cols
    row = n // cols

    px = cx - rw / 2 + cell_w * (col + 0.5)
    py = grid_cy + rh / 2 - cell_h * (row + 0.5)

    return (px, py, 0.0)


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
    from rendering_engine.engine import BBox

    pos = _parse_position(action.position)
    # Clamp region position to diagram zone
    pos = (
        max(SAFE_AREA_LEFT + 1.3, min(SAFE_AREA_RIGHT - 1.3, pos[0])),
        max(DIAGRAM_ZONE_BOTTOM + 1.0, min(DIAGRAM_ZONE_TOP - 1.0, pos[1])),
        0,
    )

    # Dynamic sizing: shrink as more regions accumulate
    existing_regions = sum(
        1 for k, cat in state._categories.items()
        if cat == "persistent" and not k.startswith("__")
        and hasattr(state.objects.get(k), "get_width")
        and state.objects[k].get_width() > 2.0
    )
    if action.parent_id:
        width, height = 3.8, 2.5
    elif existing_regions >= 3:
        width, height = 3.0, 2.2
    elif existing_regions >= 2:
        width, height = 3.5, 2.5
    elif existing_regions >= 1:
        width, height = 4.0, 2.8
    else:
        width, height = 4.5, 3.0

    border = RoundedRectangle(
        width=width, height=height,
        corner_radius=REGION_CORNER_RADIUS,
        color=MUTED,
        stroke_width=REGION_STROKE_WIDTH,
        fill_color=darken_color(MUTED, 0.5),
        fill_opacity=0.1,
    ).move_to(pos)
    apply_sheen(border, factor=0.1)

    clean = _clean_label(action.label, max_len=36)
    label = Text(
        clean, font_size=SUBLABEL_FONT_SIZE * 0.95,
        color=WHITE,
    )
    label.set_opacity(1.0)
    if label.width > width - 0.3:
        label.set_width(width - 0.3)
    label.next_to(border, UP, buff=0.1).align_to(border, direction=UP)
    label.shift(DOWN * 0.3)

    # Dark pill behind region label for contrast
    label_bg = RoundedRectangle(
        width=label.width + 0.2,
        height=label.height + 0.1,
        corner_radius=0.05,
        stroke_width=0,
        fill_color=BG_COLOR,
        fill_opacity=0.65,
    )
    label_bg.move_to(label.get_center())

    group = VGroup(border, label_bg, label)

    if action.parent_id:
        parent = state.get(action.parent_id)
        if parent is not None:
            group.move_to(parent.get_center())
            group.set_width(parent.width - REGION_PADDING)
            group.set_height(parent.height - REGION_PADDING)
    elif existing_regions > 0:
        # Use spatial registry to find a non-overlapping position
        group_bbox = BBox(
            float(group.get_left()[0]), float(group.get_right()[0]),
            float(group.get_bottom()[1]), float(group.get_top()[1]),
        )
        if state.overlaps_any(group_bbox, margin=0.3):
            # Try a grid of candidate positions within the safe area
            best_pos = None
            sa_cx = (SAFE_AREA_LEFT + SAFE_AREA_RIGHT) / 2
            sa_cy = (SAFE_AREA_BOTTOM + SAFE_AREA_TOP) / 2
            candidates = [
                (sa_cx + 3.0, sa_cy), (sa_cx - 3.0, sa_cy),
                (sa_cx, sa_cy + 1.5), (sa_cx, sa_cy - 1.5),
                (sa_cx + 3.0, sa_cy + 1.2), (sa_cx - 3.0, sa_cy + 1.2),
                (sa_cx + 3.0, sa_cy - 1.2), (sa_cx - 3.0, sa_cy - 1.2),
            ]
            for tx, ty in candidates:
                tx = max(SAFE_AREA_LEFT + width / 2 + 0.2,
                         min(SAFE_AREA_RIGHT - width / 2 - 0.2, tx))
                ty = max(SAFE_AREA_BOTTOM + height / 2 + 0.2,
                         min(SAFE_AREA_TOP - height / 2 - 0.2, ty))
                test_bbox = BBox(
                    tx - width / 2, tx + width / 2,
                    ty - height / 2, ty + height / 2,
                )
                if not state.overlaps_any(test_bbox, margin=0.3):
                    best_pos = (tx, ty)
                    break
            if best_pos:
                group.move_to([best_pos[0], best_pos[1], 0])

    state.register(action.id, group)
    scene.play(FadeIn(group), run_time=FADE_DURATION)


# ---------------------------------------------------------------------------
# Cloud service node
# ---------------------------------------------------------------------------

def render_create_cloud_service(scene: ManimScene, state: SceneState, action) -> None:
    """Place a cloud service node, optionally inside a region."""
    from rendering_engine.engine import BBox

    color_hex, _ = _SERVICE_THEME.get(action.service_type.value, ("#95a5a6", "rectangle"))

    # Scale down when inside a region so services fit without overlapping
    in_region = bool(action.region_id and state.get(action.region_id))
    scale = 0.55 if in_region else 0.9

    dark_hex = darken_color(color_hex, 0.35)
    box = RoundedRectangle(
        width=NODE_WIDTH * scale,
        height=NODE_HEIGHT * scale,
        corner_radius=NODE_CORNER_RADIUS,
        color=color_hex,
        stroke_width=NODE_STROKE_WIDTH,
        fill_color=dark_hex,
        fill_opacity=0.2,
    )
    apply_sheen(box, factor=0.15)

    font_scale = 0.65 if in_region else 0.9
    clean_name = _clean_label(action.label, max_len=32)
    svc_type_label = Text(
        action.service_type.value.replace("_", " ").title(),
        font_size=SUBLABEL_FONT_SIZE * 0.78 * (0.72 if in_region else 1.0),
        color=WHITE,
    )
    svc_type_label.set_opacity(0.85)
    name_label = Text(clean_name, font_size=LABEL_FONT_SIZE * font_scale, color=WHITE)
    name_label.set_opacity(1.0)
    max_label_w = NODE_WIDTH * scale * 0.92
    if name_label.width > max_label_w:
        name_label.set_width(max_label_w)

    inner = VGroup(name_label, svc_type_label).arrange(DOWN, buff=0.06)
    needed_w = inner.width + 0.25
    if needed_w > box.width:
        box.stretch_to_fit_width(needed_w)
    text_bg = RoundedRectangle(
        width=inner.width + 0.15,
        height=inner.height + 0.1,
        corner_radius=0.06,
        stroke_width=0,
        fill_color=BG_COLOR,
        fill_opacity=0.55,
    )
    inner.move_to(box.get_center())
    text_bg.move_to(inner.get_center())
    node = VGroup(box, text_bg, inner)

    if in_region:
        region = state.get(action.region_id)
        node.move_to(_grid_position_within_region(state, action.region_id, region, action.position))

        # Light nudge if overlapping a sibling — stay within parent region
        node_bbox = BBox(
            float(node.get_left()[0]), float(node.get_right()[0]),
            float(node.get_bottom()[1]), float(node.get_top()[1]),
        )
        hits = state.overlaps_any(node_bbox, margin=0.15,
                                  exclude={action.region_id})
        if hits:
            rcx, rcy, _ = region.get_center()
            rw = region.get_width() * 0.70
            rh = region.get_height() * 0.58
            # Small shifts within the region bounds
            step_x = node.get_width() + 0.15
            step_y = node.get_height() + 0.1
            found = False
            for dy, dx in [(0, step_x), (0, -step_x),
                           (-step_y, 0), (step_y, 0),
                           (-step_y, step_x), (-step_y, -step_x),
                           (step_y, step_x), (step_y, -step_x)]:
                nx = node.get_center()[0] + dx
                ny = node.get_center()[1] + dy
                # Stay within region bounds
                if abs(nx - rcx) > rw or abs(ny - rcy) > rh:
                    continue
                node.move_to([nx, ny, 0])
                test_bbox = BBox(
                    float(node.get_left()[0]), float(node.get_right()[0]),
                    float(node.get_bottom()[1]), float(node.get_top()[1]),
                )
                if not state.overlaps_any(test_bbox, margin=0.15,
                                          exclude={action.region_id}):
                    found = True
                    break
            if not found:
                # Fallback: place at grid position (accept mild overlap)
                node.move_to(_grid_position_within_region(state, action.region_id, region, action.position))
    elif action.region_id:
        # region_id specified but region not found in state
        node.move_to(_parse_position(action.position))
    else:
        node.move_to(_parse_position(action.position))

    # Clamp service position to diagram zone
    cx, cy, _ = node.get_center()
    clamped_x = max(SAFE_AREA_LEFT + 0.5, min(SAFE_AREA_RIGHT - 0.5, cx))
    clamped_y = max(DIAGRAM_ZONE_BOTTOM + 0.3, min(DIAGRAM_ZONE_TOP - 0.3, cy))
    if clamped_x != cx or clamped_y != cy:
        node.move_to([clamped_x, clamped_y, 0])

    parent_id = action.region_id if in_region else None
    state.register(action.id, node, parent_id=parent_id)
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
    plab = _clean_label(action.label or "request", max_len=16)
    packet_label = Text(
        plab, font_size=max(12, int(SUBLABEL_FONT_SIZE) - 2),
        color=WHITE,
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
            if lbl.width > 4.0:
                lbl.set_width(4.0)
            mid = path.get_center() + UP * 0.35
            pill = RoundedRectangle(
                width=min(lbl.width + 0.35, 4.35), height=lbl.height + 0.14,
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
