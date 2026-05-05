"""Generate viral 4-scene vertical short scripts.

Produces an ``EnrichedVideoScript`` ready to feed into the shorts rendering
pipeline.  Reuses the same JSON schema as long-form so audio mux, manifest
builder, subtitle scheduler, and frame validator work unchanged.
"""

from __future__ import annotations

import hashlib
import json as _json
import logging
import os

from dotenv import load_dotenv
from openai import OpenAI

from llm_orchestrator_semantic import _sanitize_script_dict, _strip_json_fences
from models_semantic import EnrichedVideoScript, SemanticVideoScript
from prompts.shorts import (
    SHORTS_SYSTEM_PROMPT,
    VERTICAL_ACTION_WHITELIST,
    build_shorts_user_prompt,
)

load_dotenv()

logger = logging.getLogger(__name__)

# Hard cap on scenes a short can have, regardless of LLM output.  Excess
# scenes are dropped — the prompt insists on exactly 4 but defensive trim
# protects against over-generation.
_MAX_SHORTS_SCENES = 4


def _filter_to_vertical_actions(data: dict) -> dict:
    """Strip actions outside the vertical whitelist.

    Wide actions (topology, sequence diagrams, comparisons, tables, charts)
    would clip on a 1080x1920 canvas.  We refuse to render them rather than
    let the LLM override the layout invariant.
    """
    for scene in data.get("scenes", []):
        cleaned = []
        for act in scene.get("actions", []):
            atype = act.get("type", "")
            if atype in VERTICAL_ACTION_WHITELIST:
                cleaned.append(act)
            else:
                logger.warning(
                    "Stripping non-vertical action type '%s' from short scene '%s'",
                    atype, scene.get("scene_id", "?"),
                )
        scene["actions"] = cleaned
    return data


def _truncate_scenes(data: dict, max_scenes: int = _MAX_SHORTS_SCENES) -> dict:
    scenes = data.get("scenes", [])
    if len(scenes) > max_scenes:
        logger.warning(
            "Shorts LLM emitted %d scenes; truncating to %d", len(scenes), max_scenes,
        )
        data["scenes"] = scenes[:max_scenes]
    return data


def _hash_str(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:32]


def generate_shorts_script(
    topic: str,
    long_form_script: EnrichedVideoScript | None = None,
    category: str = "",
) -> EnrichedVideoScript:
    """Generate a viral 4-scene vertical short for the given topic.

    Args:
        topic: The same topic as the long-form video (or standalone if no
            long form was generated).
        long_form_script: Optional long-form ``EnrichedVideoScript`` for the
            same topic.  Its title and final-takeaway narration are passed
            as context so the short's CTA references the same framing.
        category: One of the eight category names (networking, security, ...);
            used for theming and SFX selection.  Empty string is fine for
            shorts — the short doesn't need specialty pedagogical structure
            since it's a single self-contained beat.

    Returns:
        An ``EnrichedVideoScript`` with exactly <=4 scenes, audio-ready.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY is not set in environment")

    model = os.getenv("OPENAI_MODEL", "gpt-4.1")
    client = OpenAI(api_key=api_key)

    long_excerpt: str | None = None
    if long_form_script and long_form_script.scenes:
        last = long_form_script.scenes[-1]
        long_excerpt = (
            f"Long-form title: {long_form_script.title}\n"
            f"Long-form takeaway: {last.narration[:600]}"
        )

    user_content = build_shorts_user_prompt(topic, long_excerpt)

    logger.info(
        "Generating shorts script for topic: %s (model: %s, category: %s)",
        topic, model, category,
    )

    prompt_hash = _hash_str(SHORTS_SYSTEM_PROMPT, user_content)
    llm_script: SemanticVideoScript | None = None

    # Cache shorts under a distinct namespace so they don't collide with the
    # long-form script cache for the same topic.
    cache_key_topic = f"shorts::{topic}"
    try:
        from caching import cache_llm_script, cached_llm_script
        cached = cached_llm_script(cache_key_topic, category, prompt_hash, model)
        if cached:
            try:
                cached = _sanitize_script_dict(cached)
                cached = _filter_to_vertical_actions(cached)
                cached = _truncate_scenes(cached)
                llm_script = SemanticVideoScript.model_validate(cached)
            except Exception as e:
                logger.warning("Cached shorts script failed validation, regenerating: %s", e)
                llm_script = None
    except Exception as e:
        logger.debug("Shorts cache lookup skipped: %s", e)

    if llm_script is None:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SHORTS_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
        )

        raw = completion.choices[0].message.content
        if not raw:
            raise ValueError("Shorts LLM returned empty content")

        try:
            raw_dict = _json.loads(_strip_json_fences(raw))
            raw_dict = _sanitize_script_dict(raw_dict)
            raw_dict = _filter_to_vertical_actions(raw_dict)
            raw_dict = _truncate_scenes(raw_dict)
            llm_script = SemanticVideoScript.model_validate(raw_dict)
        except Exception as e:
            logger.error("Failed to parse shorts script JSON: %s", e)
            logger.debug("Raw response (first 2000 chars): %s", raw[:2000])
            raise

        try:
            from caching import cache_llm_script
            cache_llm_script(
                cache_key_topic, category, prompt_hash, model,
                llm_script.model_dump(by_alias=True),
            )
        except Exception as e:
            logger.debug("Shorts cache store skipped: %s", e)

    enriched = EnrichedVideoScript.from_llm_output(llm_script)
    enriched.category = category
    enriched.title_card_subtitle = ""  # shorts don't render a title card

    logger.info(
        "Generated shorts script: %d scenes for '%s'",
        len(enriched.scenes), enriched.title,
    )
    return enriched
