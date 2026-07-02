"""Post-process LLM semantic scripts: enforce globally unique definition IDs.

Runs after generation and before ``validate_semantic_script``.  Complements the
implicit connection-id scheme in ``semantic_validation`` (empty ``id`` →
``conn_a_b``, ``conn_a_b__1``, …).

Renaming applies only to **definition** fields (``create_node``, ``create_connection``
with explicit ``id``, topology nodes, cloud resources).  Reference fields
(``send_packet`` ``from``/``to``, etc.) are left unchanged — avoid redefining the
same logical object twice; prefer one create and reuse node ids across scenes.
"""

from __future__ import annotations

import logging

from models_semantic import EnrichedVideoScript

logger = logging.getLogger(__name__)


def _make_unique(defn_id: str, seen: set[str]) -> str:
    """First use keeps ``defn_id``; later collisions become ``id__dup2``, ``id__dup3``, …"""
    if defn_id not in seen:
        seen.add(defn_id)
        return defn_id
    n = 2
    while True:
        cand = f"{defn_id}__dup{n}"
        if cand not in seen:
            seen.add(cand)
            if cand != defn_id:
                logger.info("Repaired duplicate definition id: %r -> %r", defn_id, cand)
            return cand
        n += 1


def repair_duplicate_ids(script: EnrichedVideoScript) -> EnrichedVideoScript:
    """Return a copy of the script with globally unique ids on defining actions.

    For ``create_topology`` specifically: if every node ID is already
    defined, drop the action entirely instead of renaming to ``__dup2``.
    The LLM's intent in that case is to *reference* the existing cast
    (e.g. a "Meet the Cast" scene after the hook already created them) —
    re-rendering with suffixed IDs duplicates the nodes on screen.
    """
    seen: set[str] = set()
    data = script.model_dump(mode="json")

    for scene in data["scenes"]:
        new_actions = []
        for act in scene["actions"]:
            t = act["type"]

            if t == "create_node":
                old = act["id"]
                act["id"] = _make_unique(old, seen)
                new_actions.append(act)

            elif t == "create_topology":
                node_ids = [n["id"] for n in (act.get("nodes") or [])]
                already_defined = [nid for nid in node_ids if nid in seen]
                if node_ids and len(already_defined) == len(node_ids):
                    # All nodes already exist — drop this topology action.
                    logger.info(
                        "Skipped create_topology in scene %r: all node IDs "
                        "%s already defined (LLM likely meant to reference, "
                        "not recreate)",
                        scene.get("scene_id", "?"), node_ids,
                    )
                    continue
                for node in act.get("nodes") or []:
                    old = node["id"]
                    node["id"] = _make_unique(old, seen)
                new_actions.append(act)

            elif t == "create_connection":
                explicit = (act.get("id") or "").strip()
                if explicit:
                    act["id"] = _make_unique(explicit, seen)
                new_actions.append(act)

            elif t == "create_cloud_region":
                old = act["id"]
                act["id"] = _make_unique(old, seen)
                new_actions.append(act)

            elif t == "create_cloud_service":
                old = act["id"]
                act["id"] = _make_unique(old, seen)
                new_actions.append(act)

            else:
                new_actions.append(act)

        scene["actions"] = new_actions

    return EnrichedVideoScript.model_validate(data)
