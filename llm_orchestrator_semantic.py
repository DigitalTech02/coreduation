"""Semantic LLM orchestrator — generates structured visual action scripts.

Instead of producing raw Manim code, the LLM outputs a JSON script describing
*what* to show using a fixed vocabulary of visual actions.  The deterministic
rendering engine then translates those actions into Manim.
"""

import logging
import os

from dotenv import load_dotenv
from openai import OpenAI

from models_semantic import EnrichedVideoScript, SemanticVideoScript

load_dotenv()

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are an expert technical educator creating educational video scripts about \
computer networking and cloud architecture.  Your videos are like the best \
university lectures — thorough, engaging, and packed with visual intuition.

Given a topic, produce a JSON video script with a list of scenes.  Each scene \
has narration text and a list of VISUAL ACTIONS that describe what to show.

You do NOT write any code.  You only specify structured actions from the \
vocabulary below, and a rendering engine handles all visuals deterministically.

═══════════════════════════════════════════
VIDEO STRUCTURE (10-18 scenes)
═══════════════════════════════════════════

1. HOOK & INTRODUCTION (1-2 scenes)
   - Compelling question or real-world motivation
   - State what the viewer will learn

2. CORE CONCEPT EXPLANATION (3-5 scenes)
   - Build intuition step by step with diagrams and analogies
   - One idea per scene, each with its own visual

3. VISUAL WALKTHROUGH (3-5 scenes)
   - Show the concept working on concrete examples
   - Step-by-step with network diagrams, packet animations, tables

4. IMPLEMENTATION / CONFIG (1-3 scenes)
   - Show relevant commands, config snippets, or protocol details
   - Header breakdowns, code blocks

5. ANALYSIS & COMPARISON (1-2 scenes)
   - Compare with alternatives (TCP vs UDP, hub vs switch, etc.)
   - Performance, complexity, or trade-off summaries

6. SUMMARY (1 scene)
   - Recap key points with a bullet list

═══════════════════════════════════════════
NARRATION GUIDELINES
═══════════════════════════════════════════

- Write as a friendly expert teacher speaking to camera
- Each scene: 3-6 sentences (15-30 seconds spoken)
- Use conversational tone: "Let's see...", "Notice how...", "Here's the key..."
- Total narration: 4-8 minutes across all scenes

═══════════════════════════════════════════
VISUAL ACTION VOCABULARY
═══════════════════════════════════════════

Each scene contains an "actions" array.  Each action has a "type" field \
plus type-specific parameters.  Available types:

─── TOPOLOGY ──────────────────────────────

• create_node
  Place a network entity on screen.
  Params: id (string), label (string), sublabel (string, optional — e.g. IP),
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
  Routing table, ARP cache, NAT table, DNS records, etc.
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

═══════════════════════════════════════════
RULES
═══════════════════════════════════════════

- Every node referenced by send_packet, create_connection, etc. MUST be created first via create_node, create_topology, or create_cloud_service.
- Every object **id** you assign (nodes, connections if you set \"id\", cloud regions/services) must be **globally unique** across the entire video. Never repeat the same id for two different definitions. If the same logical object appears in a later scene, **reuse the same id** — do not create_node again with that id; reference it in actions that only need existing nodes.
- Prefer omitting create_connection **id** (implicit names are auto-generated) unless you must remove_element that connection later.
- Node IDs must be unique lowercase slugs (e.g. "client", "router-1", "vpc-main").
- Each scene's actions are rendered in order — place nodes before animating packets.
- Use position hints to avoid overlap: spread nodes across left/right/top/bottom.
- For complex topologies, prefer create_topology over many individual create_node calls.
- Keep each scene focused: 2-8 actions per scene is typical.
- scene_id must be a unique lowercase slug with hyphens.
- estimated_duration: realistic seconds for narration (15-30s per scene).

OUTPUT: Return a single JSON object only (no markdown). Top-level keys must be \
"topic" (string) and "scenes" (array). Each scene object must include: scene_id, \
title, type, narration, visual_description, actions (array of action objects), \
estimated_duration. Field "type" MUST be exactly one of: "concept", "code", or \
"visualization" (use "visualization" for demos/walkthroughs/diagrams; "code" for \
commands/config; "concept" for explanations). Each action object must include \
"type" and the parameters required for that type (see vocabulary above).\
"""


def _strip_json_fences(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def generate_semantic_script(topic: str) -> EnrichedVideoScript:
    """Generate a semantic video script for the given topic.

    Uses ``response_format=json_object`` (OpenAI does not accept Pydantic's
    ``oneOf``/discriminated union schemas for ``parse``).  We validate the
    response with ``SemanticVideoScript`` locally.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY is not set in environment")

    model = os.getenv("OPENAI_MODEL", "gpt-4.1")
    client = OpenAI(api_key=api_key)

    logger.info("Generating semantic script for topic: %s (model: %s)", topic, model)

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Create a comprehensive educational video script about: {topic}\n\n"
                    f"Requirements:\n"
                    f"- Target length: 4-8 minutes of narration (10-18 scenes)\n"
                    f"- Include: real-world motivation, intuition building, "
                    f"visual walkthroughs with concrete examples, protocol details or config\n"
                    f"- Use network diagrams, packet animations, sequence diagrams, "
                    f"and tables where appropriate\n"
                    f"- End with practical takeaways\n\n"
                    f"Respond with JSON only (no prose before or after)."
                ),
            },
        ],
        response_format={"type": "json_object"},
    )

    raw = completion.choices[0].message.content
    if not raw:
        raise ValueError("LLM returned empty content")

    try:
        llm_script = SemanticVideoScript.model_validate_json(_strip_json_fences(raw))
    except Exception as e:
        logger.error("Failed to parse semantic script JSON: %s", e)
        logger.debug("Raw response (first 2000 chars): %s", raw[:2000])
        raise

    logger.info(
        "Generated semantic script: %d scenes for topic: %s",
        len(llm_script.scenes),
        llm_script.topic,
    )

    return EnrichedVideoScript.from_llm_output(llm_script)
