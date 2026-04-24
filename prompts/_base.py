"""Base dataclass and shared prompt assembler for specialty prompts."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SpecialtyPrompt:
    """Domain-specific prompt configuration for the semantic video engine."""

    category: str
    title_card_subtitle: str
    persona: str
    video_structure: str
    narration_style: str
    preferred_actions: str
    example_scene: str
    user_prompt_extra: str = ""

    def build_system_prompt(self) -> str:
        return (
            f"{self.persona}\n\n"
            f"Given a topic, produce a JSON video script with a list of scenes.  Each scene "
            f"has narration text and a list of VISUAL ACTIONS that describe what to show.\n\n"
            f"You do NOT write any code.  You only specify structured actions from the "
            f"vocabulary below, and a rendering engine handles all visuals deterministically.\n\n"
            f"{self.video_structure}\n\n"
            f"{self.narration_style}\n\n"
            f"{ACTION_VOCABULARY}\n\n"
            f"{self.preferred_actions}\n\n"
            f"{SHARED_RULES}\n\n"
            f"{self.example_scene}\n\n"
            f"{OUTPUT_FORMAT}"
        )


# ── Shared action vocabulary (identical across all categories) ───────────

ACTION_VOCABULARY = """\
═══════════════════════════════════════════
VISUAL ACTION VOCABULARY
═══════════════════════════════════════════

Each scene contains an "actions" array.  Each action has a "type" field \
plus type-specific parameters.  Available types:

─── TOPOLOGY ──────────────────────────────

• create_node
  Place a visual entity on screen.
  Params: id (string), label (string), sublabel (string, optional),
          position (left|right|center|top|bottom|top_left|top_right|bottom_left|bottom_right or "x,y"),
          icon_type (computer|server|router|switch|firewall|cloud|phone|database|load_balancer|generic)

• create_connection
  Draw a link between two nodes.
  Params: from (node id), to (node id),
          style (solid|dashed|dotted), label (string, optional),
          color (string, optional), bidirectional (bool, default false)

• create_topology
  Shortcut to lay out a full topology.
  Params: layout (star|mesh|ring|bus|tree),
          nodes (array of {id, label, sublabel?, icon_type?}),
          center_node_id (string, optional — for star layout)

• update_node
  Change a node's label, sublabel, or highlight color.
  Params: id, label?, sublabel?, highlight_color? (red|green|yellow|blue etc.)

• remove_element
  Fade out a node or connection.  Params: id

─── PACKET FLOW ───────────────────────────

• send_packet
  Animate a labeled packet from one node to another.
  Params: from (node id), to (node id), label (string), color (string), speed (float, default 1.0)

• send_broadcast
  Send a packet from one node to all its neighbors simultaneously.
  Params: from (node id), label (string), color (string)

─── SEQUENCE DIAGRAM ──────────────────────

• show_sequence_diagram
  Full UML-style sequence diagram.
  Params: title (string, optional),
          participants (array of strings),
          messages (array of {from, to, label, color?, dashed?})

─── DATA / PROTOCOL DISPLAY ───────────────

• show_layer_stack
  OSI or TCP/IP layer model.
  Params: stack_type (osi|tcp_ip), highlight_layers (array of ints, 0-indexed from top),
          title (string, optional)

• show_header_breakdown
  Horizontal packet/frame field diagram.
  Params: title (string, optional),
          fields (array of {name, size?, highlight?}),
          highlight_field (string, optional — field name to highlight)

• show_table
  Data table (arrays, routing tables, comparison grids, etc.).
  Params: title (string, optional), headers (array of strings),
          rows (array of {cells: [string], highlight?: bool}),
          highlight_row (int, optional)

• show_math
  Render a LaTeX math expression.
  Params: expression (LaTeX string), label (string, optional)

─── PRESENTATION ──────────────────────────

• show_text_block
  Titled text (definition, key fact).
  Params: title (string, optional), body (string, optional)

• show_code_block
  Terminal command or config snippet.
  Params: title (string, optional), language (string, optional),
          lines (array of strings), highlight_lines (array of int indices, optional)

• show_comparison
  Side-by-side comparison.
  Params: title (string, optional),
          left: {title, items: [string]}, right: {title, items: [string]}

• show_bullet_list
  Progressive bullet points.
  Params: title (string, optional), items (array of strings),
          progressive (bool, default true)

─── CLOUD ARCHITECTURE ────────────────────

• create_cloud_region
  Bounding box for a cloud region/VPC/AZ/subnet.
  Params: id, label, parent_id (string, optional — for nesting), position

• create_cloud_service
  Cloud service node (compute, storage, etc.).
  Params: id, label,
          service_type (compute|storage|database|serverless|api_gateway|cdn|load_balancer|queue|cache|dns|generic),
          region_id (string, optional), position

• show_data_flow
  Animate a request hopping through cloud services.
  Params: hops (array of {node_id, label?}), label (string, optional), color (string, optional)\
"""

# ── Shared rules (identical across all categories) ───────────────────────

SHARED_RULES = """\
═══════════════════════════════════════════
RULES
═══════════════════════════════════════════

- Every node referenced by send_packet, create_connection, etc. MUST be \
created first via create_node, create_topology, or create_cloud_service.
- Every object **id** you assign (nodes, connections if you set "id", cloud \
regions/services) must be **globally unique** across the entire video. Never \
repeat the same id for two different definitions. If the same logical object \
appears in a later scene, **reuse the same id** — do not create_node again \
with that id; reference it in actions that only need existing nodes.
- Prefer omitting create_connection **id** (implicit names are auto-generated) \
unless you must remove_element that connection later.
- Node IDs must be unique lowercase slugs (e.g. "client", "router-1", "vpc-main").
- Each scene's actions are rendered in order — place nodes before animating packets.
- Use position hints to avoid overlap: spread nodes across left/right/top/bottom.
- For complex topologies, prefer create_topology over many individual create_node calls.
- Keep each scene focused: 2-8 actions per scene is typical.
- scene_id must be a unique lowercase slug with hyphens.
- estimated_duration: realistic seconds for narration (15-30s per scene).\
"""

# ── Output format (identical across all categories) ──────────────────────

OUTPUT_FORMAT = """\
OUTPUT: Return a single JSON object only (no markdown). Top-level keys must be \
"topic" (string) and "scenes" (array). Each scene object must include: scene_id, \
title, type, narration, visual_description, actions (array of action objects), \
estimated_duration. Field "type" MUST be exactly one of: "concept", "code", or \
"visualization" (use "visualization" for demos/walkthroughs/diagrams; "code" for \
commands/config; "concept" for explanations). Each action object must include \
"type" and the parameters required for that type (see vocabulary above).\
"""
