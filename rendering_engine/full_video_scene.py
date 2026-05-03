"""Single Manim Scene: title card, scene segments, paced waits, fade transitions.

Used by the semantic engine to render the whole video in one pass.
Handles cross-scene persistence so topology objects survive into scenes
that reference them (e.g. send_packet from a node created earlier).
"""

from __future__ import annotations

import logging
from typing import Any

from manim import DOWN, LEFT, ORIGIN, RIGHT, UP, Dot, FadeIn, FadeOut, Line, Text, VGroup, WHITE

from rendering_engine.engine import SceneState, _dispatch_action, _rebuild_action
from rendering_engine.styles import (
    CATEGORY_ACCENT,
    GLOW_OPACITY,
    MUTED,
    PRIMARY,
    SCENE_FADE_OUT_SECONDS,
    SCENE_GAP_SECONDS,
    SUBTITLE_FONT_SIZE,
    TITLE_CARD_SECONDS,
    TITLE_FADE_IN,
    TITLE_FADE_OUT,
    TITLE_FONT_SIZE,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cross-scene look-ahead
# ---------------------------------------------------------------------------

def _collect_future_refs(scenes: list[dict]) -> list[set[str]]:
    """For each scene index *i*, return the set of object IDs referenced
    by any scene after *i* (i+1 … n-1).

    This lets the renderer decide which persistent objects to *keep* at the
    end of scene *i* instead of fading them out.
    """
    n = len(scenes)

    refs_per_scene: list[set[str]] = []
    for sc in scenes:
        refs: set[str] = set()
        for a in sc.get("actions", []):
            for key in ("from", "to", "id", "from_node", "to_node",
                        "parent_id", "region_id", "target_id"):
                val = a.get(key)
                if val:
                    refs.add(val)
            for tid in a.get("target_ids", []):
                if tid:
                    refs.add(tid)
            for hop in a.get("hops", []):
                nid = hop.get("node_id")
                if nid:
                    refs.add(nid)
        refs_per_scene.append(refs)

    future: list[set[str]] = []
    suffix: set[str] = set()
    for i in range(n - 1, -1, -1):
        future.append(set(suffix))
        suffix |= refs_per_scene[i]
    future.reverse()
    return future


# ---------------------------------------------------------------------------
# Persistent object visibility toggle
# ---------------------------------------------------------------------------

def _extract_scene_refs(actions: list[dict]) -> set[str]:
    """Extract all object IDs referenced by a scene's actions."""
    refs: set[str] = set()
    for a in actions:
        for key in ("from", "to", "id", "from_node", "to_node",
                    "parent_id", "region_id", "target_id"):
            val = a.get(key)
            if val:
                refs.add(val)
        for tid in a.get("target_ids", []):
            if tid:
                refs.add(tid)
        for hop in a.get("hops", []):
            nid = hop.get("node_id")
            if nid:
                refs.add(nid)
    return refs


# Actions that take over the full canvas as a "slide".  When a scene contains
# any of these, persistent topology objects from prior scenes are hidden so the
# slide content has the canvas to itself — otherwise the lifelines / table
# rows / code block render on top of (or behind) leftover nodes.
_FULL_CANVAS_TYPES = frozenset({
    "show_sequence_diagram",
    "show_table",
    "show_code_block",
    "show_layer_stack",
    "show_header_breakdown",
    "show_chart",
    "show_comparison",
    "show_text_block",
    "show_bullet_list",
})


def _scene_has_full_canvas_action(actions: list[dict]) -> bool:
    return any(a.get("type") in _FULL_CANVAS_TYPES for a in actions)


def _toggle_persistent_topic_header(state: SceneState, suppress: bool) -> None:
    """Hide or show the persistent topic header.

    Slide-style scenes (full canvas) suppress it so the scene title doesn't
    fight with a tiny duplicate header at the top edge.  The header keeps its
    anchor updater either way — only opacity changes.
    """
    header = state.objects.get(_TOPIC_HEADER_KEY)
    if header is None:
        return
    target = 0.0 if suppress else 1.0
    try:
        for sub in header.submobjects:
            sub.set_opacity(target)
        header.set_opacity(target)
    except Exception:
        pass


def _auto_toggle_persistent(scene: Any, state: SceneState, actions: list[dict]) -> None:
    """Hide or restore persistent objects based on whether this scene uses them.

    When a scene is purely presentation (tables, text, bullets) with no
    references to persistent topology/node objects, those objects are faded
    to invisible so they don't clutter the slide.  They're restored when a
    later scene references them again.
    """
    persistent_ids = {
        k for k, cat in state._categories.items()
        if cat == "persistent"
        and not k.startswith("__progress")
        and not k.startswith("__")
    }
    if not persistent_ids:
        return

    scene_refs = _extract_scene_refs(actions)
    scene_uses_persistent = bool(persistent_ids & scene_refs)

    # Slide-style scenes hide leftover topology even if a stray retention
    # action references it — the visual goal is a clean stage for the slide.
    if _scene_has_full_canvas_action(actions):
        scene_uses_persistent = False

    if scene_uses_persistent:
        if state._hidden:
            state.restore_persistent(scene)
        try:
            from rendering_engine.easing import add_parallax
            existing = getattr(state, "_parallax_updater", None)
            if existing is None:
                updater = add_parallax(scene, amplitude=0.03, period=18.0,
                                       enable_zoom_breathing=False)
                state._parallax_updater = updater
        except Exception:
            pass
    else:
        if not state._hidden:
            state.hide_persistent(scene)
        try:
            from rendering_engine.easing import remove_parallax
            existing = getattr(state, "_parallax_updater", None)
            if existing is not None:
                remove_parallax(scene, existing)
                state._parallax_updater = None
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_full_video_construct(scene: Any, data: dict) -> None:
    """Build the full animation: title, then each scene with narration pacing."""
    from config import ENABLE_SUBTITLES, SUBTITLE_MAX_WORDS, SUBTITLE_MODE

    topic = data.get("topic", "")
    scenes: list[dict] = data.get("scenes", [])

    subtitle = data.get("title_card_subtitle", "")
    category = data.get("category", "")

    from rendering_engine.branding import add_watermark, play_intro_card, play_outro_card
    play_intro_card(scene, category)

    _play_title_card(scene, topic, subtitle, category)

    future_refs = _collect_future_refs(scenes)
    state = SceneState()
    add_watermark(scene, state, category)

    _add_persistent_topic_header(scene, state, topic, category)
    _add_corner_decorations(scene, state, category)

    n = len(scenes)

    for i, sc in enumerate(scenes):
        actions = sc.get("actions", [])
        narration = sc.get("narration", "")
        audio_dur = float(
            sc.get("audio_duration") or sc.get("estimated_duration") or 10.0
        )

        _auto_toggle_persistent(scene, state, actions)
        _toggle_persistent_topic_header(
            state, suppress=_scene_has_full_canvas_action(actions),
        )

        t0 = scene.renderer.time

        for action_dict in actions:
            action = _rebuild_action(action_dict)
            if action is None:
                continue
            _dispatch_action(scene, state, action)

        elapsed = scene.renderer.time - t0
        pause_after = float(sc.get("pause_after", 0.0))
        wait_time = max(0.0, audio_dur + pause_after - elapsed - SCENE_FADE_OUT_SECONDS)

        if ENABLE_SUBTITLES and narration and wait_time > 1.0:
            from rendering_engine.subtitles import play_subtitles_for_scene
            play_subtitles_for_scene(
                scene, narration, wait_time,
                max_words=SUBTITLE_MAX_WORDS,
                audio_path=sc.get("audio_path"),
            )
        elif wait_time > 0.01:
            scene.wait(wait_time)

        _reset_camera_if_needed(scene)

        keep = future_refs[i] if i < len(future_refs) else set()
        _clear_scene(scene, state, keep)

        if i < n - 1 and SCENE_GAP_SECONDS > 0:
            scene.wait(SCENE_GAP_SECONDS)

    play_outro_card(scene, category, topic)


# ---------------------------------------------------------------------------
# Scene cleanup with selective persistence
# ---------------------------------------------------------------------------

def _clear_scene(scene: Any, state: SceneState, keep_ids: set[str]) -> None:
    """Fade-out objects at end of a scene, preserving those needed later.

    *keep_ids* contains IDs referenced by future scenes.  Instead of keeping
    ALL persistent objects when any is needed, we now selectively keep only
    the specific objects in *keep_ids* plus connections whose endpoints are
    in *keep_ids* (to maintain topology coherence).  Internal ``__`` prefixed
    objects (header, watermark) are always kept.
    """
    # Build set of persistent IDs to keep: those explicitly referenced +
    # connections whose endpoints are both in keep_ids
    keep_persistent: set[str] = set()
    for k in list(state.objects):
        if k.startswith("__"):
            continue
        cat = state._categories.get(k, "persistent")
        if cat != "persistent":
            continue
        if k in keep_ids:
            keep_persistent.add(k)
        elif k.startswith("conn_"):
            # Keep connections whose endpoint node IDs are in keep_ids
            parts = k.split("_", 3)  # conn_<from>_<to> or conn_<from>_<to>__N
            if len(parts) >= 3:
                from_id = parts[1]
                to_id = parts[2].split("__")[0]
                if from_id in keep_ids and to_id in keep_ids:
                    keep_persistent.add(k)

    to_fade: list = []
    to_remove_keys: list[str] = []

    for k, mob in list(state.objects.items()):
        if k.startswith("__"):
            continue  # always keep internal objects
        cat = state._categories.get(k, "persistent")
        if cat == "persistent" and k in keep_persistent:
            continue
        to_fade.append(mob)
        to_remove_keys.append(k)

    kept_mob_ids = {
        id(state.objects[k])
        for k in state.objects
        if k not in to_remove_keys
    }

    protected_ids = set()
    try:
        camera = getattr(scene, "camera", None)
        if camera:
            frame = getattr(camera, "frame", None)
            if frame:
                protected_ids.add(id(frame))
            protected_ids.add(id(camera))
    except Exception:
        pass
    for mob in scene.mobjects:
        try:
            z = mob.get_z_index() if hasattr(mob, "get_z_index") else 0
            if z <= -90:
                protected_ids.add(id(mob))
        except Exception:
            pass
    for k in state.objects:
        if k.startswith("__"):
            protected_ids.add(id(state.objects[k]))

    orphans = [
        m for m in scene.mobjects
        if id(m) not in kept_mob_ids and id(m) not in protected_ids
    ]
    all_fade = to_fade + orphans

    if all_fade:
        seen = set()
        unique = []
        for m in all_fade:
            mid = id(m)
            if mid not in seen and mid not in protected_ids:
                seen.add(mid)
                unique.append(m)
        if unique:
            scene.play(
                *[FadeOut(m, shift=DOWN * 0.12) for m in unique],
                run_time=SCENE_FADE_OUT_SECONDS,
            )

    for k in to_remove_keys:
        state.unregister(k)

    for mob in list(scene.mobjects):
        if id(mob) not in kept_mob_ids and id(mob) not in protected_ids:
            scene.remove(mob)


# ---------------------------------------------------------------------------
# Camera reset between scenes
# ---------------------------------------------------------------------------

def _reset_camera_if_needed(scene: Any) -> None:
    """Smoothly reset camera to default if it was moved by focus_camera."""
    camera = getattr(scene, "camera", None)
    frame = getattr(camera, "frame", None)
    if frame is None:
        return
    current_width = frame.get_width()
    current_center = frame.get_center()
    if abs(current_width - 14.2) > 0.05 or abs(current_center[0]) > 0.05 or abs(current_center[1]) > 0.05:
        scene.play(
            frame.animate.set_width(14.2).move_to(ORIGIN),
            run_time=0.4,
        )


# ---------------------------------------------------------------------------
# Persistent topic header (always visible at top)
# ---------------------------------------------------------------------------

_TOPIC_HEADER_KEY = "__topic_header"


def _add_persistent_topic_header(
    scene: Any, state: SceneState, topic: str, category: str = "",
) -> None:
    """Add a small persistent topic label at the top of the frame.

    Anchored to the camera via updater so it stays put during parallax.
    """
    if not topic:
        return

    from manim import RoundedRectangle

    header = Text(
        topic[:80],
        font_size=17,
        color=WHITE,
    )
    header.set_opacity(0.96)
    if header.width > 10:
        header.set_width(10)

    bg = RoundedRectangle(
        width=header.width + 0.5,
        height=header.height + 0.18,
        corner_radius=0.06,
        stroke_width=1.2,
        stroke_color=CATEGORY_ACCENT.get(category, PRIMARY),
        stroke_opacity=0.5,
        fill_color="#0a0e18",
        fill_opacity=0.82,
    )
    bg.move_to(header.get_center())
    group = VGroup(bg, header)

    camera = getattr(scene, "camera", None)
    frame = getattr(camera, "frame", None)

    def _anchor(mob):
        try:
            if frame is not None:
                cx = frame.get_center()[0]
                cy = frame.get_center()[1] + frame.get_height() / 2 - mob.height / 2 - 0.22
                mob.move_to([cx, cy, 0])
            else:
                mob.to_edge(UP, buff=0.22)
        except Exception:
            pass

    _anchor(group)
    group.add_updater(_anchor)
    group.set_z_index(30)
    scene.add(group)

    if state is not None:
        try:
            state.register(_TOPIC_HEADER_KEY, group)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Corner decorations
# ---------------------------------------------------------------------------

_CORNER_DECO_KEY = "__corner_deco"


def _add_corner_decorations(scene: Any, state: SceneState, category: str = "") -> None:
    """Place subtle accent dots (top-right) and bracket lines (bottom-left).

    Anchored to camera so they stay in place during parallax.
    """
    accent = CATEGORY_ACCENT.get(category, PRIMARY)

    # Top-right accent dots
    dots = VGroup()
    for dx, dy in [(0, 0), (0.18, 0), (0.36, 0)]:
        d = Dot(radius=0.035, color=accent)
        d.set_opacity(0.35)
        d.shift(RIGHT * dx + UP * dy)
        dots.add(d)

    # Bottom-left bracket lines
    bracket = VGroup()
    vline = Line(UP * 0.3, DOWN * 0.0, color=accent, stroke_width=1.5)
    vline.set_opacity(0.3)
    hline = Line(LEFT * 0.0, RIGHT * 0.3, color=accent, stroke_width=1.5)
    hline.set_opacity(0.3)
    hline.move_to(vline.get_bottom(), aligned_edge=LEFT)
    bracket.add(vline, hline)

    group = VGroup(dots, bracket)

    camera = getattr(scene, "camera", None)
    frame = getattr(camera, "frame", None)

    def _anchor(mob):
        try:
            if frame is not None:
                cx = frame.get_center()[0]
                cy = frame.get_center()[1]
                hw = frame.get_width() / 2
                hh = frame.get_height() / 2
                # dots → top-right
                dots.move_to([cx + hw - 0.55, cy + hh - 0.45, 0])
                # bracket → bottom-left
                bracket.move_to([cx - hw + 0.45, cy - hh + 0.45, 0])
            else:
                dots.move_to([6.2, 3.5, 0])
                bracket.move_to([-6.2, -3.5, 0])
        except Exception:
            pass

    _anchor(group)
    group.add_updater(_anchor)
    group.set_z_index(25)
    scene.add(group)

    if state is not None:
        try:
            state.register(_CORNER_DECO_KEY, group)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Title card
# ---------------------------------------------------------------------------

def _play_title_card(
    scene: Any, topic: str, subtitle_text: str = "", category: str = "",
) -> None:
    from manim import ApplyWave, Write

    from rendering_engine.easing import (
        add_parallax,
        cubic_ease_in_out,
        cubic_ease_out,
        remove_parallax,
    )

    accent = CATEGORY_ACCENT.get(category, PRIMARY)

    title = Text(
        topic[:120] if topic else "Untitled",
        font_size=TITLE_FONT_SIZE,
        color=accent,
    )
    if title.width > 12:
        title.set_width(12)
    subtitle = Text(
        subtitle_text or "Educational Concepts",
        font_size=SUBTITLE_FONT_SIZE,
        color=MUTED,
    )
    card = VGroup(title, subtitle).arrange(DOWN, buff=0.35)

    glow = title.copy()
    glow.scale(1.15)
    glow.move_to(title.get_center())
    glow.set_fill(accent, opacity=GLOW_OPACITY)
    glow.set_stroke(width=0)
    card.add_to_back(glow)

    parallax = add_parallax(scene, amplitude=0.04, period=10.0)

    hold = max(0.1, TITLE_CARD_SECONDS - TITLE_FADE_IN - TITLE_FADE_OUT - 0.4)
    scene.play(
        Write(title, run_time=TITLE_FADE_IN, rate_func=cubic_ease_out),
        FadeIn(glow, run_time=TITLE_FADE_IN, rate_func=cubic_ease_in_out),
    )
    scene.play(
        FadeIn(subtitle, shift=UP * 0.15, rate_func=cubic_ease_out),
        run_time=0.35,
    )
    try:
        scene.play(ApplyWave(title, amplitude=0.06, run_time=0.4))
    except Exception:
        pass
    scene.wait(hold)
    scene.play(
        FadeOut(card, shift=UP * 0.15, rate_func=cubic_ease_in_out),
        run_time=TITLE_FADE_OUT,
    )
    remove_parallax(scene, parallax)
