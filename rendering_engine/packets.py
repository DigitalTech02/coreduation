"""Packet & message flow renderer — animated packets traveling between nodes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from manim import (
    DOWN,
    UP,
    FadeIn,
    FadeOut,
    MoveAlongPath,
    Line,
    RoundedRectangle,
    Text,
    VGroup,
)

from rendering_engine.styles import (
    FADE_DURATION,
    LABEL_FONT_SIZE,
    MUTED,
    PACKET_HEIGHT,
    PACKET_SPEED_BASE,
    PACKET_WIDTH,
    SHORT_PAUSE,
    SUBLABEL_FONT_SIZE,
    apply_sheen,
    resolve_color,
)

if TYPE_CHECKING:
    from manim import Scene as ManimScene

    from rendering_engine.engine import SceneState


def _link_registered(
    state: SceneState, a: str, b: str
) -> bool:
    """True if any implicit or explicit connection id between nodes ``a`` and ``b`` exists."""
    base_fwd = f"conn_{a}_{b}"
    base_rev = f"conn_{b}_{a}"
    for k in state.objects:
        if k == base_fwd or k == base_rev:
            return True
        if k.startswith(base_fwd + "__") or k.startswith(base_rev + "__"):
            return True
    return False


def _build_packet(label: str, color) -> VGroup:
    """Create a small labeled rounded rectangle representing a packet.

    The box auto-expands for long labels so text never overflows.
    """
    txt = Text(label, font_size=SUBLABEL_FONT_SIZE, color="#0f1117")
    # Ensure box is wide enough for the label (with padding)
    box_w = max(PACKET_WIDTH, txt.width + 0.3)
    box_h = max(PACKET_HEIGHT, txt.height + 0.15)
    box = RoundedRectangle(
        width=box_w,
        height=box_h,
        corner_radius=0.1,
        color=color,
        fill_color=color,
        fill_opacity=0.85,
        stroke_width=1.5,
    )
    apply_sheen(box, factor=0.35)
    txt.move_to(box.get_center())
    return VGroup(box, txt)


def render_send_packet(scene: ManimScene, state: SceneState, action) -> None:
    """Animate a packet traveling from one node to another."""
    from_mob = state.get(action.from_node)
    to_mob = state.get(action.to_node)
    if from_mob is None or to_mob is None:
        return

    color = resolve_color(action.color)
    packet = _build_packet(action.label, color)
    packet.move_to(from_mob.get_center())

    path = Line(from_mob.get_center(), to_mob.get_center())
    distance = path.get_length()
    duration = max(0.4, distance / (PACKET_SPEED_BASE * action.speed))

    scene.play(FadeIn(packet), run_time=FADE_DURATION * 0.5)
    scene.play(MoveAlongPath(packet, path), run_time=duration)
    scene.play(FadeOut(packet), run_time=FADE_DURATION * 0.5)


def render_send_broadcast(scene: ManimScene, state: SceneState, action) -> None:
    """Animate a packet broadcasting from one node to all connected neighbors."""
    from_mob = state.get(action.from_node)
    if from_mob is None:
        return

    color = resolve_color(action.color)

    targets = []
    for key, mob in state.objects.items():
        if key == action.from_node or key.startswith("conn_"):
            continue
        if _link_registered(state, action.from_node, key):
            targets.append(mob)

    if not targets:
        all_others = [
            m
            for k, m in state.objects.items()
            if k != action.from_node and not k.startswith("conn_")
        ]
        targets = all_others

    packets = []
    paths = []
    for target in targets:
        pkt = _build_packet(action.label, color)
        pkt.move_to(from_mob.get_center())
        packets.append(pkt)
        paths.append(Line(from_mob.get_center(), target.get_center()))

    scene.play(*[FadeIn(p) for p in packets], run_time=FADE_DURATION * 0.5)
    scene.play(
        *[MoveAlongPath(p, path) for p, path in zip(packets, paths)],
        run_time=1.2,
    )
    scene.play(*[FadeOut(p) for p in packets], run_time=FADE_DURATION * 0.5)
