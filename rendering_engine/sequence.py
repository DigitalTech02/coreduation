"""Sequence diagram renderer — vertical lifelines with horizontal message arrows."""

from __future__ import annotations

from typing import TYPE_CHECKING

from manim import (
    DOWN,
    UP,
    Arrow,
    Create,
    DashedLine,
    FadeIn,
    Line,
    RoundedRectangle,
    Text,
    VGroup,
    Write,
)

from rendering_engine.styles import (
    BODY_FONT_SIZE,
    FADE_DURATION,
    LABEL_FONT_SIZE,
    MEDIUM_PAUSE,
    MUTED,
    PRIMARY,
    SEQ_LIFELINE_COLOR,
    SEQ_MESSAGE_GAP,
    SEQ_PARTICIPANT_GAP,
    SHORT_PAUSE,
    SMALL_FONT_SIZE,
    SUBLABEL_FONT_SIZE,
    SUBTITLE_FONT_SIZE,
    TITLE_FONT_SIZE,
    resolve_color,
)

if TYPE_CHECKING:
    from manim import Scene as ManimScene

    from rendering_engine.engine import SceneState


def render_show_sequence_diagram(scene: ManimScene, state: SceneState, action) -> None:
    """Draw a UML-style sequence diagram with participants and messages."""
    participants = action.participants
    messages = action.messages
    n = len(participants)

    if n == 0:
        return

    total_width = (n - 1) * SEQ_PARTICIPANT_GAP
    start_x = -total_width / 2
    top_y = 2.5
    bottom_y = top_y - 1.5 - len(messages) * SEQ_MESSAGE_GAP

    participant_index: dict[str, int] = {}
    participant_x: dict[str, float] = {}
    header_mobs = []
    lifeline_mobs = []

    for i, name in enumerate(participants):
        x = start_x + i * SEQ_PARTICIPANT_GAP
        participant_index[name] = i
        participant_x[name] = x

        box = RoundedRectangle(
            width=1.8, height=0.6, corner_radius=0.1,
            color=PRIMARY, stroke_width=2,
        ).move_to([x, top_y, 0])
        label = Text(name, font_size=LABEL_FONT_SIZE, color=PRIMARY)
        label.move_to(box.get_center())
        header = VGroup(box, label)
        header_mobs.append(header)

        lifeline = DashedLine(
            [x, top_y - 0.35, 0],
            [x, bottom_y, 0],
            color=SEQ_LIFELINE_COLOR,
            stroke_width=1,
            dash_length=0.15,
        )
        lifeline_mobs.append(lifeline)

    all_parts: list = [*header_mobs, *lifeline_mobs]

    if action.title:
        title = Text(action.title, font_size=SUBTITLE_FONT_SIZE, color=PRIMARY)
        title.next_to(VGroup(*header_mobs), UP, buff=0.3)
        all_parts.append(title)
        scene.play(FadeIn(title), run_time=FADE_DURATION)

    scene.play(*[FadeIn(h) for h in header_mobs], run_time=FADE_DURATION)
    scene.play(*[Create(ll) for ll in lifeline_mobs], run_time=FADE_DURATION * 0.8)

    msg_y = top_y - 1.0
    for msg in messages:
        from_x = participant_x.get(msg.from_participant)
        to_x = participant_x.get(msg.to_participant)
        if from_x is None or to_x is None:
            continue

        color = resolve_color(msg.color) if msg.color else MUTED

        if msg.dashed:
            arrow = DashedLine(
                [from_x, msg_y, 0], [to_x, msg_y, 0],
                color=color, stroke_width=2, dash_length=0.12,
            )
        else:
            arrow = Arrow(
                [from_x, msg_y, 0], [to_x, msg_y, 0],
                color=color, stroke_width=2, tip_length=0.2, buff=0,
            )

        label = Text(msg.label, font_size=SUBLABEL_FONT_SIZE, color=color)
        label.next_to(arrow, UP, buff=0.08)

        all_parts.extend([arrow, label])
        scene.play(Create(arrow), FadeIn(label), run_time=0.6)
        scene.wait(SHORT_PAUSE)

        msg_y -= SEQ_MESSAGE_GAP

    diagram_group = VGroup(*all_parts)
    state.register(f"seq_diagram_{action.title or 'seq'}", diagram_group)
