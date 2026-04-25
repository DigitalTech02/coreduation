"""Single Manim Scene: title card, scene segments, paced waits, fade transitions.

Used by the semantic engine to render the whole video in one pass.
Handles cross-scene persistence so topology objects survive into scenes
that reference them (e.g. send_packet from a node created earlier).
"""

from __future__ import annotations

import logging
from typing import Any

from manim import DOWN, ORIGIN, UP, FadeIn, FadeOut, Text, VGroup

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


def _auto_toggle_persistent(scene: Any, state: SceneState, actions: list[dict]) -> None:
    """Hide or restore persistent objects based on whether this scene uses them.

    When a scene is purely presentation (tables, text, bullets) with no
    references to persistent topology/node objects, those objects are faded
    to invisible so they don't clutter the slide.  They're restored when a
    later scene references them again.
    """
    persistent_ids = {
        k for k, cat in state._categories.items()
        if cat == "persistent" and not k.startswith("__progress")
    }
    if not persistent_ids:
        return

    scene_refs = _extract_scene_refs(actions)
    scene_uses_persistent = bool(persistent_ids & scene_refs)

    if scene_uses_persistent:
        if state._hidden:
            state.restore_persistent(scene)
    else:
        if not state._hidden:
            state.hide_persistent(scene)


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
    _play_title_card(scene, topic, subtitle, category)

    future_refs = _collect_future_refs(scenes)
    state = SceneState()
    n = len(scenes)

    for i, sc in enumerate(scenes):
        actions = sc.get("actions", [])
        narration = sc.get("narration", "")
        audio_dur = float(
            sc.get("audio_duration") or sc.get("estimated_duration") or 10.0
        )

        _auto_toggle_persistent(scene, state, actions)

        t0 = scene.renderer.time

        for action_dict in actions:
            action = _rebuild_action(action_dict)
            if action is None:
                continue
            _dispatch_action(scene, state, action)

        elapsed = scene.renderer.time - t0
        wait_time = max(0.0, audio_dur - elapsed - SCENE_FADE_OUT_SECONDS)

        if ENABLE_SUBTITLES and narration and wait_time > 1.0:
            from rendering_engine.subtitles import play_subtitles_for_scene
            play_subtitles_for_scene(
                scene, narration, wait_time,
                max_words=SUBTITLE_MAX_WORDS,
            )
        elif wait_time > 0.01:
            scene.wait(wait_time)

        _reset_camera_if_needed(scene)

        keep = future_refs[i] if i < len(future_refs) else set()
        _clear_scene(scene, state, keep)

        if i < n - 1 and SCENE_GAP_SECONDS > 0:
            scene.wait(SCENE_GAP_SECONDS)


# ---------------------------------------------------------------------------
# Scene cleanup with selective persistence
# ---------------------------------------------------------------------------

def _clear_scene(scene: Any, state: SceneState, keep_ids: set[str]) -> None:
    """Fade-out objects at end of a scene, preserving those needed later.

    *keep_ids* contains IDs referenced by future scenes.  If ANY persistent
    object's ID appears in *keep_ids*, we keep **all** persistent objects
    (nodes, connections, regions) so the whole topology stays coherent.
    Presentation objects and orphaned mobjects are always removed.
    """
    any_persistent_needed = any(
        state._categories.get(k) == "persistent" and k in keep_ids
        for k in state.objects
    )

    to_fade: list = []
    to_remove_keys: list[str] = []

    for k, mob in list(state.objects.items()):
        cat = state._categories.get(k, "persistent")
        if cat == "persistent" and any_persistent_needed:
            continue
        to_fade.append(mob)
        to_remove_keys.append(k)

    kept_mob_ids = {
        id(state.objects[k])
        for k in state.objects
        if k not in to_remove_keys
    }
    orphans = [m for m in scene.mobjects if id(m) not in kept_mob_ids]
    all_fade = to_fade + orphans

    if all_fade:
        seen = set()
        unique = []
        for m in all_fade:
            mid = id(m)
            if mid not in seen:
                seen.add(mid)
                unique.append(m)
        scene.play(
            *[FadeOut(m, shift=DOWN * 0.12) for m in unique],
            run_time=SCENE_FADE_OUT_SECONDS,
        )

    for k in to_remove_keys:
        state.unregister(k)

    for mob in list(scene.mobjects):
        if id(mob) not in kept_mob_ids:
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
# Title card
# ---------------------------------------------------------------------------

def _play_title_card(
    scene: Any, topic: str, subtitle_text: str = "", category: str = "",
) -> None:
    from manim import ApplyWave, Write

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

    hold = max(0.1, TITLE_CARD_SECONDS - TITLE_FADE_IN - TITLE_FADE_OUT - 0.4)
    scene.play(Write(title, run_time=TITLE_FADE_IN), FadeIn(glow, run_time=TITLE_FADE_IN))
    scene.play(FadeIn(subtitle, shift=UP * 0.15), run_time=0.3)
    try:
        scene.play(ApplyWave(title, amplitude=0.06, run_time=0.4))
    except Exception:
        pass
    scene.wait(hold)
    scene.play(FadeOut(card, shift=UP * 0.15), run_time=TITLE_FADE_OUT)
