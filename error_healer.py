"""LLM-powered Manim error recovery.

Catches rendering errors and asks OpenAI to fix the broken Manim code,
retrying up to a configurable number of attempts.
"""

import logging
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

logger = logging.getLogger(__name__)

HEALER_SYSTEM_PROMPT = """\
You are a Manim Community Edition v0.20.x debugging expert.

You will receive broken Manim code and the error message it produced.
Fix the code so it runs without errors.

RULES:
- Use Manim CE v0.20.x syntax ONLY.
- Keep the same visual intent — do not change what the animation shows.
- Allowed imports: from manim import *
- Allowed Mobjects: Text, MathTex, VGroup, Square, Circle, Arrow, NumberLine, Table, Code
- Allowed Animations: Create, Write, FadeIn, FadeOut, Transform, ReplacementTransform, Indicate
- DO NOT use: external assets, ManimGL syntax, ThreeDScene, or advanced plugins.
- Return ONLY the fixed Python code. No explanations, no markdown fences.\
"""


def heal_manim_code(
    original_code: str, error_message: str, max_retries: int = 3
) -> str:
    """Attempt to fix broken Manim CE code using an LLM.

    Returns the corrected code string.
    Raises RuntimeError after max_retries exhausted.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY is not set")

    model = os.getenv("OPENAI_MODEL", "gpt-4.1")
    client = OpenAI(api_key=api_key)

    current_code = original_code
    current_error = error_message

    for attempt in range(1, max_retries + 1):
        logger.warning(
            "Healing attempt %d/%d for code (error: %s...)",
            attempt,
            max_retries,
            current_error[:120],
        )

        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": HEALER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Original code:\n```python\n{current_code}\n```\n\n"
                        f"Error message:\n```\n{current_error}\n```\n\n"
                        f"Fix this Manim CE v0.20.x code. Return ONLY the corrected Python code."
                    ),
                },
            ],
        )

        fixed_code = completion.choices[0].message.content
        if fixed_code is None:
            logger.error("Healer returned empty response on attempt %d", attempt)
            continue

        fixed_code = _strip_markdown_fences(fixed_code)
        logger.info("Healer returned fixed code on attempt %d (%d chars)", attempt, len(fixed_code))
        return fixed_code

    raise RuntimeError(
        f"Failed to heal Manim code after {max_retries} attempts. "
        f"Last error: {current_error[:200]}"
    )


def _strip_markdown_fences(code: str) -> str:
    """Remove markdown code fences if the LLM wrapped its response."""
    code = code.strip()
    if code.startswith("```python"):
        code = code[len("```python"):]
    elif code.startswith("```"):
        code = code[3:]
    if code.endswith("```"):
        code = code[:-3]
    return code.strip()
