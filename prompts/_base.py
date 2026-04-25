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
            f"{RETENTION_STRATEGY}\n\n"
            f"{self.video_structure}\n\n"
            f"{self.narration_style}\n\n"
            f"{ACTION_VOCABULARY}\n\n"
            f"{self.preferred_actions}\n\n"
            f"{SHARED_RULES}\n\n"
            f"{self.example_scene}\n\n"
            f"{OUTPUT_FORMAT}"
        )


# ── Retention strategy (identical across all categories) ─────────────────

RETENTION_STRATEGY = """\
═══════════════════════════════════════════
RETENTION-FIRST SCRIPTING
═══════════════════════════════════════════

A. HIGH-STAKES HOOK
   Scene 1 MUST open with a real-world problem, risk, failure, or curiosity gap.
   BAD: "Today we will learn binary search."
   GOOD: "If you had to find one user in a database of 10 million, checking one \
by one would be painfully slow. But there is a trick that finds the answer in \
about 24 steps."

B. OPEN LOOP
   Introduce a question or unresolved challenge early (scene 1 or 2) and resolve \
it near the end. Example: "Why does cutting the search space in half feel almost \
unfairly powerful? We will answer that by the end."

C. FAILURE-FIRST TEACHING
   Show the bad/slow/wrong approach FIRST, then introduce the better one. Use \
shake_element and dim_except to visualize failure. Examples: linear search before \
binary search, full table scan before index lookup, timeout before retransmit.

D. RE-HOOKS EVERY 45-60 SECONDS
   Insert short attention resets in narration approximately every 45-60 seconds:
   - "Here is the part most people miss."
   - "Now watch what changes."
   - "This is where the speedup happens."
   - "Here is the hidden trick."

E. CONVERSATIONAL BUT PROFESSIONAL TONE
   Avoid textbook phrasing. Use direct, clear, energetic explanation.

F. RECOMMENDED SCENE FLOW
   Scene 1: High-stakes hook
   Scene 2: Problem setup
   Scene 3: Naive/wrong/slow approach (use shake_element for failure)
   Scene 4: Introduce core idea (use emphasize_text)
   Scene 5–N: Step-by-step explanation (use focus_camera, pulse_element, show_progress)
   Midpoint scene: "Let's put it together"
   Near-final scene: Real-world implication / failure case
   Final scene: Strong summary + memorable takeaway

G. VISUAL ENGAGEMENT
   - Use pulse_element to draw attention to the active element
   - Use focus_camera to zoom into the detail being explained
   - Use shake_element when showing errors, failures, or wrong approaches
   - Use dim_except to spotlight a specific element
   - Use add_callout for important labels
   - Use show_progress / update_progress for step-by-step algorithms
   - Use emphasize_text for key phrases or big reveals\
"""


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
  Params: hops (array of {node_id, label?}), label (string, optional), color (string, optional)

─── RETENTION & CAMERA ────────────────────

• pulse_element
  Make an existing element briefly pulse/glow to draw attention.
  Params: target_id (existing element id), intensity (float, default 1.15), \
duration (float, default 0.5), color (string, optional)

• focus_camera
  Zoom/pan camera to an object or area. Keep zoom conservative (1.1-1.35).
  Params: target_id (existing element id, optional), zoom (float, default 1.2), \
duration (float, default 1.0), x (float, optional), y (float, optional)

• reset_camera
  Return to normal full-frame view.
  Params: duration (float, default 1.0)

• show_progress
  Show a persistent progress indicator (e.g. "Step 1 of 5: Find middle").
  Params: label (string), current_step (int), total_steps (int), style (string, default "sleek")

• update_progress
  Update the progress indicator.
  Params: label (string), current_step (int), total_steps (int)

• emphasize_text
  Show a large kinetic phrase briefly for impact.
  Params: text (string), emphasis_type ("pop"|"fade", default "pop"), duration (float, default 1.0)

• shake_element
  Shake an element to indicate failure, error, or wrong choice.
  Params: target_id (existing element id), duration (float, default 0.5), intensity (float, default 0.15)

• dim_except
  Dim all elements except specified targets to spotlight them.
  Params: target_ids (array of existing element ids), opacity (float, default 0.25), duration (float, default 0.5)

• restore_opacity
  Restore all elements to normal opacity after dim_except.
  Params: duration (float, default 0.5)

• add_callout
  Small explanatory label pointing to an element.
  Params: target_id (existing element id), text (string), position ("auto"|"left"|"right"|"above"|"below", default "auto"), \
duration (float, default 2.0)

• scene_transition
  Polished transition between major sections.
  Params: transition_type ("wipe"|"fade", default "wipe"), label (string, optional), duration (float, default 0.8)\
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
- estimated_duration: realistic seconds for narration (15-30s per scene).
- REFERENCEABLE IDs: Only objects created by create_node, create_topology, \
create_cloud_service, or create_cloud_region have stable IDs you can use as \
target_id in retention actions (pulse_element, shake_element, focus_camera, \
dim_except, add_callout). Presentation actions like show_table, show_text_block, \
show_code_block, show_comparison, show_bullet_list do NOT produce IDs you can \
reference. If you need to pulse/shake/callout a specific element, create it as a \
node first (create_node) so it has a referenceable ID.
- Always call restore_opacity after dim_except when you want to return to normal.
- Always call reset_camera after focus_camera when the zoom is no longer needed.
- show_progress should be placed early in step-by-step scenes; use \
update_progress to advance the step counter.
- Include at least one failure/error scenario per video when appropriate. Use \
shake_element + a red highlight or callout to illustrate the failure.\
"""

# ── Output format (identical across all categories) ──────────────────────

OUTPUT_FORMAT = """\
OUTPUT: Return a single JSON object only (no markdown).

REQUIRED top-level keys:
  "topic" (string), "scenes" (array)

OPTIONAL top-level metadata (include when possible for better videos):
  "video_title" — catchy YouTube title
  "video_hook" — the opening hook line
  "open_loop_question" — the unresolved question posed early
  "open_loop_resolution_scene_id" — scene_id where the open loop is resolved
  "retention_beats" — array of short re-hook phrases used in narration
  "target_audience" — e.g. "CS students", "junior developers"
  "emotional_tone" — e.g. "curious and energetic", "serious and precise"
  "suggested_thumbnail_text" — short punchy text for a thumbnail
  "suggested_youtube_title" — optimized YouTube title

Each scene object must include: scene_id, title, type, narration, \
visual_description, actions (array of action objects), estimated_duration.

Field "type" MUST be exactly one of: "concept", "code", or "visualization" \
(use "visualization" for demos/walkthroughs/diagrams; "code" for commands/config; \
"concept" for explanations).

Each action object must include "type" and the parameters required for that type \
(see vocabulary above).\
"""
