"""Packet & message flow renderer — animated packets traveling between nodes."""

from __future__ import annotations

import logging
import re
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

logger = logging.getLogger(__name__)

from rendering_engine.styles import (
    FADE_DURATION,
    LABEL_FONT_SIZE,
    MUTED,
    PACKET_DURATION_MAX,
    PACKET_DURATION_MIN,
    PACKET_HEIGHT,
    PACKET_MAX_WIDTH,
    PACKET_SPEED_BASE,
    PACKET_WIDTH,
    SHORT_PAUSE,
    SUBLABEL_FONT_SIZE,
    apply_sheen,
    resolve_color,
)

PACKET_LABEL_PADDING = 0.25

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
    """Create a labeled rounded rectangle representing a packet.

    Box auto-grows to fit the label between ``PACKET_WIDTH`` and
    ``PACKET_MAX_WIDTH``. If the label still doesn't fit at the cap, the text
    scales down rather than overflowing the box.
    """
    cleaned = re.sub(r"\s+", " ", (label or "").replace("\n", " ")).strip()
    txt = Text(cleaned, font_size=SUBLABEL_FONT_SIZE, color="#0f1117")

    target_w = min(
        max(PACKET_WIDTH, txt.width + PACKET_LABEL_PADDING),
        PACKET_MAX_WIDTH,
    )
    box = RoundedRectangle(
        width=target_w,
        height=PACKET_HEIGHT,
        corner_radius=0.1,
        color=color,
        fill_color=color,
        fill_opacity=0.85,
        stroke_width=1.5,
    )
    apply_sheen(box, factor=0.35)

    if txt.width > target_w - PACKET_LABEL_PADDING:
        txt.set_width(target_w - PACKET_LABEL_PADDING)
    txt.move_to(box.get_center())
    return VGroup(box, txt)


def _diag(msg: str) -> None:
    """Append diagnostic line to /tmp/packet_diag.log — bypasses Manim's
    column-aligned Rich logger which truncates anything wide."""
    try:
        with open("/tmp/packet_diag.log", "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def render_send_packet(scene: ManimScene, state: SceneState, action) -> None:
    """Animate a packet traveling from one node to another."""
    _diag(
        f"ENTER from={action.from_node!r} to={action.to_node!r} "
        f"label={action.label!r} color={action.color!r} speed={action.speed}"
    )
    from_mob = state.get(action.from_node)
    to_mob = state.get(action.to_node)
    if from_mob is None or to_mob is None:
        _diag(
            f"  SKIP: from_mob={'OK' if from_mob else 'MISSING'} "
            f"to_mob={'OK' if to_mob else 'MISSING'} — no packet rendered"
        )
        logger.warning(
            "send_packet: from=%r (%s) to=%r (%s) — endpoint(s) not in state, skipping",
            action.from_node, "found" if from_mob else "MISSING",
            action.to_node, "found" if to_mob else "MISSING",
        )
        return

    color = resolve_color(action.color)
    packet = _build_packet(action.label, color)
    # Anchor the packet at the EDGE of the source node facing the target,
    # not the source's center — starting the packet inside the box made it
    # look like it "appeared" rather than "left the client".  Same on the
    # target side: end at the receiving edge so the packet visibly arrives.
    src = from_mob.get_center()
    dst = to_mob.get_center()
    direction = dst - src
    norm = (direction[0] ** 2 + direction[1] ** 2 + direction[2] ** 2) ** 0.5
    if norm > 1e-6:
        unit = direction / norm
        try:
            src = from_mob.get_critical_point(unit)
            dst = to_mob.get_critical_point(-unit)
        except Exception:
            pass

    packet.move_to(src)

    path = Line(src, dst)
    distance = path.get_length()
    raw = distance / (PACKET_SPEED_BASE * action.speed)
    duration = max(PACKET_DURATION_MIN, min(PACKET_DURATION_MAX, raw))

    try:
        from_xy = list(from_mob.get_center())[:2]
        to_xy = list(to_mob.get_center())[:2]
    except Exception:
        from_xy = to_xy = "?"

    _diag(
        f"  PLAY: label={action.label!r} from_xy={from_xy} to_xy={to_xy} "
        f"distance={distance:.3f} raw={raw:.3f} duration={duration:.3f} "
        f"PACKET_SPEED_BASE={PACKET_SPEED_BASE} "
        f"PACKET_DURATION_MIN={PACKET_DURATION_MIN} "
        f"PACKET_DURATION_MAX={PACKET_DURATION_MAX} "
        f"FADE_DURATION={FADE_DURATION}"
    )

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
