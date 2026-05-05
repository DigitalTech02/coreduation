"""Single Manim Scene: title card, scene segments, paced waits, fade transitions.

Used by the semantic engine to render the whole video in one pass.
Handles cross-scene persistence so topology objects survive into scenes
that reference them (e.g. send_packet from a node created earlier).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from manim import (
    DOWN, LEFT, ORIGIN, RIGHT, UP,
    Arrow, Dot, FadeIn, FadeOut, Line, Rectangle, RoundedRectangle, Text, VGroup, WHITE,
)

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
    """Keep the persistent topic header visible across all scenes.

    Per user feedback (2026-05-04): the topic header must be visible for
    the entire video as a continuity anchor — it's the only thing telling
    a viewer who joins mid-video what they're watching. Previously we
    hid it on slide-style scenes; now we always show it, regardless of
    *suppress*. Slide-style renderers must keep their scene-title text
    inside ``TITLE_ZONE`` so it doesn't collide with the header band.
    """
    header = state.objects.get(_TOPIC_HEADER_KEY)
    if header is None:
        return
    try:
        for sub in header.submobjects:
            sub.set_opacity(1.0)
        header.set_opacity(1.0)
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
    refs_persistent = bool(persistent_ids & scene_refs)

    # Two-state model per user feedback:
    #   - If scene references persistent objects → keep them at FULL opacity
    #     (no dimming). The slide content's renderer is responsible for
    #     relocating itself into vacant canvas space via _avoid_collision.
    #   - Otherwise → HIDE persistent entirely so the slide has the canvas.
    if refs_persistent:
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

    from rendering_engine.branding import (
        add_credit_label,
        add_watermark,
        play_intro_card,
        play_outro_card,
    )
    # Per-scene timing manifest — written so the audio mux can place each
    # scene's narration at the actual rendered video_start, not at the
    # estimated `audio_dur + pause_after + gap` cumulative position.  This
    # is the source of truth for AV alignment; without it, action animations
    # that overshoot their declared budget cause subtitle/narration drift to
    # accumulate across scenes.  See semantic_audio.build_narration_track_from_manifest.
    manifest_path = os.environ.get("SEMANTIC_TIMING_MANIFEST")
    manifest: dict[str, Any] = {
        "intro_card_end_seconds": 0.0,
        "title_card_end_seconds": 0.0,
        "scenes": [],
        "outro_start_seconds": 0.0,
        "outro_end_seconds": 0.0,
        "total_video_duration": 0.0,
    }

    # "long" (default) renders intro card + title card + persistent topic
    # header + corner decorations + outro card.  "shorts" skips all of
    # those — a 50-second vertical short can't afford to spend ~9 seconds
    # on chrome, and the persistent header / corner art crowd a 9:16 canvas.
    mode = (data.get("mode") or "long").strip().lower()
    is_shorts = mode == "shorts"

    if not is_shorts:
        play_intro_card(scene, category)
    manifest["intro_card_end_seconds"] = float(scene.renderer.time)

    if not is_shorts:
        _play_title_card(scene, topic, subtitle, category)
    manifest["title_card_end_seconds"] = float(scene.renderer.time)

    future_refs = _collect_future_refs(scenes)
    state = SceneState()
    state.mode = "shorts" if is_shorts else "long"
    add_watermark(scene, state, category)
    if not is_shorts:
        add_credit_label(scene, state)
        _add_persistent_topic_header(scene, state, topic, category)
        _add_corner_decorations(scene, state, category)
    else:
        # Vertical-mode chrome: viewer-grabbing top badge + progress bar.
        _add_shorts_category_badge(scene, state, category)
        _add_shorts_progress_bar(scene, state, category, total_scenes=len(scenes))

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

        # Per-scene keyword burst overlay — gated by ENABLE_KEYWORD_BURST.
        # Default OFF (user feedback 2026-05-04: large dimmed background
        # word competes with content). Kept as opt-in for experiments.
        keyword_mob = None
        try:
            from config import ENABLE_KEYWORD_BURST
        except Exception:
            ENABLE_KEYWORD_BURST = False
        if ENABLE_KEYWORD_BURST:
            try:
                from rendering_engine.keyword_overlay import play_keyword_burst
                keyword_mob = play_keyword_burst(scene, state, sc, category=category)
            except Exception as e:
                logger.debug("Keyword burst skipped: %s", e)

        # Shorts mode: paint a mood-keyed background glow + render a
        # per-scene visual metaphor BEFORE actions so the canvas is fully
        # populated before the narration starts.  Both are tagged with a
        # custom "shorts_chrome" category so they survive the
        # ``state.clear_presentation`` call that fires when text/bullet
        # actions render — this was the bug in v2 that made every metaphor
        # invisible.  Cleared explicitly at scene end below.
        if is_shorts:
            try:
                _add_shorts_scene_glow(scene, state, sc.get("voice_mood") or "")
            except Exception as e:
                logger.debug("Shorts glow skipped for scene %d: %s", i, e)
            try:
                from rendering_engine.shorts_metaphors import (
                    pick_shorts_metaphor, render_shorts_metaphor,
                )
                meta_name = pick_shorts_metaphor(
                    scene_index=i,
                    total_scenes=len(scenes),
                    voice_mood=sc.get("voice_mood") or "",
                    category=category,
                )
                if meta_name:
                    render_shorts_metaphor(scene, state, meta_name, category=category)
            except Exception as e:
                logger.debug("Shorts metaphor skipped for scene %d: %s", i, e)

        t0 = scene.renderer.time

        # Record the moment this scene's narration audio MUST start in the
        # final mux.  Subtitles also anchor their timing to t0 (via
        # scene.renderer.time inside the scheduler), so audio + subtitles
        # share a single source of truth and cannot drift apart.
        manifest["scenes"].append({
            "scene_id": sc.get("scene_id", f"scene_{i}"),
            "video_start_seconds": float(t0),
            "audio_duration": float(audio_dur),
            "pause_after": float(sc.get("pause_after", 0.0) or 0.0),
        })

        # Schedule subtitles BEFORE running actions so each chunk appears
        # at its scene-relative start time even while actions are playing.
        # Time slices are allocated proportional to chunk word count and
        # sum to the full audio duration — so subtitle progression mirrors
        # narration audio progression instead of being squeezed into the
        # post-action wait window.
        scheduled_subtitles: list = []
        pause_after = float(sc.get("pause_after", 0.0))
        full_subtitle_window = audio_dur + pause_after - SCENE_FADE_OUT_SECONDS
        if ENABLE_SUBTITLES and narration and full_subtitle_window > 0.3:
            try:
                from rendering_engine.subtitles import schedule_subtitles_for_scene
                scheduled_subtitles = schedule_subtitles_for_scene(
                    scene, narration,
                    audio_duration=full_subtitle_window,
                    max_words=SUBTITLE_MAX_WORDS,
                    whisper_words=sc.get("whisper_words") or None,
                )
            except Exception as e:
                logger.debug("Subtitle scheduling skipped: %s", e)

        for action_dict in actions:
            action = _rebuild_action(action_dict)
            if action is None:
                continue
            _dispatch_action(scene, state, action)

        # Last scene of a short: animated "Watch full →" CTA overlay.
        # Plays immediately after the scene's actions so it's visible during
        # the narration's CTA line, not crammed into the trailing fade.
        if is_shorts and i == len(scenes) - 1:
            try:
                _play_shorts_cta_overlay(scene, category)
            except Exception as e:
                logger.debug("Shorts CTA overlay skipped: %s", e)

        elapsed = scene.renderer.time - t0
        wait_time = max(0.0, audio_dur + pause_after - elapsed - SCENE_FADE_OUT_SECONDS)

        # Wait out the remaining audio time so the scheduled-subtitle
        # updaters keep firing for any chunks still in their time slice.
        if wait_time > 0.01:
            scene.wait(wait_time)

        if scheduled_subtitles:
            try:
                from rendering_engine.subtitles import clear_scheduled_subtitles
                clear_scheduled_subtitles(scene, scheduled_subtitles)
            except Exception:
                pass

        if is_shorts:
            try:
                from rendering_engine.shorts_metaphors import clear_shorts_metaphor
                clear_shorts_metaphor(scene, state)
            except Exception:
                pass
            try:
                _clear_shorts_glow(scene, state)
            except Exception:
                pass

        _reset_camera_if_needed(scene)

        if keyword_mob is not None:
            try:
                from rendering_engine.keyword_overlay import fade_out_keyword_burst
                fade_out_keyword_burst(scene, keyword_mob)
            except Exception:
                pass

        keep = future_refs[i] if i < len(future_refs) else set()
        _clear_scene(scene, state, keep)

        # Record the actual end-of-scene time after wait + clear-fade.
        # Used by audio mux for per-scene music swaps that match visuals.
        if manifest["scenes"]:
            manifest["scenes"][-1]["video_end_seconds"] = float(scene.renderer.time)

        if i < n - 1 and SCENE_GAP_SECONDS > 0:
            scene.wait(SCENE_GAP_SECONDS)

    manifest["outro_start_seconds"] = float(scene.renderer.time)
    if not is_shorts:
        play_outro_card(scene, category, topic)
    manifest["outro_end_seconds"] = float(scene.renderer.time)
    manifest["total_video_duration"] = float(scene.renderer.time)

    if manifest_path:
        try:
            Path(manifest_path).write_text(
                json.dumps(manifest, indent=2), encoding="utf-8",
            )
            logger.info("Wrote scene timing manifest: %s", manifest_path)
        except Exception as e:
            logger.warning("Could not write timing manifest: %s", e)


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


# ---------------------------------------------------------------------------
# Shorts (vertical 9:16) decoration layer
# ---------------------------------------------------------------------------

# Category → header label for the shorts top badge.  Emoji prefix gives a
# punchy visual cue at frame 0 even before the LLM-generated content shows up.
_SHORTS_CATEGORY_LABEL: dict[str, str] = {
    "security":           "🔒  SECURITY",
    "networking":         "🌐  NETWORKING",
    "data-structures":    "🌳  DATA STRUCTURES",
    "programming":        "💻  PROGRAMMING",
    "cloud-architecture": "☁️  CLOUD",
    "system-design":      "⚙️  SYSTEM DESIGN",
    "business-analysis":  "📊  BUSINESS",
    "databases":          "🗄️  DATABASES",
}


def _add_shorts_category_badge(scene: Any, state: SceneState, category: str) -> None:
    """Top-of-frame pill with category emoji + label.

    Anchored to the camera frame's top edge via updater so it survives
    parallax / camera moves.  Sits at z=40 — over background, under any
    scene content that lives at default z=0+.
    """
    label = _SHORTS_CATEGORY_LABEL.get((category or "").strip().lower(), "")
    if not label:
        return

    accent = CATEGORY_ACCENT.get(category, PRIMARY)
    txt = Text(label, font_size=38, color=WHITE, weight="BOLD")

    pill = RoundedRectangle(
        width=txt.width + 1.0,
        height=txt.height + 0.45,
        corner_radius=0.25,
        color=accent,
        stroke_width=0,
        fill_color=accent,
        fill_opacity=0.95,
    )
    pill.move_to(txt.get_center())
    badge = VGroup(pill, txt)

    def _anchor(mob):
        try:
            frame = scene.camera.frame
            cy = frame.get_top()[1] - mob.height / 2 - 0.32
            mob.move_to([0, cy, 0])
        except Exception:
            mob.to_edge(UP, buff=0.35)

    _anchor(badge)
    badge.add_updater(_anchor)
    badge.set_z_index(40)
    scene.add(badge)
    state.objects["__shorts_badge"] = badge
    state._categories["__shorts_badge"] = "persistent"


# Mood → background-glow color.  Painted as a large faint blob behind the
# scene's text card so empty canvas reads as "themed background", not "dead
# space".  Matches the emotional tone of the scene's voice_mood.
_SHORTS_MOOD_GLOW: dict[str, str] = {
    "hook":       "#ff4d4d",   # urgent red
    "dramatic":   "#ff5e1f",   # angry orange
    "urgent":     "#ff5e1f",
    "narrator":   "#3fb6ff",   # cool blue (analytical)
    "analytical": "#3fb6ff",
    "calm":       "#3fb6ff",
    "excited":    "#ffd23f",   # gold (CTA energy)
}


def _add_shorts_scene_glow(scene: Any, state: SceneState, voice_mood: str) -> None:
    """Mood-keyed visual layer painted behind the scene's content.

    Three stacked elements at z=-50 (above the gradient background, behind
    all content):

    1. A big translucent radial blob in the mood color, centered.
    2. A vertical accent stripe along the LEFT edge of the canvas.
    3. A vertical accent stripe along the RIGHT edge.

    Together they fill the empty side margins with a per-scene color so the
    viewer reads the emotional arc — danger → tension → solution → CTA —
    through the background hue alone.
    """
    color = _SHORTS_MOOD_GLOW.get((voice_mood or "").strip().lower())
    if not color:
        return

    from manim import Circle, Rectangle as _Rect

    glow = Circle(radius=5.6, color=color, stroke_width=0)
    glow.set_fill(color, opacity=0.30)
    glow.move_to([0, 0.0, 0])
    glow.set_z_index(-50)

    # Vertical stripes hugging the canvas edges — adds vivid color
    # without competing with central content.  ~0.35 wide each.
    left_stripe = _Rect(width=0.45, height=14.0, color=color, stroke_width=0)
    left_stripe.set_fill(color, opacity=0.38)
    left_stripe.move_to([-3.78, 0.0, 0])  # frame_width=8 → -3.78 ≈ left edge
    left_stripe.set_z_index(-49)

    right_stripe = _Rect(width=0.45, height=14.0, color=color, stroke_width=0)
    right_stripe.set_fill(color, opacity=0.38)
    right_stripe.move_to([3.78, 0.0, 0])
    right_stripe.set_z_index(-49)

    layer = VGroup(glow, left_stripe, right_stripe)

    try:
        layer.set_opacity(0.0)
        scene.add(layer)
        scene.play(FadeIn(layer), run_time=0.35)
    except Exception:
        scene.add(layer)

    state.objects["__shorts_glow"] = layer
    state._categories["__shorts_glow"] = "shorts_chrome"


def _clear_shorts_glow(scene: Any, state: SceneState) -> None:
    glow = state.objects.get("__shorts_glow")
    if glow is None:
        return
    try:
        scene.play(FadeOut(glow), run_time=0.25)
    except Exception:
        pass
    try:
        scene.remove(glow)
    except Exception:
        pass
    state.objects.pop("__shorts_glow", None)
    state._categories.pop("__shorts_glow", None)


def _add_shorts_progress_bar(
    scene: Any, state: SceneState, category: str, total_scenes: int,
) -> None:
    """Thin top-edge progress bar that fills with playback time.

    The fill width updates each frame against ``scene.renderer.time``.  We
    estimate total duration from the number of scenes (~8s avg per shorts
    scene) — the bar resyncs to the actual finish time at video end so the
    inaccuracy is invisible to the viewer.
    """
    if total_scenes <= 0:
        return

    accent = CATEGORY_ACCENT.get(category, PRIMARY)
    # Estimated duration drives the fill rate.  Capped at 60s (Shorts limit).
    estimated_total = min(60.0, max(20.0, total_scenes * 11.0))

    BAR_WIDTH = 7.4  # slightly inset from the 8.0 frame width
    BAR_HEIGHT = 0.12
    BADGE_GAP = 1.05  # leave room for the category badge above

    track = Rectangle(
        width=BAR_WIDTH, height=BAR_HEIGHT,
        color=accent, stroke_width=0,
        fill_color=accent, fill_opacity=0.20,
    )
    fill = Rectangle(
        width=0.001, height=BAR_HEIGHT,
        color=accent, stroke_width=0,
        fill_color=accent, fill_opacity=0.95,
    )
    fill.align_to(track, LEFT)

    bar = VGroup(track, fill)
    t0 = float(scene.renderer.time)

    def _anchor_and_fill(mob, dt, _t0=t0, _total=estimated_total, _track=track, _fill=fill):
        try:
            frame = scene.camera.frame
            cy = frame.get_top()[1] - mob.height / 2 - BADGE_GAP
            mob.move_to([0, cy, 0])
            elapsed = max(0.0, float(scene.renderer.time) - _t0)
            ratio = min(1.0, elapsed / _total)
            new_w = max(0.001, BAR_WIDTH * ratio)
            _fill.stretch_to_fit_width(new_w)
            # Re-pin fill's left edge to track's left edge after stretch
            left_x = _track.get_left()[0]
            _fill.move_to([left_x + new_w / 2, _track.get_center()[1], 0])
        except Exception:
            pass

    _anchor_and_fill(bar, 0)
    bar.add_updater(_anchor_and_fill)
    bar.set_z_index(38)
    scene.add(bar)
    state.objects["__shorts_progress"] = bar
    state._categories["__shorts_progress"] = "persistent"


def _play_shorts_cta_overlay(scene: Any, category: str) -> None:
    """Animated 'Watch full →' CTA overlay used on the LAST scene of a short.

    Adds a chunky bouncing arrow + accent label below the content card so
    the viewer's eye lands on the CTA right as the narrator delivers it.
    The overlay fades out with the scene clear, no manual cleanup needed.
    """
    accent = CATEGORY_ACCENT.get(category, PRIMARY)

    label = Text("WATCH FULL VIDEO", font_size=46, color=WHITE, weight="BOLD")
    arrow = Arrow(
        start=[0, 0.7, 0], end=[0, -0.45, 0],
        color=accent, stroke_width=14, max_tip_length_to_length_ratio=0.4,
    )
    sub = Text("link in description", font_size=32, color=accent, weight="BOLD")

    cta = VGroup(label, arrow, sub).arrange(DOWN, buff=0.30)
    try:
        frame = scene.camera.frame
        cy = frame.get_bottom()[1] + 1.9
        cta.move_to([0, cy, 0])
    except Exception:
        cta.to_edge(DOWN, buff=1.0)
    cta.set_z_index(50)

    scene.play(FadeIn(label, shift=UP * 0.2), run_time=0.40)
    scene.play(FadeIn(arrow), run_time=0.25)
    try:
        # Bigger pulse to draw the eye
        scene.play(arrow.animate.scale(1.25), run_time=0.20)
        scene.play(arrow.animate.scale(1 / 1.25), run_time=0.20)
    except Exception:
        pass
    scene.play(FadeIn(sub), run_time=0.25)


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

    # Subtle halo: 1.04× scale + 0.05 opacity. Keeps the title from feeling
    # flat without producing a visible "ghost" duplicate (a known artifact of
    # the prior 1.15× / 0.14-opacity copy — it read as second-text-behind).
    glow = title.copy()
    glow.scale(1.04)
    glow.move_to(title.get_center())
    glow.set_fill(accent, opacity=0.05)
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
