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

    # Flush the manifest to disk at every checkpoint instead of only at the
    # end.  If construct() crashes mid-render (e.g. a renderer raises in
    # scene 12 of 16) we still want a manifest reflecting whatever HAS
    # rendered, so the audio mux can place narration at the right offsets
    # for the partial silent video the fallback concat produces.  Without
    # this, main.py falls back to the legacy cumulative estimator whose
    # narration runs longer than the truncated visuals — ffmpeg -shortest
    # then clips audio to the silent video's length and the voice-over
    # races ahead of the visuals.
    def _flush_manifest() -> None:
        if not manifest_path:
            return
        try:
            manifest["total_video_duration"] = float(scene.renderer.time)
            Path(manifest_path).write_text(
                json.dumps(manifest, indent=2), encoding="utf-8",
            )
        except Exception as e:
            logger.warning("Could not flush timing manifest: %s", e)

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

        # Shorts mode: paint a mood-keyed background glow + (optionally) a
        # per-scene visual metaphor BEFORE actions so the canvas is fully
        # populated before the narration starts.  Both are tagged with a
        # custom "shorts_chrome" category so they survive the
        # ``state.clear_presentation`` call that fires when text/bullet
        # actions render.  Cleared explicitly at scene end below.
        if is_shorts:
            # Director's brief: CTA scene (last scene) MUST always be gold,
            # regardless of voice_mood the LLM emitted.  Maximizes the
            # conversion impulse on the link-tap moment.
            effective_mood = sc.get("voice_mood") or ""
            if i == len(scenes) - 1:
                effective_mood = "excited"  # → gold panel

            # Topic-seeded variation: hash topic+category to pick a
            # palette variant (0/1/2) and a light-ray angle.  Two shorts
            # on different topics in the same category will look
            # distinctly different without losing the mood color story.
            palette_idx = _topic_palette_index(topic, category)
            ray_angles = (15.0, 30.0, 42.0)
            ray_angle = ray_angles[palette_idx]

            try:
                _add_shorts_scene_glow(
                    scene, state, effective_mood,
                    palette_index=palette_idx,
                    light_ray_angle_deg=ray_angle,
                )
            except Exception as e:
                logger.debug("Shorts glow skipped for scene %d: %s", i, e)

            # Skip the geometric metaphor when this scene has an AI
            # illustration injected — the DALL-E image IS the hero visual.
            # Stacking both produces a busy frame.
            has_ai_illustration = any(
                (a or {}).get("type") == "show_image" for a in actions
            )
            if not has_ai_illustration:
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

        # Phase 2 trigger: warning pulse for dramatic/urgent scenes.
        # SHORTS-ONLY.  This calls scene.play() seven times in a row on a
        # freshly created VGroup, which reliably wedges Manim/Cairo on
        # Windows for the long-form pipeline.  Shorts only have 4 scenes
        # so the bug never triggers; long-form skips it entirely.
        if is_shorts:
            try:
                _voice_mood = (sc.get("voice_mood") or "").strip().lower()
                if _voice_mood in ("dramatic", "urgent") or any(
                    (a or {}).get("type") == "shake_element" for a in actions
                ):
                    from rendering_engine.micro_animations import play_warning_pulse
                    play_warning_pulse(
                        scene,
                        position=(0.0, 4.6),
                        scale=1.1,
                        duration=0.85,
                    )
            except Exception as e:
                logger.debug("Warning pulse skipped: %s", e)

        for action_dict in actions:
            action = _rebuild_action(action_dict)
            if action is None:
                continue
            _dispatch_action(scene, state, action)

        # Phase 1 trigger: confetti burst on scenes that read as a "reward
        # / payoff / final takeaway" beat.  SHORTS-ONLY for the same
        # multi-play() Cairo wedge reason as warning_pulse above.  Shorts
        # always force this on the last (CTA) scene.
        if is_shorts:
            try:
                from rendering_engine.confetti import play_confetti_burst, should_celebrate
                should_fire_confetti = should_celebrate(
                    voice_mood=sc.get("voice_mood") or "",
                    scene_id=sc.get("scene_id") or "",
                    narration=narration,
                )
                # Force on shorts last scene (CTA)
                if i == len(scenes) - 1:
                    should_fire_confetti = True

                if should_fire_confetti:
                    play_confetti_burst(
                        scene,
                        origin=(0.0, 1.5),
                        count=60,
                        spread_x=4.5,
                        duration=1.4,
                    )
            except Exception as e:
                logger.debug("Confetti burst skipped: %s", e)

        # Phase 2 trigger: success stamp.  SHORTS-ONLY (same Cairo wedge
        # reason).  Shorts force this on the payoff scene (3rd of 4) and
        # also fire on keyword match.
        if is_shorts:
            try:
                sid_lower = (sc.get("scene_id") or "").lower()
                narration_lower = (narration or "").lower()
                keyword_match = (
                    any(k in sid_lower for k in (
                        "secured", "verified", "protected", "safe", "done",
                        "payoff", "reveal", "twist",
                    ))
                    or any(k in narration_lower for k in (
                        "now you're safe", "your data is protected", "fully encrypted",
                        "successfully verified",
                    ))
                )
                shorts_payoff_scene = len(scenes) >= 4 and i == len(scenes) - 2
                if keyword_match or shorts_payoff_scene:
                    from rendering_engine.micro_animations import play_success_stamp
                    play_success_stamp(
                        scene,
                        position=(0.0, 3.5),  # upper area to avoid card
                        scale=1.4,
                        duration=1.0,
                    )
            except Exception as e:
                logger.debug("Success stamp skipped: %s", e)

        # Last scene of a short: fade out the text card / bullet list FIRST
        # (per the marketing-pillar brief: the CTA arrow must be the only
        # thing on screen at the end to maximize click-through), then play
        # the animated "Watch full →" CTA overlay on the gold panel.
        if is_shorts and i == len(scenes) - 1:
            try:
                state.clear_presentation(scene)
            except Exception:
                pass
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

        # Checkpoint after each completed scene — see _flush_manifest above.
        _flush_manifest()

        if i < n - 1 and SCENE_GAP_SECONDS > 0:
            scene.wait(SCENE_GAP_SECONDS)

    manifest["outro_start_seconds"] = float(scene.renderer.time)
    if not is_shorts:
        play_outro_card(scene, category, topic)
    manifest["outro_end_seconds"] = float(scene.renderer.time)
    manifest["total_video_duration"] = float(scene.renderer.time)

    _flush_manifest()
    if manifest_path:
        logger.info("Wrote scene timing manifest: %s", manifest_path)


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
    txt = Text(label, font_size=46, color=WHITE, weight="BOLD")

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


# Three palette variants per voice_mood.  Topic/category hash picks one
# variant per render, so two security-category shorts on different topics
# look distinctly different without losing the mood-based color story
# (hooks still feel "danger", payoffs still feel "calm/secure", etc.).
_SHORTS_MOOD_PALETTES: dict[str, tuple[str, str, str]] = {
    "hook":       ("#ff2d55", "#e0227a", "#d63384"),  # neon red / crimson / hot pink
    "dramatic":   ("#ff6b1f", "#e05a00", "#ff3b30"),  # vivid orange / burnt orange / red-orange
    "urgent":     ("#ff6b1f", "#e05a00", "#ff3b30"),
    "narrator":   ("#0a84ff", "#5e5ce6", "#00d4ff"),  # bright blue / indigo / cyan
    "analytical": ("#0a84ff", "#5e5ce6", "#00d4ff"),
    "calm":       ("#0a84ff", "#3fdca1", "#5e5ce6"),  # bright blue / mint / indigo
    "excited":    ("#ffcc00", "#ffd23f", "#ff9500"),  # neon gold / soft gold / amber
}

# Secondary deep colors per palette variant — used for bottom vignette.
_SHORTS_MOOD_DEEP_PALETTES: dict[str, tuple[str, str, str]] = {
    "hook":       ("#7a0e2e", "#5a0830", "#4d0a2a"),
    "dramatic":   ("#7a3210", "#5a2300", "#601515"),
    "urgent":     ("#7a3210", "#5a2300", "#601515"),
    "narrator":   ("#06366b", "#1e1b4d", "#003a4d"),
    "analytical": ("#06366b", "#1e1b4d", "#003a4d"),
    "calm":       ("#06366b", "#0a4d3a", "#1e1b4d"),
    "excited":    ("#7a6500", "#5a4500", "#7a4d00"),
}


def _topic_palette_index(topic: str, category: str) -> int:
    """Hash topic+category to a deterministic 0/1/2 palette variant."""
    import hashlib
    h = hashlib.sha256(f"{topic}|{category}".encode("utf-8")).hexdigest()
    return int(h, 16) % 3


def _attach_drift(
    mob: Any,
    *,
    anchor: tuple[float, float],
    amp_x: float = 0.5,
    amp_y: float = 0.3,
    period: float = 12.0,
    phase: float = 0.0,
) -> None:
    """Add a slow sin-wave drift updater to *mob* anchored at (ax, ay).

    Period is in seconds; longer = slower drift.  amp is in canvas units.
    Each updater carries its own time accumulator so multiple drifting
    mobjects don't pulse in sync.
    """
    import math
    ax, ay = anchor
    clock = [0.0]

    def _drift(m, dt, _ax=ax, _ay=ay, _amp_x=amp_x, _amp_y=amp_y,
               _period=period, _phase=phase, _t=clock):
        _t[0] += dt
        try:
            t = _t[0]
            ox = _amp_x * math.sin(2 * math.pi * t / _period + _phase)
            oy = _amp_y * math.cos(2 * math.pi * t / _period * 0.6 + _phase)
            m.move_to([_ax + ox, _ay + oy, 0])
        except Exception:
            pass

    try:
        mob.add_updater(_drift)
    except Exception:
        pass


def _build_shorts_pattern(pattern_index: int, seed_offset: int = 0) -> list:
    """Build the per-video background pattern overlay.

    Three styles, picked by ``pattern_index``:
      0 — sparkles: 14 small white drifting dots
      1 — dot grid: 4×6 grid of faint white dots, slow vertical drift
      2 — drifting orb stack: 3 concentric expanding rings

    All sit at z=-6 (above panel + bloom + sheen, below content text).
    Pure white / low opacity so they read as "texture" rather than
    competing with the mood color.
    """
    import math
    import random
    from manim import Circle as _Circle

    rng = random.Random(0xA1B2 + seed_offset * 17)
    layers: list = []

    if pattern_index == 0:
        # Sparkle field — 14 small drifting dots scattered across the panel.
        for i in range(14):
            x = rng.uniform(-3.4, 3.4)
            y = rng.uniform(-3.5, 5.0)
            radius = rng.uniform(0.04, 0.10)
            opacity = rng.uniform(0.30, 0.65)
            dot = _Circle(radius=radius, color="#ffffff", stroke_width=0)
            dot.set_fill("#ffffff", opacity=opacity)
            dot.move_to([x, y, 0])
            dot.set_z_index(-6)
            _attach_drift(
                dot,
                anchor=(x, y),
                amp_x=rng.uniform(0.10, 0.30),
                amp_y=rng.uniform(0.10, 0.30),
                period=rng.uniform(7.0, 14.0),
                phase=rng.uniform(0.0, math.tau),
            )
            layers.append(dot)
        return layers

    if pattern_index == 1:
        # Dot grid — 4 cols × 5 rows of faint dots, slow vertical drift
        # in a wave so the grid breathes.
        cols, rows = 4, 5
        x_spacing = 7.0 / (cols - 1)
        y_spacing = 8.5 / (rows - 1)
        for ci in range(cols):
            for ri in range(rows):
                x = -3.5 + ci * x_spacing
                y = 4.0 - ri * y_spacing
                dot = _Circle(radius=0.08, color="#ffffff", stroke_width=0)
                dot.set_fill("#ffffff", opacity=0.30)
                dot.move_to([x, y, 0])
                dot.set_z_index(-6)
                _attach_drift(
                    dot,
                    anchor=(x, y),
                    amp_x=0.0,
                    amp_y=0.20,
                    period=8.0,
                    phase=ci * 0.5 + ri * 0.3,
                )
                layers.append(dot)
        return layers

    # pattern_index == 2: drifting orb stack — 3 concentric circles
    # at the center that drift slowly.  Reads as a "radar / scanning"
    # texture under the content.
    for i, (radius, opacity) in enumerate([(2.4, 0.22), (3.4, 0.14), (4.4, 0.08)]):
        ring = _Circle(radius=radius, color="#ffffff", stroke_width=2)
        ring.set_fill("#ffffff", opacity=opacity)
        ring.set_stroke("#ffffff", width=2, opacity=0.40)
        ring.move_to([0.5, -0.5, 0])
        ring.set_z_index(-6)
        _attach_drift(
            ring,
            anchor=(0.5, -0.5),
            amp_x=0.6,
            amp_y=0.4,
            period=12.0 + i * 3.0,
            phase=i * 1.2,
        )
        layers.append(ring)
    return layers


# Backwards-compat: legacy single-color maps for code that doesn't yet
# look up the palette index.  Each maps to variant 0 of the palette.
_SHORTS_MOOD_GLOW: dict[str, str] = {
    k: v[0] for k, v in _SHORTS_MOOD_PALETTES.items()
}
_SHORTS_MOOD_GLOW_DEEP: dict[str, str] = {
}


def _add_shorts_scene_glow(
    scene: Any,
    state: SceneState,
    voice_mood: str,
    *,
    palette_index: int = 0,
    light_ray_angle_deg: float = 25.0,
) -> None:
    """Mood-keyed FULL-BLEED panel + diagonal light rays.

    Replaces the previous "small card on dark canvas" model with a vivid
    infographic-style panel that fills the middle three-quarters of the
    canvas with a saturated mood color.  Above + below the panel the
    badge / progress bar / subtitle / CTA still have room to breathe.

    Layered z=-50..z=-30 (above gradient background, below content).
    Cleared between scenes by ``_clear_shorts_glow``.

    Composition (top→bottom on a 9:16 canvas, frame ±7.111 vertical):
      y=+5.5..+7    badge/progress zone — left empty
      y=-4.0..+5.5  full-bleed mood panel with gradient + light rays
      y=-7..-4      subtitle + CTA zone — left empty
    """
    mood_key = (voice_mood or "").strip().lower()
    palette = _SHORTS_MOOD_PALETTES.get(mood_key)
    deep_palette = _SHORTS_MOOD_DEEP_PALETTES.get(mood_key)
    if not palette:
        logger.warning("Shorts glow: no palette for voice_mood=%r — skipping", voice_mood)
        return

    # Topic-seeded palette variant — same topic always picks the same
    # variant (deterministic), different topics feel visually distinct.
    pi = palette_index % 3
    color = palette[pi]
    deep = (deep_palette or palette)[pi]

    # Loud log — we've debugged 6+ commits trying to make this panel
    # visible.  This warning confirms the function runs and what color
    # was selected.  If you don't see this in the render log, the
    # function isn't being called.  If you do see it but the canvas is
    # still dark, the issue is in Manim's mobject pipeline / z-index.
    logger.warning(
        "Shorts panel: voice_mood=%r color=%s — adding mood panel layers",
        voice_mood, color,
    )

    from manim import Circle, Line as _Line, Rectangle as _Rect

    layers: list = []

    # Belt: set the camera's background_color to the mood color directly.
    try:
        scene.camera.background_color = color
        logger.warning("Shorts panel: camera.background_color set to %s", color)
    except Exception as e:
        logger.warning("Shorts panel: camera.background_color failed: %s", e)

    # Suspenders: a full-canvas Rectangle at z=-10.  Tried z=-100 across
    # multiple commits without any visible result; bumping to -10 (still
    # behind text/content at z=0+, but well above the previous extreme
    # negative range).  Manim renderers may have edge cases with very
    # large negative z values.
    panel = _Rect(
        width=9.0, height=15.5,
        color=color, stroke_width=0,
    )
    panel.set_fill(color, opacity=1.0)
    panel.move_to([0, 0, 0])
    panel.set_z_index(-10)
    layers.append(panel)

    # Layer 2 — subtle bottom vignette in deeper mood color (z just
    # above the panel but below content).
    slab = _Rect(
        width=9.0, height=3.5,
        color=deep, stroke_width=0,
    )
    slab.set_fill(deep, opacity=0.30)
    slab.move_to([0, -5.4, 0])
    slab.set_z_index(-9)
    layers.append(slab)

    # Layer 3 — diagonal white light-ray streaks for energy.  Angle is
    # now dynamic per-render (topic hash → 15-45°) so two shorts on
    # different topics don't share identical line angles.
    import math
    for i, (x_offset, y_offset, length) in enumerate([
        (-2.5,  3.0, 11.0),
        ( 0.0,  4.5, 11.0),
        ( 2.0,  2.0, 11.0),
        (-1.0, -1.5, 11.0),
    ]):
        angle = math.radians(light_ray_angle_deg)
        dx = (length / 2) * math.cos(angle)
        dy = (length / 2) * math.sin(angle)
        ray = _Line(
            start=[x_offset - dx, y_offset - dy, 0],
            end=[x_offset + dx, y_offset + dy, 0],
            color="#ffffff", stroke_width=4 + i * 0.8,
        )
        ray.set_opacity(0.18 + i * 0.06)
        ray.set_z_index(-8)
        layers.append(ray)

    # Layer 4 — accent corner bloom.  Position varies per palette index
    # for visual variety: variant 0 = top-right, variant 1 = top-left,
    # variant 2 = mid-right.  Now ANIMATED — drifts on a slow figure-8
    # so the canvas never feels static.
    blob_positions = [(3.0, 5.6, 0), (-3.0, 5.6, 0), (3.4, 1.5, 0)]
    bx, by, bz = blob_positions[palette_index % 3]
    blob = Circle(radius=1.8, color="#ffffff", stroke_width=0)
    blob.set_fill("#ffffff", opacity=0.20)
    blob.move_to([bx, by, bz])
    blob.set_z_index(-8)
    _attach_drift(blob, anchor=(bx, by), amp_x=0.45, amp_y=0.30, period=11.0, phase=0.0)
    layers.append(blob)

    # Layer 4b — SECONDARY contrasting blob that drifts diagonally across
    # the panel.  Color contrasts with the panel for visible motion (red
    # panel gets purple/cyan drift, blue panel gets orange/gold, etc.).
    contrast_colors = [
        ("#bf5af2", "#5e5ce6", "#ff9500"),  # variants for hook/dramatic (red/orange) panels
        ("#ffcc00", "#ff6b1f", "#3fdca1"),  # variants for narrator (blue) panels
        ("#0a84ff", "#ff2d55", "#bf5af2"),  # variants for excited (gold) panels
    ]
    if mood_key in ("hook", "dramatic", "urgent"):
        contrast_color = contrast_colors[0][palette_index % 3]
    elif mood_key in ("narrator", "analytical", "calm"):
        contrast_color = contrast_colors[1][palette_index % 3]
    else:  # excited
        contrast_color = contrast_colors[2][palette_index % 3]

    secondary = Circle(radius=2.6, color=contrast_color, stroke_width=0)
    secondary.set_fill(contrast_color, opacity=0.28)
    sx, sy = (-2.0, -2.5)
    secondary.move_to([sx, sy, 0])
    secondary.set_z_index(-9)  # below the bright bloom but above panel
    _attach_drift(secondary, anchor=(sx, sy), amp_x=1.4, amp_y=0.9, period=18.0, phase=1.5)
    layers.append(secondary)

    # Layer 5 — GLOSSY SHEEN.  Wide, short, semi-transparent white
    # rectangle near the top of the panel that reads as "gloss reflecting
    # off the surface".  Adds a premium-product feel without competing
    # with content (sits at z=-7, behind text but above panel).
    sheen = _Rect(width=8.6, height=2.6, color="#ffffff", stroke_width=0)
    sheen.set_fill("#ffffff", opacity=0.10)
    sheen.move_to([0, 5.0, 0])
    sheen.set_z_index(-7)
    layers.append(sheen)

    # Layer 6 — TOPIC-PICKED PATTERN OVERLAY.  Three styles chosen by
    # palette_index so two videos with different topic hashes get
    # distinctly different background textures.
    pattern_layers = _build_shorts_pattern(
        pattern_index=palette_index % 3,
        seed_offset=palette_index,
    )
    layers.extend(pattern_layers)

    # Add each layer DIRECTLY to the scene — no VGroup wrapping (VGroup's
    # single z_index overrides child z_indices for scene sorting).
    for mob in layers:
        scene.add(mob)

    logger.warning(
        "Shorts panel: added %d layers; scene now has %d total mobjects",
        len(layers), len(scene.mobjects),
    )

    # Keep the layer list in state so we can clear them all together.
    state.objects["__shorts_glow"] = layers
    state._categories["__shorts_glow"] = "shorts_chrome"


def _clear_shorts_glow(scene: Any, state: SceneState) -> None:
    """Remove the per-scene background panel + decoration layers.

    The panel layers are stored as a LIST (not a VGroup) per the
    z-index propagation fix in _add_shorts_scene_glow.  Iterate and
    remove each.  Skip the FadeOut animation — the next scene's
    _add_shorts_scene_glow will paint a fresh panel that visually
    "replaces" the old one anyway, and FadeOut on a list of disparate
    mobjects can be unreliable.
    """
    layers = state.objects.get("__shorts_glow")
    if layers is None:
        return
    if not isinstance(layers, list):
        layers = [layers]
    for mob in layers:
        try:
            scene.remove(mob)
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

    label = Text("WATCH FULL VIDEO", font_size=64, color=WHITE, weight="BOLD")
    arrow = Arrow(
        start=[0, 0.85, 0], end=[0, -0.55, 0],
        color=accent, stroke_width=18, max_tip_length_to_length_ratio=0.4,
    )
    sub = Text("link in description", font_size=42, color=accent, weight="BOLD")

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
