"""Data display renderers — layer stacks, header breakdowns, tables, math."""

from __future__ import annotations

from typing import TYPE_CHECKING

from manim import (
    DOWN,
    LEFT,
    RIGHT,
    UP,
    FadeIn,
    Indicate,
    MathTex,
    Rectangle,
    RoundedRectangle,
    SurroundingRectangle,
    Text,
    VGroup,
    Write,
)

from rendering_engine.styles import (
    ACCENT,
    BG_COLOR,
    BODY_FONT_SIZE,
    FADE_DURATION,
    HEADER_FIELD_HEIGHT,
    HIGHLIGHT,
    LABEL_FONT_SIZE,
    LAYER_HEIGHT,
    LAYER_WIDTH,
    MEDIUM_PAUSE,
    MUTED,
    PRIMARY,
    SECONDARY,
    SHORT_PAUSE,
    SMALL_FONT_SIZE,
    SUBLABEL_FONT_SIZE,
    SUBTITLE_FONT_SIZE,
    TABLE_CELL_BUFF,
    TABLE_HEADER_COLOR,
    TABLE_HIGHLIGHT_COLOR,
    TABLE_ROW_ALT_COLOR,
    TITLE_FONT_SIZE,
    resolve_color,
)

if TYPE_CHECKING:
    from manim import Scene as ManimScene

    from rendering_engine.engine import SceneState

# ---------------------------------------------------------------------------
# OSI / TCP-IP layer stacks
# ---------------------------------------------------------------------------

_OSI_LAYERS = [
    ("7 — Application", "#e74c3c"),
    ("6 — Presentation", "#e67e22"),
    ("5 — Session", "#f1c40f"),
    ("4 — Transport", "#2ecc71"),
    ("3 — Network", "#1abc9c"),
    ("2 — Data Link", "#3498db"),
    ("1 — Physical", "#9b59b6"),
]

_TCP_IP_LAYERS = [
    ("Application", "#e74c3c"),
    ("Transport", "#2ecc71"),
    ("Internet", "#1abc9c"),
    ("Network Access", "#3498db"),
]


def render_show_layer_stack(scene: ManimScene, state: SceneState, action) -> None:
    layers_data = _OSI_LAYERS if action.stack_type.value == "osi" else _TCP_IP_LAYERS
    parts = []

    if action.title:
        title = Text(action.title, font_size=SUBTITLE_FONT_SIZE, color=PRIMARY)
        parts.append(title)

    layer_mobs = []
    for i, (name, color_hex) in enumerate(layers_data):
        rect = RoundedRectangle(
            width=LAYER_WIDTH, height=LAYER_HEIGHT,
            corner_radius=0.08, color=color_hex,
            fill_color=color_hex, fill_opacity=0.2,
            stroke_width=2,
        )
        label = Text(name, font_size=LABEL_FONT_SIZE, color=color_hex)
        label.move_to(rect.get_center())
        layer_mobs.append(VGroup(rect, label))

    stack = VGroup(*layer_mobs).arrange(DOWN, buff=0.08)
    parts.append(stack)

    group = VGroup(*parts).arrange(DOWN, buff=0.4)
    state.register(f"stack_{action.stack_type.value}", group)

    scene.play(FadeIn(group), run_time=FADE_DURATION)

    if action.highlight_layers:
        for layer_idx in action.highlight_layers:
            if 0 <= layer_idx < len(layer_mobs):
                scene.play(Indicate(layer_mobs[layer_idx], scale_factor=1.05), run_time=0.6)
                scene.wait(SHORT_PAUSE)


# ---------------------------------------------------------------------------
# Header / frame breakdown
# ---------------------------------------------------------------------------

def render_show_header_breakdown(scene: ManimScene, state: SceneState, action) -> None:
    parts = []

    if action.title:
        title = Text(action.title, font_size=SUBTITLE_FONT_SIZE, color=PRIMARY)
        parts.append(title)

    field_mobs = []
    for field in action.fields:
        width = max(1.2, len(field.name) * 0.18 + 0.6)
        rect = Rectangle(
            width=width, height=HEADER_FIELD_HEIGHT,
            color=SECONDARY, stroke_width=2,
            fill_color=SECONDARY, fill_opacity=0.1,
        )
        name_text = Text(field.name, font_size=SUBLABEL_FONT_SIZE, color=SECONDARY)
        name_text.move_to(rect.get_center())

        field_group = VGroup(rect, name_text)

        if field.size:
            size_text = Text(field.size, font_size=SUBLABEL_FONT_SIZE * 0.8, color=MUTED)
            size_text.next_to(rect, DOWN, buff=0.08)
            field_group.add(size_text)

        field_mobs.append(field_group)

    header_row = VGroup(*field_mobs).arrange(RIGHT, buff=0.04)

    if header_row.width > 12:
        header_row.set_width(12)

    parts.append(header_row)
    group = VGroup(*parts).arrange(DOWN, buff=0.4)
    state.register(f"header_{action.title or 'breakdown'}", group)

    scene.play(FadeIn(group), run_time=FADE_DURATION)

    for i, field in enumerate(action.fields):
        should_highlight = field.highlight or (
            action.highlight_field and field.name == action.highlight_field
        )
        if should_highlight and i < len(field_mobs):
            hl = SurroundingRectangle(field_mobs[i], color=HIGHLIGHT, buff=0.05)
            group.add(hl)
            scene.play(FadeIn(hl), run_time=0.3)
            scene.wait(MEDIUM_PAUSE)


# ---------------------------------------------------------------------------
# Table
# ---------------------------------------------------------------------------

def render_show_table(scene: ManimScene, state: SceneState, action) -> None:
    parts = []

    if action.title:
        title = Text(action.title, font_size=SUBTITLE_FONT_SIZE, color=PRIMARY)
        parts.append(title)

    n_cols = len(action.headers)
    col_width = min(2.2, 11.0 / max(n_cols, 1))

    def _make_row(cells: list[str], is_header: bool = False, is_highlighted: bool = False):
        row_cells = []
        for cell_text in cells:
            color = TABLE_HEADER_COLOR if is_header else MUTED
            font_size = LABEL_FONT_SIZE if is_header else SMALL_FONT_SIZE
            txt = Text(str(cell_text), font_size=font_size, color=color)
            cell_bg = Rectangle(
                width=col_width, height=0.5,
                stroke_width=0.5, color=MUTED,
                fill_color=TABLE_HEADER_COLOR if is_header else BG_COLOR,
                fill_opacity=0.15 if is_header else 0.0,
            )
            txt.move_to(cell_bg.get_center())
            if txt.width > col_width - 0.2:
                txt.set_width(col_width - 0.2)
            row_cells.append(VGroup(cell_bg, txt))
        return VGroup(*row_cells).arrange(RIGHT, buff=0)

    header_row = _make_row(action.headers, is_header=True)
    rows = [header_row]

    for i, row_data in enumerate(action.rows):
        is_hl = row_data.highlight or (action.highlight_row is not None and i == action.highlight_row)
        rows.append(_make_row(row_data.cells, is_highlighted=is_hl))

    table = VGroup(*rows).arrange(DOWN, buff=0)
    parts.append(table)

    group = VGroup(*parts).arrange(DOWN, buff=0.4)
    state.register(f"table_{action.title or 'tbl'}", group)

    scene.play(FadeIn(group), run_time=FADE_DURATION)

    if action.highlight_row is not None and 0 <= action.highlight_row < len(action.rows):
        target_row = rows[action.highlight_row + 1]
        hl = SurroundingRectangle(target_row, color=TABLE_HIGHLIGHT_COLOR, buff=0.03)
        group.add(hl)
        scene.play(FadeIn(hl), run_time=0.3)
        scene.wait(MEDIUM_PAUSE)


# ---------------------------------------------------------------------------
# Math expression
# ---------------------------------------------------------------------------

def render_show_math(scene: ManimScene, state: SceneState, action) -> None:
    import logging as _log

    parts = []

    if action.label:
        label = Text(action.label, font_size=BODY_FONT_SIZE, color=PRIMARY)
        parts.append(label)

    try:
        math_mob = MathTex(action.expression, font_size=TITLE_FONT_SIZE * 1.2, color=ACCENT)
    except Exception as exc:
        _log.getLogger(__name__).warning(
            "MathTex failed for '%s', falling back to Text: %s",
            action.expression, exc,
        )
        display = action.expression.replace("\\", "")
        math_mob = Text(display, font_size=TITLE_FONT_SIZE, color=ACCENT)

    parts.append(math_mob)

    group = VGroup(*parts).arrange(DOWN, buff=0.4)
    state.register(f"math_{action.label or 'expr'}", group)

    scene.play(Write(math_mob), run_time=0.8)
    if action.label:
        scene.play(FadeIn(parts[0]), run_time=FADE_DURATION)
