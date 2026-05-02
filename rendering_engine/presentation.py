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
    SAFE_AREA_BOTTOM,
    SAFE_AREA_TOP,
    SECONDARY,
    BULLET_ITEM_PAUSE,
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


def _clamp_to_safe_area(group: VGroup) -> None:
    """Clamp a content group so its top stays below the topic header and
    scale down if it exceeds the safe area height."""
    g_top = group.get_top()[1]
    if g_top > SAFE_AREA_TOP:
        group.shift([0, SAFE_AREA_TOP - g_top, 0])
    safe_height = SAFE_AREA_TOP - SAFE_AREA_BOTTOM
    if group.height > safe_height:
        group.scale(safe_height / group.height)
        group.move_to([group.get_center()[0], (SAFE_AREA_TOP + SAFE_AREA_BOTTOM) / 2, 0])


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
    _clamp_to_safe_area(group)
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
    _clamp_to_safe_area(group)
    state.register(f"bullets_{action.title or 'list'}", group)

    if title_mob:
        scene.play(_next_title_anim(title_mob), run_time=0.6)
        _post_title_flourish(scene, title_mob)

    if action.progressive:
        for i, bullet in enumerate(bullets):
            scene.play(_next_bullet_anim(bullet, i))
            scene.wait(BULLET_ITEM_PAUSE)
    else:
        scene.play(FadeIn(bullet_group), run_time=FADE_DURATION)


# ---------------------------------------------------------------------------
# show_code_block
# ---------------------------------------------------------------------------

_CODE_MAX_HEIGHT = 5.2
_CODE_MAX_WIDTH = 11.0
_CODE_LINE_MAX_WIDTH = 10.5
_CODE_SCROLL_SPEED = 1.6


def _build_code_lines(lines: list[str], max_h: float):
    """Build code line mobjects, auto-reducing font if too many lines."""
    from rendering_engine.styles import WHITE

    n = len(lines)
    font_size = CODE_FONT_SIZE
    if n > 18:
        font_size = max(12, CODE_FONT_SIZE - 6)
    elif n > 12:
        font_size = max(14, CODE_FONT_SIZE - 4)
    elif n > 8:
        font_size = max(16, CODE_FONT_SIZE - 2)

    code_mobs = []
    for line_text in lines:
        lm = Text(line_text, font_size=font_size, font=FONT_MONO, color=WHITE)
        lm.set_opacity(0.88)
        if lm.width > _CODE_LINE_MAX_WIDTH:
            lm.set_width(_CODE_LINE_MAX_WIDTH)
        code_mobs.append(lm)

    buff = 0.10 if n > 12 else 0.12
    group = VGroup(*code_mobs).arrange(DOWN, aligned_edge=LEFT, buff=buff)

    if group.width > _CODE_MAX_WIDTH:
        group.scale_to_fit_width(_CODE_MAX_WIDTH)

    return code_mobs, group


def render_show_code_block(scene: ManimScene, state: SceneState, action) -> None:
    from rendering_engine.styles import WHITE

    parts = []
    title_mob = None

    if action.title:
        title_mob = Text(action.title, font_size=SUBTITLE_FONT_SIZE, color=PRIMARY)
        if title_mob.width > _CODE_MAX_WIDTH:
            title_mob.set_width(_CODE_MAX_WIDTH)
        parts.append(title_mob)

    max_h = _CODE_MAX_HEIGHT
    if title_mob:
        max_h -= (title_mob.height + 0.35)

    code_lines, code_group = _build_code_lines(action.lines, max_h)

    needs_scroll = code_group.height > max_h
    if not needs_scroll and code_group.height > max_h * 0.92:
        code_group.scale_to_fit_height(max_h * 0.92)
        needs_scroll = False

    if needs_scroll:
        visible_box_h = max_h
        bg = RoundedRectangle(
            width=min(code_group.width + 0.6, _CODE_MAX_WIDTH + 0.6),
            height=visible_box_h + 0.3,
            corner_radius=0.1,
            color=MUTED,
            fill_color=BG_COLOR,
            fill_opacity=0.8,
        )
        bg_center = bg.get_center()
        code_group.move_to(bg_center)
        code_group.align_to(bg, UP).shift(DOWN * 0.15)

        parts.append(VGroup(bg, code_group))
        content = VGroup(*parts).arrange(DOWN, buff=0.35)
        group = _with_shadow(content)
        _clamp_to_safe_area(group)
        state.register(f"code_{action.title or 'block'}", group)

        if title_mob:
            scene.play(_next_title_anim(title_mob), run_time=0.6)

        scene.play(FadeIn(bg), run_time=0.25)

        visible_lines = [
            lm for lm in code_lines
            if lm.get_center()[1] >= bg.get_bottom()[1] - 0.1
        ]
        for lm in visible_lines[:6]:
            scene.play(FadeIn(lm, shift=RIGHT * 0.2), run_time=0.10)
        remaining = [lm for lm in visible_lines[6:]]
        if remaining:
            scene.play(*[FadeIn(lm) for lm in remaining], run_time=0.15)

        overflow = code_group.height - visible_box_h
        if overflow > 0:
            scroll_time = overflow / _CODE_SCROLL_SPEED
            scene.play(
                code_group.animate.shift(UP * overflow),
                run_time=max(scroll_time, 1.5),
                rate_func=lambda t: t,
            )
            scene.wait(0.5)
    else:
        bg = SurroundingRectangle(
            code_group, color=MUTED, fill_color=BG_COLOR,
            fill_opacity=0.8, buff=0.3, corner_radius=0.1,
        )
        code_with_bg = VGroup(bg, code_group)
        parts.append(code_with_bg)

        content = VGroup(*parts).arrange(DOWN, buff=0.35)
        group = _with_shadow(content)
        _clamp_to_safe_area(group)
        state.register(f"code_{action.title or 'block'}", group)

        if title_mob:
            scene.play(_next_title_anim(title_mob), run_time=0.6)

        scene.play(FadeIn(bg), run_time=0.25)
        if len(code_lines) <= 8:
            for line_mob in code_lines:
                scene.play(FadeIn(line_mob, shift=RIGHT * 0.2), run_time=0.12)
        else:
            scene.play(*[FadeIn(lm) for lm in code_lines], run_time=0.4)

    if action.highlight_lines:
        scene.wait(0.1)
        for line_idx in action.highlight_lines:
            if 0 <= line_idx < len(code_lines):
                hl = SurroundingRectangle(
                    code_lines[line_idx], color=HIGHLIGHT, buff=0.08,
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
    _clamp_to_safe_area(group)
    state.register(f"comparison_{action.title or 'cmp'}", group)

    if title_mob:
        scene.play(_next_title_anim(title_mob), run_time=0.6)

    scene.play(FadeIn(left_col, shift=LEFT * 0.4), run_time=0.5)
    scene.play(GrowFromCenter(divider), run_time=0.3)
    scene.play(FadeIn(right_col, shift=RIGHT * 0.4), run_time=0.5)
