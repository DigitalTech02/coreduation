"""Single Manim Scene: title card, scene segments, paced waits, fade transitions.

Used by the semantic engine to render the whole video in one pass.
Handles cross-scene persistence so topology objects survive into scenes
that reference them (e.g. send_packet from a node created earlier).
"""

from __future__ import annotations

import logging
from typing import Any

from manim import DOWN, UP, FadeIn, FadeOut, Text, VGroup

from rendering_engine.engine import SceneState, _dispatch_action, _rebuild_action
from rendering_engine.styles import (
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
                        "parent_id", "region_id"):
                val = a.get(key)
                if val:
                    refs.add(val)
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
# Main loop
# ---------------------------------------------------------------------------

def run_full_video_construct(scene: Any, data: dict) -> None:
    """Build the full animation: title, then each scene with narration pacing."""
    topic = data.get("topic", "")
    scenes: list[dict] = data.get("scenes", [])

    _play_title_card(scene, topic)

    future_refs = _collect_future_refs(scenes)
    state = SceneState()
    n = len(scenes)

    for i, sc in enumerate(scenes):
        actions = sc.get("actions", [])
        audio_dur = float(
            sc.get("audio_duration") or sc.get("estimated_duration") or 10.0
        )

        t0 = scene.renderer.time

        for action_dict in actions:
            action = _rebuild_action(action_dict)
            if action is None:
                continue
            _dispatch_action(scene, state, action)

        elapsed = scene.renderer.time - t0
        wait_time = max(0.0, audio_dur - elapsed - SCENE_FADE_OUT_SECONDS)
        if wait_time > 0.01:
            scene.wait(wait_time)

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
# Title card
# ---------------------------------------------------------------------------

def _play_title_card(scene: Any, topic: str) -> None:
    title = Text(
        topic[:120] if topic else "Untitled",
        font_size=TITLE_FONT_SIZE,
        color=PRIMARY,
    )
    if title.width > 12:
        title.set_width(12)
    subtitle = Text(
        "Networking & cloud concepts",
        font_size=SUBTITLE_FONT_SIZE,
        color=MUTED,
    )
    card = VGroup(title, subtitle).arrange(DOWN, buff=0.35)

    hold = max(0.1, TITLE_CARD_SECONDS - TITLE_FADE_IN - TITLE_FADE_OUT)
    scene.play(FadeIn(card, shift=DOWN * 0.2), run_time=TITLE_FADE_IN)
    scene.wait(hold)
    scene.play(FadeOut(card, shift=UP * 0.15), run_time=TITLE_FADE_OUT)
