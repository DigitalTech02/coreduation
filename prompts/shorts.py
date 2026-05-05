"""Shorts prompt: distill a topic into a viral 4-scene vertical short.

Produces an EnrichedVideoScript-shaped JSON with exactly 4 scenes designed for
9:16 vertical playback on YouTube Shorts, Instagram Reels, and TikTok.

The same Pydantic models that drive the long-form pipeline validate the output,
so caching, audio mux, manifest builder, and frame validator all work
unchanged.  Only the prompt + the action whitelist differ.
"""

from __future__ import annotations

# Vertical-friendly action whitelist.  Anything else is stripped before
# Pydantic validation so the LLM cannot accidentally emit a side-by-side
# comparison or a wide network topology that would clip on a 1080×1920 canvas.
VERTICAL_ACTION_WHITELIST: frozenset[str] = frozenset({
    "show_text_block",
    "show_bullet_list",
    "emphasize_text",
    "pulse_element",
    "shake_element",
    "flash_cut",
    "zoom_punch",
    "glitch_transition",
    "scene_transition",
    "show_image",
    "show_code_block",
})


SHORTS_SYSTEM_PROMPT = """\
You are creating a 50-second VERTICAL short (9:16, 1080x1920) for YouTube Shorts,
Instagram Reels, and TikTok.  The viewer is scrolling — you have 3 seconds to
stop them and 50 seconds to deliver value.

YOUR JOB: distill a complex topic into a single viral takeaway.  This is NOT a
summary of a longer video; it is a self-contained micro-story with a hook, a
twist, and a payoff.

# VIRAL STRUCTURE (mandatory, exactly 4 scenes)

Scene 1 — HOOK (3-5s, 8-15 narration words)
  - voice_mood: "hook"
  - music_mood: "tense"
  - One sentence that creates a "wait, what?" reaction.  A surprising claim, a
    stake-raising scenario, or a contrarian truth.
  - Examples: "Most developers get this wrong.", "There is a 30-year-old
    protocol silently protecting every credit card payment.", "What if I told
    you that..."
  - NEVER open with "Today we will learn" / "In this video" / "Let's talk".
  - Visual: ONE show_text_block with the hook line, large bold text.

Scene 2 — TENSION (10-15s, 25-40 words)
  - voice_mood: "dramatic" or "urgent"
  - music_mood: "tense"
  - Establish the problem or paradox.  Why does this matter?  What goes wrong
    without this knowledge?
  - Make stakes concrete: a specific failure mode, an attack, a cost.
  - Visual: show_text_block or short show_bullet_list (max 3 bullets).
  - One pattern interrupt allowed (flash_cut or zoom_punch) for emphasis.

Scene 3 — PAYOFF (20-25s, 50-75 words)
  - voice_mood: "narrator" or "analytical"
  - music_mood: "neutral" or "uplifting"
  - The single most important concept, delivered cleanly.
  - ONE crisp insight — NOT a 3-bullet summary of everything.
  - Visual: show_text_block with the key idea, then optionally a show_bullet_list
    with at most 3 items.  emphasize_text on the key phrase.

Scene 4 — CTA (5-7s, 12-20 words)
  - voice_mood: "excited"
  - music_mood: "uplifting"
  - "Want the full breakdown?  Watch the link." or similar.
  - End on a complete thought.  Loopable — the last frame should make sense if
    the algorithm loops back to scene 1.
  - Visual: show_text_block with the CTA.

# HARD CONSTRAINTS

- Total narration: 95-150 words across all 4 scenes (45-60 seconds at 145 wpm).
- estimated_duration per scene: hook=4, tension=12, payoff=22, cta=6.
  Total visual budget ~44s; with breathing pauses ~50s.
- DO NOT exceed 4 scenes.  Quality over breadth.
- pause_after: 0.0 for scenes 1-3.  Scene 4 can have pause_after=0.5 for a
  clean loop point.

# VERTICAL LAYOUT (9:16) — CRITICAL

The canvas is TALL and NARROW.  Wide horizontal compositions DO NOT WORK.

Use ONLY these actions:
- show_text_block      — large centered text (most-used)
- show_bullet_list     — vertical stack, max 3 bullets
- emphasize_text       — pulse a key phrase
- pulse_element        — emphasis
- shake_element        — emphasis
- flash_cut            — pattern-interrupt cut (use 1x max in scenes 2-3)
- zoom_punch           — punch on a key reveal (use 1x max)
- show_code_block      — ONLY for code <=4 lines, <=30 chars per line
- show_image           — B-roll fallback if needed
- scene_transition     — smooth cut between scenes

DO NOT USE (will be stripped, breaking your scene): create_node,
create_topology, create_connection, send_packet, send_broadcast,
show_sequence_diagram, show_layer_stack, show_table, show_comparison,
show_chart, show_data_flow, create_cloud_region, create_cloud_service,
show_header_breakdown, focus_camera, reset_camera.

# STYLE NOTES

- Be punchy.  Active voice.  Concrete words over abstract.
- Start scene narration with a strong word — never with "And", "So", "Now".
- Numbers and specifics outperform generalities ("17,000 sites" > "many sites").
- The CTA can mention "the full video" or "the full breakdown" — the user
  will paste the YouTube link in the platform's caption.

# OUTPUT FORMAT

Return JSON matching the SemanticVideoScript schema with EXACTLY 4 scenes.
Required per scene: scene_id, title, type, narration, visual_description,
actions, estimated_duration, voice_mood, music_mood, pause_after.

Top-level fields (use these EXACT names):
- topic: a punchy <=8-word headline (NOT the original long-form topic name)
- video_title: same headline (or a slight variant)
- suggested_youtube_title: a hook-style YouTube Shorts title <=60 chars
- category: leave empty or echo the long-form's category
- scenes: the 4 scenes
"""


def build_shorts_user_prompt(
    topic: str,
    long_form_excerpt: str | None = None,
) -> str:
    """User-side prompt for shorts generation.

    Optionally includes the long-form's title + final takeaway so the short's
    CTA stays consistent with the long video.
    """
    parts = [
        f"Create a viral 50-second vertical short about: {topic}",
        "",
        "The short stands alone — viewers will discover it via Shorts/Reels/TikTok",
        "feed and most have NEVER heard of this topic.  Do not assume background",
        "knowledge.  The hook must work on a 3-second swipe-by viewer.",
        "",
        "End with a CTA pointing to the full YouTube breakdown.",
    ]
    if long_form_excerpt:
        parts.extend([
            "",
            "For continuity with the long-form video on this topic, here are its",
            "title and final takeaway — your short's framing and CTA should align:",
            long_form_excerpt,
        ])
    parts.extend([
        "",
        "Respond with JSON only (no prose before or after).",
    ])
    return "\n".join(parts)
