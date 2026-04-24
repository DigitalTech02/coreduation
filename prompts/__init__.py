"""Specialty prompt registry — maps category names to SpecialtyPrompt instances."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prompts._base import SpecialtyPrompt

logger = logging.getLogger(__name__)

CATEGORIES: list[str] = [
    "networking",
    "data-structures",
    "programming",
    "cloud-architecture",
    "system-design",
    "business-analysis",
    "databases",
    "security",
]


def _load_registry() -> dict[str, SpecialtyPrompt]:
    from prompts.networking import PROMPT as networking
    from prompts.data_structures import PROMPT as data_structures
    from prompts.programming import PROMPT as programming
    from prompts.cloud_architecture import PROMPT as cloud_architecture
    from prompts.system_design import PROMPT as system_design
    from prompts.business_analysis import PROMPT as business_analysis
    from prompts.databases import PROMPT as databases
    from prompts.security import PROMPT as security

    return {
        "networking": networking,
        "data-structures": data_structures,
        "programming": programming,
        "cloud-architecture": cloud_architecture,
        "system-design": system_design,
        "business-analysis": business_analysis,
        "databases": databases,
        "security": security,
    }


_registry: dict[str, SpecialtyPrompt] | None = None


def _get_registry() -> dict[str, SpecialtyPrompt]:
    global _registry
    if _registry is None:
        _registry = _load_registry()
    return _registry


def get_prompt(category: str) -> SpecialtyPrompt:
    reg = _get_registry()
    key = category.strip().lower()
    if key not in reg:
        logger.warning("Unknown category '%s', falling back to 'networking'", key)
        key = "networking"
    return reg[key]


def auto_detect_category(topic: str) -> str:
    """Ask a fast LLM call to classify the topic into one of the categories."""
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "networking"

    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL_FAST", os.getenv("OPENAI_MODEL", "gpt-4.1"))

    categories_str = ", ".join(CATEGORIES)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    f"You are a topic classifier. Given a video topic, reply with "
                    f"exactly ONE of these categories (nothing else): {categories_str}"
                ),
            },
            {"role": "user", "content": topic},
        ],
        max_tokens=20,
        temperature=0,
    )

    raw = (resp.choices[0].message.content or "").strip().lower()
    if raw in CATEGORIES:
        return raw

    for cat in CATEGORIES:
        if cat in raw:
            return cat

    logger.warning("Auto-detect returned '%s', falling back to 'networking'", raw)
    return "networking"
