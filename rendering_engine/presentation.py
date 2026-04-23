"""Presentation renderers — text blocks, bullet lists, code blocks, comparisons."""

from __future__ import annotations

from typing import TYPE_CHECKING

from manim import (
    DOWN,
    LEFT,
    RIGHT,
    UP,
    DashedLine,
    FadeIn,
    FadeOut,
    Line,
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
    CODE_FONT_SIZE,
    FADE_DURATION,
    FONT_MONO,
    HIGHLIGHT,
    LABEL_FONT_SIZE,
    MEDIUM_PAUSE,
    MUTED,
    PRIMARY,
    SECONDARY,
    SHORT_PAUSE,
    SMALL_FONT_SIZE,
    SUBTITLE_FONT_SIZE,
    TITLE_FONT_SIZE,
    WRITE_DURATION,
    resolve_color,
)

if TYPE_CHECKING:
    from manim import Scene as ManimScene

    from rendering_engine.engine import SceneState


# ---------------------------------------------------------------------------
# show_text_block
# ---------------------------------------------------------------------------

def render_show_text_block(scene: ManimScene, state: SceneState, action) -> None:
    parts = []

    if action.title:
        title = Text(action.title, font_size=TITLE_FONT_SIZE, color=PRIMARY)
        parts.append(title)

    if action.body:
        body = Text(
            action.body, font_size=BODY_FONT_SIZE, color=MUTED,
            line_spacing=1.4,
        )
        if len(action.body) > 100:
            body.set_width(min(body.width, 10))
        parts.append(body)

    if not parts:
        return

    group = VGroup(*parts).arrange(DOWN, buff=0.4)
    state.register(f"text_{action.title or 'block'}", group)
    scene.play(FadeIn(group), run_time=FADE_DURATION)


# ---------------------------------------------------------------------------
# show_bullet_list
# ---------------------------------------------------------------------------

def render_show_bullet_list(scene: ManimScene, state: SceneState, action) -> None:
    parts = []

    if action.title:
        title = Text(action.title, font_size=SUBTITLE_FONT_SIZE, color=PRIMARY)
        parts.append(title)

    bullets = []
    for item_text in action.items:
        bullet = Text(f"  •  {item_text}", font_size=BODY_FONT_SIZE, color=MUTED)
        if bullet.width > 10:
            bullet.set_width(10)
        bullets.append(bullet)

    bullet_group = VGroup(*bullets).arrange(DOWN, aligned_edge=LEFT, buff=0.25)
    parts.append(bullet_group)

    group = VGroup(*parts).arrange(DOWN, aligned_edge=LEFT, buff=0.5)
    state.register(f"bullets_{action.title or 'list'}", group)

    if action.title:
        scene.play(FadeIn(parts[0]), run_time=FADE_DURATION)

    if action.progressive:
        for bullet in bullets:
            scene.play(FadeIn(bullet, shift=RIGHT * 0.3), run_time=0.4)
            scene.wait(SHORT_PAUSE)
    else:
        scene.play(FadeIn(bullet_group), run_time=FADE_DURATION)


# ---------------------------------------------------------------------------
# show_code_block
# ---------------------------------------------------------------------------

def render_show_code_block(scene: ManimScene, state: SceneState, action) -> None:
    parts = []

    if action.title:
        title = Text(action.title, font_size=SUBTITLE_FONT_SIZE, color=PRIMARY)
        parts.append(title)

    code_lines = []
    for line_text in action.lines:
        line_mob = Text(line_text, font_size=CODE_FONT_SIZE, font=FONT_MONO, color=MUTED)
        code_lines.append(line_mob)

    code_group = VGroup(*code_lines).arrange(DOWN, aligned_edge=LEFT, buff=0.12)

    bg = SurroundingRectangle(
        code_group, color=MUTED, fill_color=BG_COLOR,
        fill_opacity=0.7, buff=0.3, corner_radius=0.1,
    )
    code_with_bg = VGroup(bg, code_group)
    parts.append(code_with_bg)

    group = VGroup(*parts).arrange(DOWN, buff=0.4)
    state.register(f"code_{action.title or 'block'}", group)

    scene.play(FadeIn(group), run_time=FADE_DURATION)

    if action.highlight_lines:
        for line_idx in action.highlight_lines:
            if 0 <= line_idx < len(code_lines):
                hl = SurroundingRectangle(
                    code_lines[line_idx], color=HIGHLIGHT, buff=0.05,
                )
                scene.play(FadeIn(hl), run_time=0.3)
                scene.wait(MEDIUM_PAUSE)
                scene.play(FadeOut(hl), run_time=0.2)


# ---------------------------------------------------------------------------
# show_comparison
# ---------------------------------------------------------------------------

def render_show_comparison(scene: ManimScene, state: SceneState, action) -> None:
    parts = []

    if action.title:
        title = Text(action.title, font_size=TITLE_FONT_SIZE, color=PRIMARY)
        parts.append(title)

    left_title = Text(action.left.title, font_size=SUBTITLE_FONT_SIZE, color=SECONDARY)
    left_items = VGroup(*[
        Text(f"•  {item}", font_size=SMALL_FONT_SIZE, color=MUTED) for item in action.left.items
    ]).arrange(DOWN, aligned_edge=LEFT, buff=0.2)
    left_col = VGroup(left_title, left_items).arrange(DOWN, buff=0.3)

    right_title = Text(action.right.title, font_size=SUBTITLE_FONT_SIZE, color=ACCENT)
    right_items = VGroup(*[
        Text(f"•  {item}", font_size=SMALL_FONT_SIZE, color=MUTED) for item in action.right.items
    ]).arrange(DOWN, aligned_edge=LEFT, buff=0.2)
    right_col = VGroup(right_title, right_items).arrange(DOWN, buff=0.3)

    columns = VGroup(left_col, right_col).arrange(RIGHT, buff=1.5)

    divider = DashedLine(
        columns.get_top() + UP * 0.2,
        columns.get_bottom() + DOWN * 0.2,
        color=MUTED,
    ).move_to(columns.get_center())

    comparison = VGroup(columns, divider)
    parts.append(comparison)

    group = VGroup(*parts).arrange(DOWN, buff=0.5)
    state.register(f"comparison_{action.title or 'cmp'}", group)

    scene.play(FadeIn(group), run_time=FADE_DURATION)
