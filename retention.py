"""Retention enrichment — ensure visual activity to prevent dormant screens.

The ``ensure_retention_beats`` function injects visual actions into scenes
that have long narration but too few visual events, keeping the 3-second rule.

Key strategy: if a scene has NO persistent visual (no table, code, bullets, text,
topology, etc.), inject a ``show_text_block`` from the scene title + a key phrase
from the narration so the viewer always has something to look at.
"""

from __future__ import annotations

import logging

from models_semantic import EnrichedVideoScript

logger = logging.getLogger(__name__)

_PERSISTENT_VISUAL_TYPES = frozenset({
    "show_table", "show_code_block", "show_comparison", "show_bullet_list",
    "show_sequence_diagram", "show_layer_stack", "show_header_breakdown",
    "show_text_block", "show_math",
    "create_node", "create_connection", "create_topology",
    "create_cloud_region", "create_cloud_service",
})


def _has_persistent_visual(actions: list[dict]) -> bool:
    """True if at least one action produces content that stays on screen."""
    return any(a.get("type") in _PERSISTENT_VISUAL_TYPES for a in actions)


def _extract_key_phrase(narration: str, max_len: int = 80) -> str:
    """Pull the first sentence or clause as a summary line."""
    text = narration.strip()
    for sep in [". ", "? ", "! ", "— ", ", "]:
        idx = text.find(sep)
        if 15 < idx < max_len:
            return text[:idx + 1].strip()
    return text[:max_len].strip() + ("..." if len(text) > max_len else "")


def _estimate_visual_seconds(actions: list[dict]) -> float:
    """Rough estimate of how many seconds the actions fill visually."""
    total = 0.0
    for a in actions:
        t = a.get("type", "")
        if t in _PERSISTENT_VISUAL_TYPES:
            total += 3.0
        elif t in ("send_packet", "send_broadcast", "show_data_flow"):
            total += 2.0
        elif t in ("pulse_element", "shake_element", "emphasize_text", "add_callout"):
            total += 1.0
        elif t in ("focus_camera", "reset_camera", "scene_transition"):
            total += a.get("duration", 0.8)
        elif t in ("show_progress", "update_progress"):
            total += 0.5
        elif t in ("dim_except", "restore_opacity"):
            total += 0.5
        elif t in ("update_node", "remove_element"):
            total += 0.8
        else:
            total += 1.0
    return total


def _find_pulseable_id(actions: list[dict]) -> str | None:
    """Find the most recently created or referenced element id."""
    last_id = None
    for a in actions:
        for key in ("id", "target_id", "from", "to", "from_node", "to_node"):
            val = a.get(key)
            if val and not val.startswith("conn_") and val != "no-ref-id":
                last_id = val
    return last_id


def ensure_retention_beats(
    script: EnrichedVideoScript,
    max_idle_seconds: float = 3.0,
) -> EnrichedVideoScript:
    """Enrich the script with visual content where screens would go dormant.

    Two strategies:
    1. If a scene has NO persistent visual at all, inject a ``show_text_block``
       with the scene title and a key narration phrase so there's always
       something on screen.
    2. If a scene has persistent visuals but a long idle gap, inject a subtle
       ``pulse_element`` on the last referenced object.

    Modifies scenes in-place and returns the same script.
    """
    from models_semantic import ShowTextBlock, PulseElement

    for scene in script.scenes:
        raw_actions = [a.model_dump(by_alias=True) for a in scene.actions]

        if not _has_persistent_visual(raw_actions):
            key_phrase = _extract_key_phrase(scene.narration)
            fallback = ShowTextBlock(
                title=scene.title,
                body=key_phrase,
                position="center",
            )
            scene.actions.insert(0, fallback)
            logger.info(
                "Retention: injected show_text_block in scene %s (no persistent visual)",
                scene.scene_id,
            )
            continue

        audio_dur = scene.audio_duration or scene.estimated_duration
        visual_dur = _estimate_visual_seconds(raw_actions)
        idle_gap = audio_dur - visual_dur

        if idle_gap <= max_idle_seconds:
            continue

        pulseable = _find_pulseable_id(raw_actions)
        if pulseable:
            beat = PulseElement(target_id=pulseable, intensity=1.08, duration=0.35)
            scene.actions.append(beat)
            logger.debug(
                "Retention beat: added pulse on %r in scene %s (idle gap %.1fs)",
                pulseable, scene.scene_id, idle_gap,
            )

    return script
