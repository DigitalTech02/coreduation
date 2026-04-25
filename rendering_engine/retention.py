"""Retention-focused renderers: pulse, shake, dim, callout, emphasis, progress, camera, transitions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from manim import (
    DOWN,
    LEFT,
    RIGHT,
    UP,
    ORIGIN,
    ApplyMethod,
    FadeIn,
    FadeOut,
    RoundedRectangle,
    SurroundingRectangle,
    Text,
    VGroup,
    Write,
    Line,
    Arrow,
)

from rendering_engine.styles import (
    ACCENT,
    BG_COLOR,
    CALLOUT_BG_OPACITY,
    CALLOUT_FONT_SIZE,
    CALLOUT_LINE_COLOR,
    EMPHASIS_FONT_SIZE,
    FADE_DURATION,
    GLOW_OPACITY,
    MUTED,
    PRIMARY,
    PROGRESS_BAR_HEIGHT,
    PROGRESS_BAR_WIDTH,
    PROGRESS_BG_COLOR,
    PROGRESS_COLOR,
    PROGRESS_LABEL_FONT_SIZE,
    PROGRESS_Y_OFFSET,
    SMALL_FONT_SIZE,
    resolve_color,
)

if TYPE_CHECKING:
    from manim import Scene as ManimScene

    from rendering_engine.engine import SceneState

logger = logging.getLogger(__name__)

_PROGRESS_STATE_KEY = "__progress_ui__"


# ---------------------------------------------------------------------------
# pulse_element
# ---------------------------------------------------------------------------

def render_pulse_element(scene: "ManimScene", state: "SceneState", action) -> None:
    mob = state.get(action.target_id)
    if mob is None:
        logger.warning("pulse_element: target %r not found — skipping", action.target_id)
        return

    color = resolve_color(action.color) if action.color else None
    intensity = max(1.01, min(action.intensity, 1.5))
    original_center = mob.get_center().copy()

    mob.generate_target()
    mob.target.scale(intensity)
    mob.target.move_to(original_center)
    if color:
        mob.target.set_color(color)

    scene.play(
        ApplyMethod(mob.scale, intensity, {"about_point": original_center}),
        run_time=action.duration * 0.5,
    )
    scene.play(
        ApplyMethod(mob.scale, 1.0 / intensity, {"about_point": original_center}),
        run_time=action.duration * 0.5,
    )


# ---------------------------------------------------------------------------
# shake_element
# ---------------------------------------------------------------------------

def render_shake_element(scene: "ManimScene", state: "SceneState", action) -> None:
    mob = state.get(action.target_id)
    if mob is None:
        logger.warning("shake_element: target %r not found — skipping", action.target_id)
        return

    intensity = max(0.05, min(action.intensity, 0.5))
    original_pos = mob.get_center().copy()

    offsets = [
        RIGHT * intensity, LEFT * intensity * 1.2,
        RIGHT * intensity * 0.8, LEFT * intensity * 0.6,
    ]
    step_time = action.duration / (len(offsets) + 1)
    for offset in offsets:
        scene.play(
            mob.animate.move_to(original_pos + offset),
            run_time=step_time, rate_func=lambda t: t,
        )
    scene.play(
        mob.animate.move_to(original_pos),
        run_time=step_time, rate_func=lambda t: t,
    )


# ---------------------------------------------------------------------------
# focus_camera
# ---------------------------------------------------------------------------

def render_focus_camera(scene: "ManimScene", state: "SceneState", action) -> None:
    camera = getattr(scene, "camera", None)
    frame = getattr(camera, "frame", None)
    if frame is None:
        logger.warning("focus_camera: MovingCameraScene not available — skipping")
        return

    from config import CAMERA_MAX_ZOOM
    zoom = max(1.0, min(action.zoom, CAMERA_MAX_ZOOM))
    target_width = 14.2 / zoom

    if action.target_id:
        mob = state.get(action.target_id)
        if mob is None:
            logger.warning("focus_camera: target %r not found — skipping", action.target_id)
            return
        target_center = mob.get_center()
    elif action.x is not None and action.y is not None:
        target_center = [action.x, action.y, 0]
    else:
        target_center = ORIGIN

    scene.play(
        frame.animate.set_width(target_width).move_to(target_center),
        run_time=action.duration,
    )


# ---------------------------------------------------------------------------
# reset_camera
# ---------------------------------------------------------------------------

def render_reset_camera(scene: "ManimScene", state: "SceneState", action) -> None:
    camera = getattr(scene, "camera", None)
    frame = getattr(camera, "frame", None)
    if frame is None:
        logger.warning("reset_camera: MovingCameraScene not available — skipping")
        return

    scene.play(
        frame.animate.set_width(14.2).move_to(ORIGIN),
        run_time=action.duration,
    )


# ---------------------------------------------------------------------------
# show_progress
# ---------------------------------------------------------------------------

def _build_progress_group(label: str, current: int, total: int) -> VGroup:
    total = max(total, 1)
    fraction = min(current, total) / total

    bg_bar = RoundedRectangle(
        width=PROGRESS_BAR_WIDTH, height=PROGRESS_BAR_HEIGHT,
        corner_radius=PROGRESS_BAR_HEIGHT / 2,
        color=PROGRESS_BG_COLOR, fill_color=PROGRESS_BG_COLOR,
        fill_opacity=0.4, stroke_width=0.5,
    )
    fill_width = max(PROGRESS_BAR_HEIGHT, PROGRESS_BAR_WIDTH * fraction)
    fill_bar = RoundedRectangle(
        width=fill_width, height=PROGRESS_BAR_HEIGHT,
        corner_radius=PROGRESS_BAR_HEIGHT / 2,
        color=PROGRESS_COLOR, fill_color=PROGRESS_COLOR,
        fill_opacity=0.85, stroke_width=0,
    )
    fill_bar.align_to(bg_bar, LEFT)

    display_text = f"{label}  ({current}/{total})"
    lbl = Text(display_text, font_size=PROGRESS_LABEL_FONT_SIZE, color=MUTED)
    lbl.next_to(bg_bar, UP, buff=0.1)

    group = VGroup(bg_bar, fill_bar, lbl)
    group.move_to([0, PROGRESS_Y_OFFSET, 0])
    return group


def render_show_progress(scene: "ManimScene", state: "SceneState", action) -> None:
    from config import ENABLE_PROGRESS_UI
    if not ENABLE_PROGRESS_UI:
        return

    old = state.get(_PROGRESS_STATE_KEY)
    if old is not None:
        scene.play(FadeOut(old), run_time=0.2)
        state.unregister(_PROGRESS_STATE_KEY)

    group = _build_progress_group(action.label, action.current_step, action.total_steps)
    state.register(_PROGRESS_STATE_KEY, group, category="persistent")
    scene.play(FadeIn(group), run_time=0.3)


# ---------------------------------------------------------------------------
# update_progress
# ---------------------------------------------------------------------------

def render_update_progress(scene: "ManimScene", state: "SceneState", action) -> None:
    from config import ENABLE_PROGRESS_UI
    if not ENABLE_PROGRESS_UI:
        return

    old = state.get(_PROGRESS_STATE_KEY)
    if old is not None:
        scene.play(FadeOut(old), run_time=0.15)
        state.unregister(_PROGRESS_STATE_KEY)

    group = _build_progress_group(action.label, action.current_step, action.total_steps)
    state.register(_PROGRESS_STATE_KEY, group, category="persistent")
    scene.play(FadeIn(group), run_time=0.25)


# ---------------------------------------------------------------------------
# emphasize_text
# ---------------------------------------------------------------------------

_emphasis_counter = 0


def _find_vacant_y(state: "SceneState") -> float:
    """Find the best Y position for overlay text, avoiding existing visible objects.

    Screen ranges roughly y = -3.8 (bottom) to y = 3.5 (top).
    Returns the Y center for the emphasis text.
    """
    all_mobs = [
        m for k, m in state.objects.items()
        if not k.startswith("__progress") and not state.is_hidden(k)
    ]
    if not all_mobs:
        return 0.0

    tops = [m.get_top()[1] for m in all_mobs]
    bots = [m.get_bottom()[1] for m in all_mobs]
    content_top = max(tops)
    content_bot = min(bots)

    space_above = 3.5 - content_top
    space_below = content_bot - (-3.5)

    if space_above >= 1.2:
        return content_top + space_above / 2
    if space_below >= 1.2:
        return content_bot - space_below / 2
    return 3.0


def render_emphasize_text(scene: "ManimScene", state: "SceneState", action) -> None:
    from manim import ApplyWave, Circumscribe, GrowFromCenter, Indicate, Wiggle

    global _emphasis_counter
    _emphasis_counter += 1

    txt = Text(
        action.text, font_size=EMPHASIS_FONT_SIZE, color=ACCENT,
    )
    if txt.width > 12:
        txt.set_width(12)

    target_y = _find_vacant_y(state)
    txt.move_to([0, target_y, 0])

    if action.emphasis_type == "pop":
        txt.scale(0.3)
        scene.play(txt.animate.scale(1.0 / 0.3), run_time=action.duration * 0.4)
    else:
        scene.play(GrowFromCenter(txt), run_time=action.duration * 0.4)

    flourish = _emphasis_counter % 4
    try:
        if flourish == 0:
            scene.play(ApplyWave(txt, amplitude=0.1, run_time=0.5))
        elif flourish == 1:
            scene.play(Indicate(txt, color=PRIMARY, scale_factor=1.08), run_time=0.4)
        elif flourish == 2:
            scene.play(Wiggle(txt, scale_value=1.05, rotation_angle=0.02, run_time=0.4))
        else:
            scene.play(Circumscribe(txt, color=ACCENT, run_time=0.5, fade_out=True))
    except Exception:
        pass

    scene.wait(max(0.1, action.duration * 0.2))

    import uuid
    key = f"__emphasis_{uuid.uuid4().hex[:8]}__"
    state.register(key, txt, category="presentation")


# ---------------------------------------------------------------------------
# dim_except
# ---------------------------------------------------------------------------

def render_dim_except(scene: "ManimScene", state: "SceneState", action) -> None:
    keep_set = set(action.target_ids)
    anims = []
    for key, mob in state.objects.items():
        if key.startswith("__"):
            continue
        if key not in keep_set:
            anims.append(mob.animate.set_opacity(action.opacity))
    if anims:
        scene.play(*anims, run_time=action.duration)


# ---------------------------------------------------------------------------
# restore_opacity
# ---------------------------------------------------------------------------

def render_restore_opacity(scene: "ManimScene", state: "SceneState", action) -> None:
    anims = []
    for key, mob in state.objects.items():
        if key.startswith("__"):
            continue
        anims.append(mob.animate.set_opacity(1.0))
    if anims:
        scene.play(*anims, run_time=action.duration)


# ---------------------------------------------------------------------------
# add_callout
# ---------------------------------------------------------------------------

def render_add_callout(scene: "ManimScene", state: "SceneState", action) -> None:
    mob = state.get(action.target_id)
    if mob is None:
        logger.warning("add_callout: target %r not found — skipping", action.target_id)
        return

    lbl = Text(action.text, font_size=CALLOUT_FONT_SIZE, color=CALLOUT_LINE_COLOR)
    if lbl.width > 4.5:
        lbl.set_width(4.5)

    bg = SurroundingRectangle(
        lbl, color=CALLOUT_LINE_COLOR, fill_color=BG_COLOR,
        fill_opacity=CALLOUT_BG_OPACITY, buff=0.12, corner_radius=0.08,
    )
    callout = VGroup(bg, lbl)

    pos = action.position.lower()
    if pos == "left":
        callout.next_to(mob, LEFT, buff=0.3)
    elif pos == "right":
        callout.next_to(mob, RIGHT, buff=0.3)
    elif pos == "below":
        callout.next_to(mob, DOWN, buff=0.3)
    else:
        callout.next_to(mob, UP, buff=0.3)

    tip = Line(
        callout.get_edge_center(-callout.get_center() + mob.get_center()),
        mob.get_center(),
        color=CALLOUT_LINE_COLOR, stroke_width=1.5,
    )
    full_callout = VGroup(callout, tip)

    scene.play(FadeIn(full_callout), run_time=0.35)
    scene.wait(max(0.1, action.duration - 0.7))
    scene.play(FadeOut(full_callout), run_time=0.35)


# ---------------------------------------------------------------------------
# scene_transition
# ---------------------------------------------------------------------------

def render_scene_transition(scene: "ManimScene", state: "SceneState", action) -> None:
    if action.label:
        lbl = Text(action.label, font_size=32, color=PRIMARY)
        scene.play(FadeIn(lbl, shift=RIGHT * 0.5), run_time=action.duration * 0.4)
        scene.wait(action.duration * 0.3)
        scene.play(FadeOut(lbl, shift=LEFT * 0.5), run_time=action.duration * 0.3)
    else:
        scene.wait(max(0.1, action.duration * 0.3))
