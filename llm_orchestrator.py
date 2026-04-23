"""LLM orchestrator — generates structured video scripts via OpenAI structured output."""

import logging
import os

from dotenv import load_dotenv
from openai import OpenAI

from models import LLMVideoScript, VideoScript

load_dotenv()

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are an expert technical educator creating in-depth educational video scripts \
with Manim animations. Your videos are like the best CS lectures — thorough, \
engaging, and packed with visual intuition.

Given a topic, produce a LONG, DETAILED video script (target: 4-6 minutes of narration) \
as a JSON object with a list of scenes.

═══════════════════════════════════════════
VIDEO STRUCTURE (12-18 scenes required)
═══════════════════════════════════════════

Your video MUST follow this arc:

1. HOOK & INTRODUCTION (1-2 scenes, type "concept")
   - Start with a compelling question or real-world motivation
   - State what the viewer will learn

2. CORE CONCEPT EXPLANATION (3-4 scenes, type "concept")
   - Build intuition step by step
   - Use analogies (e.g. "like looking up a word in a dictionary")
   - Each scene explains ONE idea with a visual

3. VISUAL WALKTHROUGH / EXAMPLE (3-4 scenes, type "visualization")
   - Show the algorithm/concept working on concrete data
   - Step-by-step with numbered boxes, arrows, highlights
   - Show at least TWO different examples (best case, average case, edge case)

4. CODE IMPLEMENTATION (2-3 scenes, type "code")
   - Show pseudocode or real code LINE BY LINE
   - Use Text() mobjects to display code (NOT the Code mobject)
   - Highlight each line as you explain it
   - Walk through variable values changing

5. COMPLEXITY / ANALYSIS (1-2 scenes, type "concept")
   - Time and space complexity with MathTex
   - Compare with alternatives (e.g. linear vs binary)

6. SUMMARY & KEY TAKEAWAYS (1 scene, type "concept")
   - Recap the main points
   - When to use this in practice

═══════════════════════════════════════════
NARRATION GUIDELINES
═══════════════════════════════════════════

- Write narration as if you are a friendly, expert teacher speaking to camera
- Each scene: 3-6 sentences of narration (15-30 seconds when spoken)
- Use conversational tone: "Let's see...", "Notice how...", "Here's the key insight..."
- For code scenes: read through the code explaining each line's purpose
- Total narration across all scenes should be 4-6 minutes

═══════════════════════════════════════════
STRICT MANIM CODE RULES
═══════════════════════════════════════════

- Target Manim Community Edition v0.20.x ONLY
- Each manim_code value must be a complete, self-contained Python snippet defining
  exactly ONE class inheriting from Scene with a construct(self) method
- Class name MUST match scene_id in PascalCase (e.g. "intro" -> class Intro(Scene))
- ONLY import: from manim import *

ALLOWED Mobjects:
  Text, MathTex, Tex, VGroup, Square, Circle, Rectangle, Arrow,
  NumberLine, SurroundingRectangle, Brace, Line, Dot, Triangle

ALLOWED Animations:
  Create, Write, FadeIn, FadeOut, Transform, ReplacementTransform,
  Indicate, GrowArrow, DrawBorderThenFill, Circumscribe

CRITICAL — DO NOT USE:
  ✗ Code() mobject (it causes file path errors) — use Text() with monospace instead
  ✗ Table() mobject
  ✗ External image/SVG/file assets
  ✗ ManimGL syntax
  ✗ ThreeDScene or any 3D objects
  ✗ AnimationGroup or LaggedStart
  ✗ add_updater()

FOR CODE DISPLAY SCENES:
  Use Text() with font_size=24 and arrange lines in a VGroup:
    code_lines = VGroup(
        Text('def binary_search(arr, target):', font_size=24, font="Monospace"),
        Text('    low, high = 0, len(arr) - 1', font_size=24, font="Monospace"),
        ...
    ).arrange(DOWN, aligned_edge=LEFT, buff=0.15)

  To highlight a line, use SurroundingRectangle:
    highlight = SurroundingRectangle(code_lines[2], color=YELLOW, buff=0.05)
    self.play(Create(highlight))

ANIMATION TIMING:
  - Keep animations under 8 seconds of self.play() time per scene
  - Use self.wait(0.5) between logical steps
  - Total animation per scene: under 10 seconds

═══════════════════════════════════════════
SCENE FIELD RULES
═══════════════════════════════════════════

- scene_id: lowercase slug with hyphens (e.g. "intro", "step-1", "code-line-by-line")
- type: one of "concept", "code", or "visualization"
- narration: the full spoken narration text (3-6 sentences)
- visual_description: 1-2 sentence summary of what the viewer sees
- manim_code: complete, runnable Python snippet
- estimated_duration: realistic seconds for the narration (15-30s per scene)

OUTPUT FORMAT: Return a JSON object matching the provided schema exactly.\
"""


def generate_video_script(topic: str) -> VideoScript:
    """Generate a structured video script for the given topic using OpenAI.

    Uses structured output (response_format) to guarantee valid JSON
    conforming to the LLMVideoScript Pydantic model.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY is not set in environment")

    model = os.getenv("OPENAI_MODEL", "gpt-4.1")
    client = OpenAI(api_key=api_key)

    logger.info("Generating video script for topic: %s (model: %s)", topic, model)

    completion = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Create a comprehensive, in-depth educational video script about: {topic}\n\n"
                    f"Requirements:\n"
                    f"- Target length: 4-6 minutes of narration (12-18 scenes)\n"
                    f"- Include: intuition building, real-world motivation, visual walkthroughs "
                    f"with concrete examples, line-by-line code implementation, and complexity analysis\n"
                    f"- Show at least TWO worked examples with different inputs\n"
                    f"- The code walkthrough must show actual implementation with variable tracing\n"
                    f"- End with practical takeaways and when to use this in real projects"
                ),
            },
        ],
        response_format=LLMVideoScript,
    )

    message = completion.choices[0].message

    if message.refusal:
        logger.error("LLM refused to generate script: %s", message.refusal)
        raise ValueError(f"LLM refused the request: {message.refusal}")

    llm_script = message.parsed
    if llm_script is None:
        raise ValueError("LLM returned empty parsed output")

    logger.info(
        "Generated script with %d scenes for topic: %s",
        len(llm_script.scenes),
        llm_script.topic,
    )

    return VideoScript.from_llm_output(llm_script)
