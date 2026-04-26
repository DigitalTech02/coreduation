"""Semantic LLM orchestrator — generates structured visual action scripts.

Instead of producing raw Manim code, the LLM outputs a JSON script describing
*what* to show using a fixed vocabulary of visual actions.  The deterministic
rendering engine then translates those actions into Manim.

Specialty prompts are loaded from ``prompts/`` based on the ``--category`` flag.
"""

import hashlib
import logging
import os

from dotenv import load_dotenv
from openai import OpenAI

from models_semantic import EnrichedVideoScript, SemanticVideoScript

load_dotenv()

logger = logging.getLogger(__name__)


def _hash_str(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:32]


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


def generate_semantic_script(
    topic: str,
    category: str = "auto",
) -> EnrichedVideoScript:
    """Generate a semantic video script for the given topic.

    *category* selects a specialty prompt from the ``prompts/`` registry.
    ``"auto"`` uses a fast LLM call to classify the topic first.

    Returns an ``EnrichedVideoScript`` ready for rendering.
    """
    from prompts import auto_detect_category, get_prompt

    if category == "auto":
        category = auto_detect_category(topic)
        logger.info("Auto-detected category: %s", category)

    specialty = get_prompt(category)
    system_prompt = specialty.build_system_prompt()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY is not set in environment")

    model = os.getenv("OPENAI_MODEL", "gpt-4.1")
    client = OpenAI(api_key=api_key)

    logger.info(
        "Generating semantic script for topic: %s (model: %s, category: %s)",
        topic, model, category,
    )

    user_content = (
        f"Create a comprehensive educational video script about: {topic}\n\n"
        f"Requirements:\n"
        f"- Target length: 4-8 minutes of narration (10-18 scenes)\n"
        f"- Include: real-world motivation, intuition building, "
        f"visual walkthroughs with concrete examples\n"
        f"- End with practical takeaways\n"
    )
    if specialty.user_prompt_extra:
        user_content += f"\n{specialty.user_prompt_extra}\n"
    user_content += "\nRespond with JSON only (no prose before or after)."

    prompt_hash = _hash_str(system_prompt, user_content)
    llm_script = None

    try:
        from caching import cached_llm_script, cache_llm_script
        cached = cached_llm_script(topic, category, prompt_hash, model)
        if cached:
            try:
                llm_script = SemanticVideoScript.model_validate(cached)
            except Exception as e:
                logger.warning("Cached LLM script failed validation, regenerating: %s", e)
                llm_script = None
    except Exception as e:
        logger.debug("LLM script cache lookup skipped: %s", e)

    if llm_script is None:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
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

        try:
            from caching import cache_llm_script
            cache_llm_script(topic, category, prompt_hash, model,
                             llm_script.model_dump(by_alias=True))
        except Exception as e:
            logger.debug("LLM script cache store skipped: %s", e)

    logger.info(
        "Generated semantic script: %d scenes for topic: %s",
        len(llm_script.scenes),
        llm_script.topic,
    )

    enriched = EnrichedVideoScript.from_llm_output(llm_script)
    enriched.category = category
    enriched.title_card_subtitle = specialty.title_card_subtitle
    return enriched
