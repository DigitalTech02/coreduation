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
    FONT_SANS,
    HIGHLIGHT,
    LABEL_FONT_SIZE,
    MEDIUM_PAUSE,
    MIN_FONT_BODY,
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
    """Clamp a content group so it fits inside the safe area on all sides."""
    from rendering_engine.styles import SAFE_AREA_LEFT, SAFE_AREA_RIGHT

    safe_height = SAFE_AREA_TOP - SAFE_AREA_BOTTOM
    safe_width = SAFE_AREA_RIGHT - SAFE_AREA_LEFT

    # Scale down to fit width (file22-style left-edge-clipped comparison bug:
    # 2-column layouts with long titles + 1.5-unit gutter often exceed
    # safe_width, then no shift can recover them — they need a scale).
    if group.width > safe_width:
        group.scale(safe_width / group.width)

    # Top clamp
    g_top = group.get_top()[1]
    if g_top > SAFE_AREA_TOP:
        group.shift([0, SAFE_AREA_TOP - g_top, 0])

    # Height scale + recenter vertically if still too tall
    if group.height > safe_height:
        group.scale(safe_height / group.height)
        group.move_to([group.get_center()[0], (SAFE_AREA_TOP + SAFE_AREA_BOTTOM) / 2, 0])

    # Horizontal recenter if escaped sides
    g_left = group.get_left()[0]
    g_right = group.get_right()[0]
    if g_left < SAFE_AREA_LEFT:
        group.shift([SAFE_AREA_LEFT - g_left, 0, 0])
    elif g_right > SAFE_AREA_RIGHT:
        group.shift([SAFE_AREA_RIGHT - g_right, 0, 0])


def fit_text_to_box(
    text: str,
    max_width: float,
    max_height: float,
    *,
    ideal_font: int = BODY_FONT_SIZE,
    min_font: int = MIN_FONT_BODY,
    color=MUTED,
    weight: str = "NORMAL",
    line_spacing: float = 1.3,
) -> Text | None:
    """Build a Text mobject that wraps and fits inside ``(max_width, max_height)``.

    Strategy:
      1. Try ``ideal_font`` with word-wrap targeting ``max_width``.
      2. Shrink font in 2pt steps down to ``min_font`` if it's too tall.
      3. Return ``None`` if even the smallest size doesn't fit — caller
         should split the content into multiple scenes rather than render
         unreadable text.

    The character-width estimate is heuristic (sans-serif at ~0.0062 manim
    units per pt-char-width) but consistently err's slightly toward more
    aggressive wrapping, which is the failure mode we want.
    """
    import textwrap as _tw

    def _chars_per_line(font_size: int) -> int:
        char_w = max(0.0001, font_size * 0.0062)
        return max(10, int(max_width / char_w))

    for fs in range(ideal_font, min_font - 1, -2):
        cpl = _chars_per_line(fs)
        wrapped_lines = _tw.wrap(text, width=cpl) or [text]
        wrapped = "\n".join(wrapped_lines)
        mob = Text(wrapped, font_size=fs, color=color, weight=weight,
                   line_spacing=line_spacing)
        if mob.width > max_width:
            mob.set_width(max_width)
        if mob.height <= max_height:
            return mob
    return None


def _avoid_collision(scene, state, group: VGroup, margin: float = 0.20) -> VGroup:
    """If *group* would overlap visible diagram objects, try in order:

    1. Relocate to the largest vacant region (above / below / left / right
       of the diagram), scale to fit, wrap in a card.
    2. If no region big enough exists, hide the colliding persistent
       objects entirely for the duration of this slide. The next scene's
       ``_auto_toggle_persistent`` will restore them when needed.

    The two-state rule (per user feedback): full diagram OR hidden — never
    "diagram + text awkwardly stacked". Always wrap relocated/hidden-bg
    text in a Manim card so it reads as a contained block.
    """
    from rendering_engine.engine import BBox

    bbox = BBox(
        group.get_left()[0],
        group.get_right()[0],
        group.get_bottom()[1],
        group.get_top()[1],
    )
    colliders = state.overlaps_any(bbox, margin=margin)
    if not colliders:
        return _wrap_in_card(scene, group, opaque=False)

    region = state.find_largest_vacant_region(min_width=2.5, min_height=0.8)

    # ------------------------------------------------------------------
    # Path 1: usable vacant region exists — relocate + scale + card.
    # ------------------------------------------------------------------
    if region is not None:
        avail_w = (region.right - region.left) - 2 * margin
        avail_h = (region.top - region.bottom) - 2 * margin
        if avail_w > 0 and avail_h > 0:
            scale = min(
                1.0,
                avail_w / max(0.1, group.width),
                avail_h / max(0.1, group.height),
            )
            if scale < 0.99:
                group.scale(max(0.65, scale * 0.97))

            target_x = (region.left + region.right) / 2
            target_y = (region.bottom + region.top) / 2
            cx, cy = group.get_center()[0], group.get_center()[1]
            group.shift([target_x - cx, target_y - cy, 0])

            # Re-check after relocation — if the region was estimated and
            # the text actually still overlaps something, fall through to
            # path 2 instead of leaving a broken layout on screen.
            new_bbox = BBox(
                group.get_left()[0], group.get_right()[0],
                group.get_bottom()[1], group.get_top()[1],
            )
            if not state.overlaps_any(new_bbox, margin=margin):
                return _wrap_in_card(scene, group, opaque=True)

    # ------------------------------------------------------------------
    # Path 2: canvas too crowded — hide the persistent topology, recentre
    # the text to mid-canvas, and wrap in a fully opaque card.  The next
    # scene's _auto_toggle_persistent restores topology if still needed.
    # ------------------------------------------------------------------
    try:
        state.hide_persistent(scene)
    except Exception:
        pass

    # Recenter the (possibly already scaled) group to the canvas centre.
    cx, cy = group.get_center()[0], group.get_center()[1]
    group.shift([0 - cx, 0 - cy, 0])
    return _wrap_in_card(scene, group, opaque=True)


def _wrap_in_card(
    scene, group: VGroup, *, opaque: bool,
    min_width: float | None = None,
    min_height: float | None = None,
) -> VGroup:
    """Wrap *group* in a rounded-rect card with isometric drop-shadow.

    ``opaque=True`` uses near-opaque fill so the card occludes anything
    behind it cleanly (used when the text was relocated or topology was
    hidden).  ``opaque=False`` is a subtle border-only treatment used
    when no overlap was detected.

    ``min_width`` / ``min_height`` enforce a minimum card size — useful in
    shorts mode where a one-line text block would otherwise produce a thin
    card lost in the canvas.  When the natural card is smaller than the
    minimum, the card grows but the inner content stays centered.
    """
    from manim import FadeIn, RoundedRectangle

    from rendering_engine.styles import make_isometric_shadow

    if opaque:
        w = max(group.width + 0.55, min_width or 0.0)
        h = max(group.height + 0.45, min_height or 0.0)
        card = RoundedRectangle(
            width=w,
            height=h,
            corner_radius=0.18 if (min_width or min_height) else 0.12,
            stroke_width=2.0 if (min_width or min_height) else 1.5,
            stroke_color=MUTED,
            stroke_opacity=0.55,
            fill_color=BG_COLOR,
            fill_opacity=0.96,
        )
    else:
        card = RoundedRectangle(
            width=group.width + 0.4,
            height=group.height + 0.3,
            corner_radius=0.10,
            stroke_width=1.0,
            stroke_color=MUTED,
            stroke_opacity=0.30,
            fill_color=BG_COLOR,
            fill_opacity=0.0,
        )
    card.move_to(group.get_center())
    card_with_shadow = make_isometric_shadow(card, depth=0.10, layers=2, opacity=0.30)
    try:
        scene.play(FadeIn(card_with_shadow), run_time=0.20)
    except Exception:
        pass
    return VGroup(card_with_shadow, group)


# ---------------------------------------------------------------------------
# show_text_block
# ---------------------------------------------------------------------------

def render_show_text_block(scene: ManimScene, state: SceneState, action) -> None:
    parts = []
    title_mob = None

    # Shorts mode: BIG, bold, dominant text on a 9:16 canvas — kept narrow
    # enough to clear the right-side button column (Like / Comment / Share)
    # that platform UIs overlay on the right ~10% of the canvas.  Phone
    # comfortable-read minimum is ~70pt; current scales produce
    # title=112pt body=68pt bullet=62pt — all comfortably above threshold.
    is_shorts = getattr(state, "mode", "long") == "shorts"
    title_size = int(TITLE_FONT_SIZE * 2.8) if is_shorts else TITLE_FONT_SIZE   # 40 → 112
    body_size = int(BODY_FONT_SIZE * 2.6) if is_shorts else BODY_FONT_SIZE      # 26 → 68
    body_max_width = 6.6 if is_shorts else 10.0
    body_break_threshold = 40 if is_shorts else 100

    if action.title:
        title_mob = Text(
            action.title, font_size=title_size, color=PRIMARY, weight="BOLD",
        )
        # Title can't exceed canvas width either.  In shorts the safe width
        # is ~6.6 units (leaves a 0.7-unit buffer on each side for the
        # platform UI button columns); horizontal long-form is ~12.
        max_title_width = 6.6 if is_shorts else 12.0
        if title_mob.width > max_title_width:
            title_mob.set_width(max_title_width)
        parts.append(title_mob)

    if action.body:
        body = Text(
            action.body, font_size=body_size, color=MUTED,
            line_spacing=1.4, weight="MEDIUM" if is_shorts else "NORMAL",
        )
        if len(action.body) > body_break_threshold:
            body.set_width(min(body.width, body_max_width))
        parts.append(body)

    if not parts:
        return

    buff = 0.6 if is_shorts else 0.4
    content = VGroup(*parts).arrange(DOWN, buff=buff)
    group = _with_shadow(content)
    _clamp_to_safe_area(group)
    if not is_shorts:
        # Long-form: route through collision-avoidance + card wrap.
        group = _avoid_collision(scene, state, group)
    else:
        # Shorts: text sits DIRECTLY on the mood-colored panel (the
        # background panel IS the visual container).  No dark card chrome
        # needed — that was the old "small card on dark canvas" model that
        # we deliberately replaced.  Forces title/body to white-bold for
        # contrast against the saturated panel color.
        from manim import WHITE as _WHITE
        for part in parts:
            try:
                part.set_color(_WHITE)
            except Exception:
                pass
        group.move_to([0, -0.5, 0])
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

    # Shorts mode: bigger fonts so the bullet card fills the vertical canvas.
    # Title at 32 × 2.3 = 74pt; bullets at 26 × 2.4 = 62pt.  Both above
    # the 70pt phone-comfort threshold for the title and just under for
    # bullets (kept smaller so the title still reads as the header).
    is_shorts = getattr(state, "mode", "long") == "shorts"
    bullet_title_size = int(SUBTITLE_FONT_SIZE * 2.3) if is_shorts else SUBTITLE_FONT_SIZE

    if action.title:
        title_mob = Text(
            action.title, font_size=bullet_title_size, color=PRIMARY,
            weight="BOLD" if is_shorts else "NORMAL",
        )
        parts.append(title_mob)

    bullet_size = int(BODY_FONT_SIZE * 2.4) if is_shorts else BODY_FONT_SIZE   # 26 → 62
    bullet_max_w = 6.6 if is_shorts else 10.0
    bullets = []
    for item_text in action.items:
        bullet = Text(
            f"  •  {item_text}", font_size=bullet_size, color=MUTED,
            weight="MEDIUM" if is_shorts else "NORMAL",
        )
        if bullet.width > bullet_max_w:
            bullet.set_width(bullet_max_w)
        bullets.append(bullet)

    bullet_buff = 0.4 if is_shorts else 0.25
    bullet_group = VGroup(*bullets).arrange(DOWN, aligned_edge=LEFT, buff=bullet_buff)
    parts.append(bullet_group)

    parts_buff = 0.7 if is_shorts else 0.5
    content = VGroup(*parts).arrange(DOWN, aligned_edge=LEFT, buff=parts_buff)
    group = _with_shadow(content)
    _clamp_to_safe_area(group)
    if not is_shorts:
        group = _avoid_collision(scene, state, group)
    else:
        # Shorts: bullet list sits directly on the mood panel — no dark
        # card chrome.  Force title to bright accent (cyan-ish white) and
        # bullets to white for max contrast.
        from manim import WHITE as _WHITE
        try:
            if title_mob is not None:
                title_mob.set_color(_WHITE)
            for bullet in bullets:
                bullet.set_color(_WHITE)
        except Exception:
            pass
        group.move_to([0, -0.5, 0])
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
    """Build code line mobjects sized so the whole block fits in *max_h*.

    Manim doesn't clip child mobjects to a parent bounding box, so the
    previous "scroll if too tall" path produced visually scrambled output:
    the scroll animation shifted lines up but the off-box ones remained
    visible at their new positions, overlapping the in-box ones.

    Instead: pick a font size and per-line buffer that GUARANTEES the
    block fits inside ``max_h``. If the smallest readable size still
    overflows, the renderer's scroll fallback handles it (and even there
    we now hide the off-box lines).
    """
    from rendering_engine.styles import WHITE

    n = max(1, len(lines))
    target_h = max(0.5, max_h - 0.3)  # leave room for buffer/border

    # Find a (font_size, buff) that fits. Search from ideal downward.
    chosen_font = CODE_FONT_SIZE
    chosen_buff = 0.12
    for font_size, buff in (
        (CODE_FONT_SIZE, 0.14),
        (CODE_FONT_SIZE, 0.12),
        (CODE_FONT_SIZE - 2, 0.12),
        (CODE_FONT_SIZE - 4, 0.10),
        (CODE_FONT_SIZE - 6, 0.08),
        (CODE_FONT_SIZE - 8, 0.07),
        (12, 0.06),
    ):
        if font_size < 12:
            continue
        # rough Manim line height ≈ font_size * 0.018 + tiny margin
        approx_line_h = font_size * 0.018 + 0.05
        approx_total = n * approx_line_h + (n - 1) * buff
        if approx_total <= target_h:
            chosen_font, chosen_buff = font_size, buff
            break

    # First, build a reference line so we can measure proper row height.
    # Empty / whitespace-only lines render as ~zero-height mobjects in Manim
    # (even " " is shorter than a normal line), which collapses arrange()'s
    # row spacing and causes neighbouring code lines to overlap on screen.
    # We use the reference height for any blank line so the row takes its
    # full vertical slot but stays invisible.
    from manim import Rectangle
    ref = Text("Ag", font_size=chosen_font, font=FONT_MONO, color=WHITE)
    ref_h = ref.height

    code_mobs = []
    for line_text in lines:
        if line_text.strip():
            lm = Text(line_text, font_size=chosen_font, font=FONT_MONO, color=WHITE)
            lm.set_opacity(0.88)
        else:
            # Invisible spacer with proper line height so arrange() lays out
            # subsequent lines at the correct y-offset.
            lm = Rectangle(width=0.01, height=ref_h, stroke_width=0, fill_opacity=0)
        if lm.width > _CODE_LINE_MAX_WIDTH:
            lm.set_width(_CODE_LINE_MAX_WIDTH)
        code_mobs.append(lm)

    group = VGroup(*code_mobs).arrange(DOWN, aligned_edge=LEFT, buff=chosen_buff)

    if group.width > _CODE_MAX_WIDTH:
        group.scale_to_fit_width(_CODE_MAX_WIDTH)

    # Final safety: if our heuristic was wrong, scale the entire group to fit.
    if group.height > target_h:
        group.scale_to_fit_height(target_h)

    return code_mobs, group


def render_show_code_block(scene: ManimScene, state: SceneState, action) -> None:
    from rendering_engine.styles import WHITE

    is_shorts = getattr(state, "mode", "long") == "shorts"
    parts = []
    title_mob = None

    if action.title:
        # Code-block title: 32 × 1.9 = 61pt in shorts (was 48pt — too small).
        title_size = int(SUBTITLE_FONT_SIZE * 1.9) if is_shorts else SUBTITLE_FONT_SIZE
        title_mob = Text(
            action.title, font_size=title_size,
            color=WHITE if is_shorts else PRIMARY,
            weight="BOLD" if is_shorts else "NORMAL",
        )
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

    # _build_code_lines now adaptively sizes content to fit, so needs_scroll
    # should be False in practice. If it somehow isn't (e.g. user passes very
    # long single lines), force the group to scale rather than enter the
    # scroll path — Manim doesn't clip to a bounding box, so scrolling
    # produces overlapping text rather than a clean scroll.
    if needs_scroll:
        code_group.scale_to_fit_height(max_h * 0.95)
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
        if is_shorts:
            # Traffic-light window chrome in shorts mode (macOS-style).
            # Three colored dots in the top-left + a darker title bar above
            # the code, on a chunky dark window bg.  Matches the user's
            # reference visuals (Image 1) where code blocks read as IDE
            # windows, not floating text on dark.
            from manim import RoundedRectangle as _RR2, Circle as _Circle

            window_w = max(code_group.width + 0.9, 6.8)
            chrome_h = 0.55
            window_h = code_group.height + chrome_h + 0.6

            window_bg = _RR2(
                width=window_w, height=window_h, corner_radius=0.20,
                color="#2a2a2e", stroke_width=3,
                fill_color="#16161a", fill_opacity=0.98,
            )
            chrome_bar = _RR2(
                width=window_w - 0.04, height=chrome_h, corner_radius=0.18,
                color="#2a2a2e", stroke_width=0,
                fill_color="#2a2a2e", fill_opacity=1.0,
            )
            chrome_bar.align_to(window_bg, UP).shift(DOWN * 0.02)

            dots = VGroup()
            for i, dot_color in enumerate(("#ff5f56", "#ffbd2e", "#27c93f")):
                d = _Circle(radius=0.10, color=dot_color, stroke_width=0)
                d.set_fill(dot_color, opacity=1.0)
                d.move_to(chrome_bar.get_left() + RIGHT * (0.35 + i * 0.32))
                dots.add(d)

            code_group.next_to(chrome_bar, DOWN, buff=0.18)
            code_group.align_to(window_bg, LEFT).shift(RIGHT * 0.35)

            code_with_bg = VGroup(window_bg, chrome_bar, dots, code_group)
            parts.append(code_with_bg)
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
    group = _avoid_collision(scene, state, group)
    state.register(f"comparison_{action.title or 'cmp'}", group)

    if title_mob:
        scene.play(_next_title_anim(title_mob), run_time=0.6)

    scene.play(FadeIn(left_col, shift=LEFT * 0.4), run_time=0.5)
    scene.play(GrowFromCenter(divider), run_time=0.3)
    scene.play(FadeIn(right_col, shift=RIGHT * 0.4), run_time=0.5)
