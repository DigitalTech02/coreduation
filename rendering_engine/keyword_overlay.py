"""Per-scene keyword burst — large faint background watermark word.

Pulls 1-2 high-signal words from the scene title + narration and renders
them as a huge translucent text mobject in the largest vacant region of
the canvas. Sits at z=-50, fades in at scene start, fades out before
``_clear_scene`` runs.

Goal: fill empty canvas space with a visual echo of what the narrator is
talking about, without competing with the actual content.

No LLM, no model dependency — purely deterministic word ranking.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from manim import (
    ApplyWave,
    FadeIn,
    FadeOut,
    Text,
    VGroup,
)

from rendering_engine.engine import BBox, SceneState
from rendering_engine.styles import (
    CATEGORY_ACCENT,
    FONT_SANS,
    PRIMARY,
)

logger = logging.getLogger(__name__)


# Common English stopwords + verbs/connectors that aren't visually evocative.
_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "do",
    "does", "for", "from", "had", "has", "have", "he", "her", "here", "him",
    "his", "how", "i", "if", "in", "into", "is", "it", "its", "just", "let",
    "me", "my", "no", "not", "now", "of", "on", "one", "only", "or", "our",
    "out", "over", "she", "so", "some", "such", "than", "that", "the",
    "their", "them", "then", "there", "these", "they", "this", "those",
    "to", "too", "up", "us", "use", "uses", "using", "very", "was", "we",
    "well", "were", "what", "when", "where", "which", "while", "who",
    "why", "will", "with", "would", "you", "your", "yours", "also",
    "about", "after", "again", "all", "any", "before", "being", "both",
    "each", "few", "more", "most", "other", "same", "should", "could",
    "must", "may", "might", "every", "much", "many", "ever", "even",
    "back", "down", "off", "between", "without", "since", "first",
    "second", "third", "next", "last", "another", "another's",
    "really", "actually", "basically", "literally", "essentially",
})


def _tokenise(text: str) -> list[str]:
    """Split *text* into lower-case alphanumeric tokens."""
    if not text:
        return []
    return [t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9_-]+", text)]


def extract_keyword(title: str, narration: str) -> str:
    """Pick the single best keyword to highlight for a scene.

    Strategy:
    1. Capitalised multi-letter words in narration (acronyms, technical
       terms) score highest — these are usually the entities under
       discussion (TCP, OAuth, JWT, Kubernetes).
    2. Words appearing in BOTH the title and narration score next.
    3. Otherwise the longest non-stopword token in the title.

    Returns "" when nothing usable is found.
    """
    if not (title or narration):
        return ""

    # 1. Acronyms / proper nouns — capitalised, length ≥ 2, in narration.
    cap_pattern = re.compile(r"\b[A-Z][A-Za-z0-9_-]{1,}\b")
    caps = cap_pattern.findall(narration or "")
    caps = [c for c in caps if c.lower() not in _STOPWORDS and len(c) >= 2]
    if caps:
        # Prefer fully-uppercase acronyms (TCP, JWT, HTTPS) over Title Case.
        caps_sorted = sorted(
            caps,
            key=lambda w: (w.isupper(), len(w), -caps.index(w)),
            reverse=True,
        )
        return caps_sorted[0]

    title_tokens = [t for t in _tokenise(title) if t not in _STOPWORDS and len(t) >= 4]
    narr_tokens = set(t for t in _tokenise(narration) if t not in _STOPWORDS)

    # 2. Title × narration intersection — longest wins.
    overlap = [t for t in title_tokens if t in narr_tokens]
    if overlap:
        overlap.sort(key=len, reverse=True)
        return overlap[0].upper() if len(overlap[0]) <= 5 else overlap[0].title()

    # 3. Longest title word.
    if title_tokens:
        title_tokens.sort(key=len, reverse=True)
        word = title_tokens[0]
        return word.upper() if len(word) <= 5 else word.title()

    return ""


def play_keyword_burst(
    scene: Any, state: SceneState, scene_dict: dict, *, category: str = "",
) -> Any | None:
    """Render the scene's keyword as a faint background word in vacant space.

    Returns the mobject so the caller can fade it out at scene end. Returns
    ``None`` when disabled, when no keyword is extractable, or when the
    canvas is already full.
    """
    try:
        from config import ENABLE_KEYWORD_BURST
    except Exception:
        ENABLE_KEYWORD_BURST = True
    if not ENABLE_KEYWORD_BURST:
        return None

    title = scene_dict.get("title", "") or ""
    narration = scene_dict.get("narration", "") or ""
    keyword = extract_keyword(title, narration)
    if not keyword or len(keyword) > 18:
        return None

    # Find a vacant region BEFORE any of the scene's actions render — the
    # only thing on the canvas at this point is persistent topology + the
    # topic header. We only place a burst when there's a substantial
    # vacant region available.
    region = state.find_largest_vacant_region(min_width=3.0, min_height=1.5)
    if region is None:
        return None

    avail_w = region.right - region.left
    avail_h = region.top - region.bottom
    if avail_w < 3.0 or avail_h < 1.5:
        return None

    # Build the word at a large font, then scale to fit ~85% of the region.
    accent = CATEGORY_ACCENT.get(category, PRIMARY)
    word = Text(keyword, font_size=120, color=accent, weight="BOLD", font=FONT_SANS)
    target_w = avail_w * 0.88
    target_h = avail_h * 0.78
    scale = min(target_w / max(0.1, word.width), target_h / max(0.1, word.height), 1.0)
    if scale < 0.99:
        word.scale(scale)

    # Center inside the vacant region.
    cx = (region.left + region.right) / 2
    cy = (region.bottom + region.top) / 2
    word.move_to([cx, cy, 0])

    # Translucent — must NOT compete with primary content.
    word.set_fill(accent, opacity=0.10)
    word.set_stroke(accent, width=0.6, opacity=0.18)
    word.set_z_index(-50)

    try:
        scene.play(FadeIn(word, run_time=0.5))
    except Exception:
        scene.add(word)

    # Subtle wave once, ignored on failure (some Manim builds choke on
    # ApplyWave for very wide text).
    try:
        scene.play(ApplyWave(word, amplitude=0.08, run_time=0.5))
    except Exception:
        pass

    return word


def fade_out_keyword_burst(scene: Any, mob: Any) -> None:
    """Fade out a previously placed keyword burst, ignoring failures."""
    if mob is None:
        return
    try:
        scene.play(FadeOut(mob, run_time=0.35))
        scene.remove(mob)
    except Exception:
        try:
            scene.remove(mob)
        except Exception:
            pass
