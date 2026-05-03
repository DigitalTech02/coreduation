"""Track 4C — auto-fix loop driven by 4A + 4B validation findings.

When a scene fails validation, ask the LLM to revise just that scene's
actions to address the specific finding. Returns a revised script that
the pipeline can re-render.

Design choices:
  - Per-scene revision (not whole-script): cheaper, more targeted, less
    chance of breaking already-good scenes.
  - Single-shot revision per scene per retry: cap at 2 retries total to
    bound cost and avoid infinite loops.
  - Combines findings from BOTH validators (4A + 4B) into one fix request.
  - Falls back to the original scene if the LLM revision fails to parse
    or doesn't produce a valid action list.
  - Gated by ENABLE_AUTO_FIX env var (default off — costs ~$0.02 per
    failed scene per retry).

What this does NOT do:
  - Does not re-render scene-by-scene in isolation (the Manim pipeline
    runs the whole script at once). Auto-fix returns a revised script;
    the caller decides whether to re-render the full video.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SceneFix:
    """Per-scene fix request: the original scene + collected findings."""

    scene_id: str
    findings: list[dict]   # mix of FrameFinding + SceneQAFinding dicts
    original_actions: list[dict]


_FIX_SYSTEM_PROMPT = """\
You are a video script repair specialist. A rendered scene from an educational
video has been flagged with visual problems. You will be given the scene's
original action list and the structured findings from the validators. Your job
is to revise the scene's actions to address the findings.

Rules:
- Output a JSON object with a single key "actions" whose value is the revised
  list of action dicts. Match the original action vocabulary exactly.
- Make the SMALLEST change needed. Do not redesign the scene.
- If the finding is "blank": add visible content (create_node, show_text_block
  with body, show_bullet_list, show_table, etc.) so the scene is no longer
  empty.
- If the finding is "overlap" or "misaligned": separate the conflicting
  elements; prefer relocating text out of the diagram zone, or shrinking
  bullet lists to <=5 items.
- If the finding is "duplicate": remove the duplicate action.
- If the finding is "cutoff" or "overflow": shorten labels / wrap text /
  reduce font size implied by content density.
- If the finding is "illegible": increase font weight implied by using
  emphasize_text instead of show_text_block, or shorten text content.

Action vocabulary reminder (most-used types):
  create_node {id, label, sublabel?, position, icon_type}
  create_connection {from, to, style?, label?, color?}
  send_packet {from, to, label, color}
  show_text_block {title?, body?, position?}
  show_bullet_list {title?, items, progressive?}
  show_table {title?, headers, rows}
  show_code_block {title?, language?, lines, highlight_lines?}
  show_comparison {left:{title,items}, right:{title,items}, title?}
  show_sequence_diagram {title?, participants, messages}
  show_layer_stack {stack_type, highlight_layers, title?}
  show_header_breakdown {title?, fields:[{name,size?,highlight?}], highlight_field?}
  pulse_element {target_id, intensity?, duration?}
  shake_element {target_id, duration?, intensity?}
  add_callout {target_id, text, position?, duration?}
  emphasize_text {text, emphasis_type?, duration?}
  dim_except {target_ids, opacity?, duration?}
  restore_opacity {duration?}
  focus_camera {target_id?, zoom?, duration?, x?, y?}
  reset_camera {duration?}

Output JSON only. No prose. No markdown fences. Example output:
  {"actions":[{"type":"create_node","id":"victim_app","label":"Victim App",
  "icon_type":"computer","position":"left"}, ...]}\
"""


def _build_user_prompt(fix: SceneFix) -> str:
    """Compose the user message describing the broken scene + its findings."""
    findings_summary = "\n".join(
        f"  - [{f.get('severity','?').upper()}] {f.get('type','?')}: "
        f"{f.get('detail') or f.get('description') or ''} "
        f"{'→ ' + f['suggestion'] if f.get('suggestion') else ''}"
        for f in fix.findings
    ) or "  - (no findings)"
    return (
        f"Scene id: {fix.scene_id}\n"
        f"\n"
        f"Findings:\n{findings_summary}\n"
        f"\n"
        f"Original actions (JSON):\n"
        f"{json.dumps(fix.original_actions, indent=2)}\n"
        f"\n"
        f"Return revised actions in the format described."
    )


def _revise_scene_actions(client: Any, model: str, fix: SceneFix) -> list[dict] | None:
    """Single LLM call to revise one scene's actions. Returns None on failure."""
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _FIX_SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(fix)},
            ],
            response_format={"type": "json_object"},
            max_tokens=1500,
            temperature=0.2,
        )
        raw = completion.choices[0].message.content or "{}"
        data = json.loads(raw)
        actions = data.get("actions")
        if not isinstance(actions, list) or not actions:
            logger.warning(
                "auto_fix: scene %s produced empty/invalid actions; keeping original",
                fix.scene_id,
            )
            return None
        return actions
    except Exception as e:
        logger.warning("auto_fix: scene %s revision failed: %s", fix.scene_id, e)
        return None


def revise_failed_scenes(
    script_dict: dict,
    fixes: list[SceneFix],
) -> tuple[dict, list[str]]:
    """Apply LLM revisions to the failed scenes in *script_dict*.

    Returns ``(revised_script_dict, list_of_revised_scene_ids)``. Scenes
    whose revision LLM call fails are left untouched.
    """
    if not fixes:
        return script_dict, []

    enable = os.getenv("ENABLE_AUTO_FIX", "false").strip().lower() in (
        "1", "true", "yes", "on",
    )
    if not enable:
        logger.info("Auto-fix disabled (set ENABLE_AUTO_FIX=true to enable).")
        return script_dict, []

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set; auto-fix skipped")
        return script_dict, []

    from openai import OpenAI
    model = os.getenv("OPENAI_MODEL", "gpt-4.1")
    client = OpenAI(api_key=api_key)

    fixes_by_id = {f.scene_id: f for f in fixes}
    revised_ids: list[str] = []

    for scene in script_dict.get("scenes", []):
        sid = scene.get("scene_id")
        if sid not in fixes_by_id:
            continue
        new_actions = _revise_scene_actions(client, model, fixes_by_id[sid])
        if new_actions is not None:
            scene["actions"] = new_actions
            revised_ids.append(sid)
            logger.info("auto_fix: revised scene %s (%d actions)",
                        sid, len(new_actions))

    return script_dict, revised_ids


def collect_fixes(
    deterministic_findings: list[Any] | None,
    scene_qa_findings: list[Any] | None,
    scenes: list[dict],
) -> list[SceneFix]:
    """Merge 4A + 4B findings into per-scene fix requests.

    Only scenes with at least one ``severity=fail`` finding produce a
    SceneFix — warns are not retried.
    """
    by_scene: dict[str, list[dict]] = {}

    def _add(items, source):
        for x in items or []:
            d = x.to_dict() if hasattr(x, "to_dict") else dict(x)
            sid = d.get("scene_id")
            if not sid:
                continue
            if d.get("severity") != "fail" and not any(
                f.get("severity") == "fail" for f in d.get("findings", [])
            ):
                continue
            for finding in d.get("findings", []) or [d]:
                if finding.get("severity") == "fail":
                    by_scene.setdefault(sid, []).append({
                        **finding,
                        "source": source,
                    })

    _add(deterministic_findings, "4A")
    _add(scene_qa_findings, "4B")

    # Index original actions by scene_id so each fix has the source actions.
    actions_by_id = {
        s.get("scene_id"): s.get("actions", []) for s in scenes
    }

    return [
        SceneFix(
            scene_id=sid,
            findings=findings,
            original_actions=actions_by_id.get(sid, []),
        )
        for sid, findings in by_scene.items()
        if sid in actions_by_id
    ]
