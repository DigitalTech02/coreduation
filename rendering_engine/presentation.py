"""Presentation renderers — text blocks, bullet lists, code blocks, comparisons.

Uses varied entrance animations (Write, GrowFromCenter, SpiralIn, ApplyWave,
Wiggle, Circumscribe) to keep text-heavy scenes visually engaging.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from manim import (
    DOWN,
    LEFT,
    RIGHT,
    UP,
    ApplyWave,
    Circumscribe,
    DashedLine,
    FadeIn,
    FadeOut,
    GrowFromCenter,
    Indicate,
    Line,
    RoundedRectangle,
    SpinInFromNothing,
    SurroundingRectangle,
    Text,
    VGroup,
    Wiggle,
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
    SHADOW_COLOR,
    SHADOW_OFFSET,
    SHADOW_OPACITY,
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

_anim_cycle_counter = 0


def _next_title_anim(mob):
    """Cycle through varied entrance animations for titles."""
    global _anim_cycle_counter
    _anim_cycle_counter += 1
    choice = _anim_cycle_counter % 4
    if choice == 0:
        return Write(mob, run_time=0.7)
    elif choice == 1:
        return GrowFromCenter(mob, run_time=0.6)
    elif choice == 2:
        return FadeIn(mob, shift=DOWN * 0.25, run_time=0.5)
    else:
        return FadeIn(mob, shift=RIGHT * 0.4, run_time=0.5)


def _next_bullet_anim(mob, index: int):
    """Varied entrance for progressive bullet items."""
    choice = index % 4
    if choice == 0:
        return FadeIn(mob, shift=RIGHT * 0.35, run_time=0.4)
    elif choice == 1:
        return FadeIn(mob, shift=UP * 0.2, run_time=0.4)
    elif choice == 2:
        return GrowFromCenter(mob, run_time=0.45)
    else:
        return FadeIn(mob, shift=LEFT * 0.15 + UP * 0.1, run_time=0.4)


def _post_title_flourish(scene, title_mob):
    """Subtle post-entrance flourish on a title to add polish."""
    global _anim_cycle_counter
    choice = _anim_cycle_counter % 3
    try:
        if choice == 0:
            scene.play(Indicate(title_mob, color=ACCENT, scale_factor=1.05), run_time=0.4)
        elif choice == 1:
            scene.play(ApplyWave(title_mob, amplitude=0.08, run_time=0.5))
        else:
            scene.play(Circumscribe(title_mob, color=PRIMARY, run_time=0.5, fade_out=True))
    except Exception:
        pass


def _with_shadow(content: VGroup) -> VGroup:
    """Wrap *content* in a VGroup with a drop shadow behind it."""
    shadow = content.copy()
    shadow.set_color(SHADOW_COLOR)
    shadow.set_fill(SHADOW_COLOR, opacity=SHADOW_OPACITY)
    shadow.set_stroke(width=0)
    shadow.shift(SHADOW_OFFSET[0] * RIGHT + SHADOW_OFFSET[1] * UP)
    return VGroup(shadow, content)


# ---------------------------------------------------------------------------
# show_text_block
# ---------------------------------------------------------------------------

def render_show_text_block(scene: ManimScene, state: SceneState, action) -> None:
    parts = []
    title_mob = None

    if action.title:
        title_mob = Text(action.title, font_size=TITLE_FONT_SIZE, color=PRIMARY)
        parts.append(title_mob)

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

    content = VGroup(*parts).arrange(DOWN, buff=0.4)
    group = _with_shadow(content)
    state.register(f"text_{action.title or 'block'}", group)

    if title_mob and len(parts) > 1:
        scene.play(_next_title_anim(title_mob), run_time=0.6)
        _post_title_flourish(scene, title_mob)
        scene.play(FadeIn(parts[1], shift=UP * 0.15), run_time=0.5)
    else:
        scene.play(_next_title_anim(parts[0]), run_time=0.6)


# ---------------------------------------------------------------------------
# show_bullet_list
# ---------------------------------------------------------------------------

def render_show_bullet_list(scene: ManimScene, state: SceneState, action) -> None:
    parts = []
    title_mob = None

    if action.title:
        title_mob = Text(action.title, font_size=SUBTITLE_FONT_SIZE, color=PRIMARY)
        parts.append(title_mob)

    bullets = []
    for item_text in action.items:
        bullet = Text(f"  •  {item_text}", font_size=BODY_FONT_SIZE, color=MUTED)
        if bullet.width > 10:
            bullet.set_width(10)
        bullets.append(bullet)

    bullet_group = VGroup(*bullets).arrange(DOWN, aligned_edge=LEFT, buff=0.25)
    parts.append(bullet_group)

    content = VGroup(*parts).arrange(DOWN, aligned_edge=LEFT, buff=0.5)
    group = _with_shadow(content)
    state.register(f"bullets_{action.title or 'list'}", group)

    if title_mob:
        scene.play(_next_title_anim(title_mob), run_time=0.6)
        _post_title_flourish(scene, title_mob)

    if action.progressive:
        for i, bullet in enumerate(bullets):
            scene.play(_next_bullet_anim(bullet, i))
            scene.wait(SHORT_PAUSE)
    else:
        scene.play(FadeIn(bullet_group), run_time=FADE_DURATION)


# ---------------------------------------------------------------------------
# show_code_block
# ---------------------------------------------------------------------------

def render_show_code_block(scene: ManimScene, state: SceneState, action) -> None:
    parts = []
    title_mob = None

    if action.title:
        title_mob = Text(action.title, font_size=SUBTITLE_FONT_SIZE, color=PRIMARY)
        parts.append(title_mob)

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

    content = VGroup(*parts).arrange(DOWN, buff=0.4)
    group = _with_shadow(content)
    state.register(f"code_{action.title or 'block'}", group)

    if title_mob:
        scene.play(_next_title_anim(title_mob), run_time=0.6)

    scene.play(FadeIn(bg), run_time=0.25)
    for i, line_mob in enumerate(code_lines):
        scene.play(FadeIn(line_mob, shift=RIGHT * 0.2), run_time=0.15)

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
    title_mob = None

    if action.title:
        title_mob = Text(action.title, font_size=TITLE_FONT_SIZE, color=PRIMARY)
        parts.append(title_mob)

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

    content = VGroup(*parts).arrange(DOWN, buff=0.5)
    group = _with_shadow(content)
    state.register(f"comparison_{action.title or 'cmp'}", group)

    if title_mob:
        scene.play(_next_title_anim(title_mob), run_time=0.6)

    scene.play(FadeIn(left_col, shift=LEFT * 0.4), run_time=0.5)
    scene.play(GrowFromCenter(divider), run_time=0.3)
    scene.play(FadeIn(right_col, shift=RIGHT * 0.4), run_time=0.5)
