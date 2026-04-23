"""Validate semantic scripts before rendering — reference checks in action order.

Duplicate **implicit** connection ids (same endpoints, no explicit ``id``) are
allocated as ``conn_a_b``, ``conn_a_b__1``, … in :func:`_reserve_implicit_connection_id`
(rendering uses the same scheme in ``topology._unique_connection_id``).

Duplicate **explicit** ids should be repaired by :func:`semantic_repair.repair_duplicate_ids`
before this validator runs.
"""

from __future__ import annotations

from pydantic import TypeAdapter

from models_semantic import EnrichedVideoScript, VisualAction


def _reserve_implicit_connection_id(from_node: str, to_node: str, known: set[str]) -> str:
    """Auto id ``conn_{a}_{b}``, ``conn_{a}_{b}__1``, … so duplicate edges validate."""
    base = f"conn_{from_node}_{to_node}"
    cid = base
    suffix = 0
    while cid in known:
        suffix += 1
        cid = f"{base}__{suffix}"
    known.add(cid)
    return cid


def validate_semantic_script(script: EnrichedVideoScript) -> list[str]:
    """Process every action in script order. Raises ValueError if references break.

    Sequence diagram participants are names, not topology node IDs: we do not
    require them to appear in ``known``.
    """
    known: set[str] = set()
    issues: list[str] = []

    def add_id(obj_id: str, scene_id: str, ctx: str) -> None:
        if obj_id in known:
            issues.append(f"scene {scene_id} {ctx}: duplicate id {obj_id!r}")
        known.add(obj_id)

    def need(ref: str, scene_id: str, ctx: str) -> None:
        if ref and ref not in known:
            issues.append(f"scene {scene_id} {ctx}: unknown id {ref!r}")

    for scene in script.scenes:
        sid = scene.scene_id
        for action in scene.actions:
            t = action.type

            if t == "create_node":
                add_id(action.id, sid, "create_node")

            elif t == "create_topology":
                for n in action.nodes:
                    add_id(n.id, sid, "create_topology")

            elif t == "create_connection":
                need(action.from_node, sid, "create_connection from")
                need(action.to_node, sid, "create_connection to")
                explicit = (action.id or "").strip()
                if explicit:
                    if explicit in known:
                        issues.append(f"scene {sid}: duplicate connection id {explicit!r}")
                    known.add(explicit)
                else:
                    _reserve_implicit_connection_id(
                        action.from_node, action.to_node, known
                    )

            elif t == "update_node":
                need(action.id, sid, "update_node")

            elif t == "remove_element":
                need(action.id, sid, "remove_element")

            elif t == "send_packet":
                need(action.from_node, sid, "send_packet from")
                need(action.to_node, sid, "send_packet to")

            elif t == "send_broadcast":
                need(action.from_node, sid, "send_broadcast")

            elif t == "show_sequence_diagram":
                pass

            elif t == "create_cloud_region":
                add_id(action.id, sid, "create_cloud_region")
                if action.parent_id:
                    need(action.parent_id, sid, "create_cloud_region parent")

            elif t == "create_cloud_service":
                add_id(action.id, sid, "create_cloud_service")

            elif t == "show_data_flow":
                for hop in action.hops:
                    need(hop.node_id, sid, "show_data_flow")

    if issues:
        msg = "Semantic validation failed:\n" + "\n".join(f"  - {i}" for i in issues)
        raise ValueError(msg)

    return []


def parse_actions_from_dicts(raw: list[dict]) -> list:
    adapter = TypeAdapter(list[VisualAction])
    return adapter.validate_python(raw)
