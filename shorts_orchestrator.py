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


def _inject_ai_illustrations(data: dict, topic: str) -> dict:
    """Auto-inject a ``show_image`` action at the start of every shorts scene.

    Gated by ``config.ENABLE_AI_BROLL`` — if disabled, this is a no-op.
    Otherwise: for each scene without an existing show_image action, derive
    a vibrant cartoon-style DALL-E prompt from the scene's narration +
    voice_mood and prepend a show_image action.  The DALL-E call happens
    lazily inside ``render_show_image`` (cached on disk by prompt hash).

    Why auto-inject vs. asking the LLM to emit image_prompt: the LLM will
    forget half the time, and even when it remembers the prompts are
    inconsistent in style.  Auto-derivation guarantees every scene gets
    a visually consistent illustration in the user's preferred style.
    """
    try:
        from config import ENABLE_AI_BROLL
    except Exception:
        return data
    if not ENABLE_AI_BROLL:
        return data

    for scene in data.get("scenes", []):
        actions = scene.get("actions") or []
        # Skip if LLM already emitted show_image for this scene
        if any((a or {}).get("type") == "show_image" for a in actions):
            continue

        prompt = _derive_image_prompt(
            scene_id=scene.get("scene_id", ""),
            narration=scene.get("narration", ""),
            voice_mood=scene.get("voice_mood", ""),
            topic=topic,
        )
        if not prompt:
            continue

        # Use a chunk of the scene's audio budget for the Ken Burns reveal —
        # capped at 2.2 s so the image doesn't eat the whole scene.  Caller
        # later renders text/bullets after the image fades out.
        est_dur = float(scene.get("estimated_duration", 8.0) or 8.0)
        ken_burns_dur = max(1.4, min(2.2, est_dur * 0.32))

        actions.insert(0, {
            "type": "show_image",
            "image_path": "",
            "image_prompt": prompt,
            "duration": ken_burns_dur,
            "pan": "in",
            "caption": "",
        })
        scene["actions"] = actions
        logger.info(
            "Injected AI broll into shorts scene '%s' (prompt: %r)",
            scene.get("scene_id", "?"), prompt[:80],
        )

    return data


_AI_BROLL_BASE_STYLE = (
    "vibrant flat cartoon illustration, neon accent colors, dark navy "
    "background, bold outlines, vector style, centered composition, "
    "no text, clean infographic style, square 1:1"
)


def _derive_image_prompt(
    scene_id: str, narration: str, voice_mood: str, topic: str,
) -> str:
    """Heuristic: pick a vibrant subject for this scene's DALL-E illustration.

    Routes by scene_id keywords + voice_mood + narration content so each
    scene of a story arc (hook → tension → payoff → CTA) gets a distinct
    but stylistically consistent illustration.
    """
    sid = (scene_id or "").lower()
    mood = (voice_mood or "").lower()
    text = (narration or "").lower()
    topic_short = topic[:60]

    is_cta = any(k in sid for k in ("cta", "outro", "watch", "tap", "link")) \
        or "full breakdown" in text or "link in description" in text
    is_hook = sid.startswith("hook") or mood == "hook" \
        or any(k in text[:80] for k in ("imagine", "what if", "every time"))
    is_attack = any(k in text for k in (
        "attack", "hack", "steal", "spy", "intercept", "leak", "broken", "fake",
    ))
    is_secure = any(k in text for k in (
        "secure", "encrypt", "verify", "shield", "protect", "safe", "lock",
    ))

    if is_cta:
        subject = (
            "smartphone with a glowing red play button on screen, finger "
            "tapping, gold spark accents, viral video thumbnail vibe"
        )
    elif is_hook:
        subject = (
            f"alarming concept illustration about {topic_short}, urgent "
            "atmosphere, glowing neon red highlights, eye-catching"
        )
    elif is_attack:
        subject = (
            "shadowy hacker silhouette with broken padlock and red lightning, "
            "data leak motif, danger, neon red and orange"
        )
    elif is_secure:
        subject = (
            "glowing green padlock with shield, encryption symbols flowing, "
            "secure handshake between two devices, neon green and blue"
        )
    elif mood in ("dramatic", "urgent"):
        subject = (
            f"dramatic concept illustration about {topic_short}, intense red "
            "and orange lighting, motion blur, big bold central object"
        )
    else:
        subject = (
            f"clean concept illustration explaining {topic_short}, friendly "
            "robot mascot pointing at the key idea, neon blue accents"
        )

    return f"{subject}, {_AI_BROLL_BASE_STYLE}"


def _split_at_natural_break(text: str, max_title_chars: int = 35) -> tuple[str, str]:
    """Split a long sentence into (title, body) at the most punchy break.

    Priority of split points: em-dash → colon → first comma → word boundary
    near max_title_chars.  Returns (title, body); body may be empty if the
    text is already short enough to be one title.

    Example:
        "No one told you—every secure website hides a secret handshake"
        → ("No one told you", "every secure website hides a secret handshake")
    """
    s = (text or "").strip()
    if not s:
        return "", ""

    # Title is fine as-is when short enough
    if len(s) <= max_title_chars:
        return s, ""

    # Em-dash split (highest signal — typically marks the punch line)
    for em in ("—", "–", " - "):
        if em in s:
            idx = s.find(em)
            title = s[:idx].strip().rstrip(".,;:!?")
            body = s[idx + len(em):].strip()
            if title and 4 <= len(title) <= max_title_chars + 15:
                return title, body

    # Colon split
    if ":" in s:
        idx = s.find(":")
        title = s[:idx].strip()
        body = s[idx + 1:].strip()
        if title and 4 <= len(title) <= max_title_chars + 15:
            return title, body

    # First comma
    if "," in s:
        idx = s.find(",")
        title = s[:idx].strip()
        body = s[idx + 1:].strip()
        if title and 4 <= len(title) <= max_title_chars + 10:
            return title, body

    # Last resort: word-boundary truncate
    words = s.split()
    title_words: list[str] = []
    char_count = 0
    for w in words:
        if char_count + len(w) + (1 if title_words else 0) > max_title_chars:
            break
        title_words.append(w)
        char_count += len(w) + (1 if len(title_words) > 1 else 0)
    if title_words:
        title = " ".join(title_words).rstrip(".,;:!?")
        rest = s[len(" ".join(title_words)):].lstrip(" ,.;:!?")
        return title, rest
    return s, ""


_MAX_SHORTS_BODY_CHARS = 110


def _trim_body_to_one_sentence(body: str, max_chars: int = _MAX_SHORTS_BODY_CHARS) -> str:
    """Cap a verbose body at the first sentence boundary, max ~110 chars.

    The LLM frequently emits 200-char paragraphs into ``body`` which then
    wrap to 9 narrow lines on a 9:16 canvas — reads as "wall of text",
    not "infographic".  Cap to one short sentence.
    """
    s = (body or "").strip()
    if len(s) <= max_chars:
        return s

    # Try to end at a sentence boundary within max_chars.
    cutoff = -1
    for i, ch in enumerate(s[:max_chars + 20]):
        if ch in ".!?" and (i + 1 == len(s) or s[i + 1] == " "):
            cutoff = i + 1
            break
    if 30 <= cutoff <= max_chars + 20:
        return s[:cutoff].strip()

    # Otherwise truncate at last word boundary before max_chars.
    truncated = s[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > 30:
        truncated = truncated[:last_space]
    return truncated.rstrip(",;:- ") + "..."


def _split_long_titles(data: dict) -> dict:
    """Walk every show_text_block; split long titles, trim long bodies.

    1.  Title > 40 chars AND body empty → split at natural break point.
        Prevents the renderer's auto-shrink from compressing big-font
        titles into 30pt mush.
    2.  Body > 110 chars → trim to first sentence (or word boundary).
        Prevents 200-char paragraphs from wrapping to 9 narrow lines.
    """
    for scene in data.get("scenes", []):
        for act in scene.get("actions", []) or []:
            if (act or {}).get("type") != "show_text_block":
                continue
            title = (act.get("title") or "").strip()
            body = (act.get("body") or "").strip()

            # Split long title into title + body
            if title and not body and len(title) > 40:
                new_title, new_body = _split_at_natural_break(title)
                if new_body:
                    act["title"] = new_title
                    act["body"] = new_body
                    title = new_title
                    body = new_body
                    logger.info(
                        "Split long title in scene '%s': %r → %r + %r",
                        scene.get("scene_id", "?"),
                        (title + " " + body)[:40],
                        new_title[:40], new_body[:40],
                    )

            # Trim long body to one sentence
            if body and len(body) > _MAX_SHORTS_BODY_CHARS:
                trimmed = _trim_body_to_one_sentence(body)
                if trimmed != body:
                    act["body"] = trimmed
                    logger.info(
                        "Trimmed long body in scene '%s' (%d → %d chars)",
                        scene.get("scene_id", "?"), len(body), len(trimmed),
                    )

    return data


def _inject_lottie_icons(data: dict) -> dict:
    """Auto-inject ``show_lottie`` actions on key shorts scenes.

    Per-scene icon mapping (positional, robust to LLM mood variations):
      Scene 1 (hook)    — no Lottie (AI illustration carries the visual)
      Scene 2 (tension) — warning_alert  (yellow ⚠ pop-in mid-scene)
      Scene 3 (payoff)  — success_check  (green ✓ at the climax beat)
      Scene 4 (CTA)     — swipe_arrow    (gold ↗ before the CTA overlay)

    Append (not prepend) so the AI illustration plays first, then the
    icon punctuates after the main content reveals.
    """
    scenes = data.get("scenes") or []
    if not scenes:
        return data

    icon_for_scene = {
        1: "warning_alert",
        2: "success_check",
        3: "swipe_arrow",
    }
    if len(scenes) < 4:
        return data

    for idx, icon_id in icon_for_scene.items():
        if idx >= len(scenes):
            continue
        scene = scenes[idx]
        actions = scene.get("actions") or []
        # Don't inject if LLM already emitted a Lottie for this scene
        if any((a or {}).get("type") == "show_lottie" for a in actions):
            continue
        actions.append({
            "type": "show_lottie",
            "lottie_id": icon_id,
            "duration": 1.0,
            "position": "upper",
            "scale": 2.4,
        })
        scene["actions"] = actions
        logger.info(
            "Injected show_lottie %r on shorts scene %d (%s)",
            icon_id, idx, scene.get("scene_id", "?"),
        )

    return data


def _inject_pattern_interrupts(data: dict) -> dict:
    """Force-inject pattern-interrupt actions on key scene positions.

    Director's brief from the user:
      Scene 1 (hook):    MUST start with zoom_punch  (stops the scroll)
      Scene 3 (payoff):  MUST start with flash_cut   (marks the reveal)

    Both are visible AND audible — SFX_MAP ties zoom_punch to
    cinematic_impact_hit and flash_cut to suspenseful_boom.  If the LLM
    already emitted them, this is a no-op.
    """
    scenes = data.get("scenes") or []
    if not scenes:
        return data

    def _has_action_type(scene: dict, atype: str) -> bool:
        return any(
            (a or {}).get("type") == atype
            for a in scene.get("actions") or []
        )

    # Scene 1 — hook: zoom_punch
    if len(scenes) >= 1:
        s1 = scenes[0]
        if not _has_action_type(s1, "zoom_punch"):
            actions = list(s1.get("actions") or [])
            actions.insert(0, {
                "type": "zoom_punch",
                "duration": 0.30,
                "scale": 1.18,
            })
            s1["actions"] = actions
            logger.info("Injected zoom_punch at start of hook scene '%s'",
                        s1.get("scene_id", "?"))

    # Scene 3 — payoff: flash_cut (only when there are >= 3 scenes;
    # otherwise the structure isn't hook → tension → payoff → cta).
    if len(scenes) >= 3:
        s3 = scenes[2]
        if not _has_action_type(s3, "flash_cut"):
            actions = list(s3.get("actions") or [])
            actions.insert(0, {
                "type": "flash_cut",
                "color": "white",
                "duration": 0.18,
            })
            s3["actions"] = actions
            logger.info("Injected flash_cut at start of payoff scene '%s'",
                        s3.get("scene_id", "?"))

    return data


def _enrich_empty_actions(data: dict) -> dict:
    """Repair empty action content so shorts never render a blank canvas.

    The LLM sometimes emits ``show_text_block`` with empty ``title``/``body``
    placeholders.  In long-form that's fine because the persistent topic
    header + intro card + outro card give the viewer something to look at.
    In a 9:16 short with no chrome, an empty action means a black frame.

    Two repairs:
    1. If a ``show_text_block`` has empty title AND body, fill ``body`` from
       the scene narration (truncated to ~140 chars so it fits a vertical card).
    2. If a scene has zero non-empty actions, inject a default
       ``show_text_block`` whose body is the narration.

    This is shorts-specific defensive enrichment.  Long-form runs untouched.
    """
    for scene in data.get("scenes", []):
        narration = (scene.get("narration") or "").strip()
        actions = scene.get("actions") or []

        for act in actions:
            if act.get("type") != "show_text_block":
                continue
            title = (act.get("title") or "").strip()
            body = (act.get("body") or "").strip()
            if title or body:
                continue
            if narration:
                # Use first sentence as title (short, punchy), rest as body.
                first_sentence_end = -1
                for terminator in (". ", "! ", "? "):
                    idx = narration.find(terminator)
                    if idx != -1 and (first_sentence_end == -1 or idx < first_sentence_end):
                        first_sentence_end = idx + 1
                if 0 < first_sentence_end < len(narration) - 4:
                    full_title = narration[:first_sentence_end].strip().rstrip(".!?")
                    rest = narration[first_sentence_end:].strip()[:200]
                else:
                    full_title = narration.strip().rstrip(".!?")
                    rest = ""

                # Always run the title through the natural-break splitter so
                # we never end up with an 80-char title that the renderer
                # has to auto-shrink to fit.  If the title splits, append
                # the split-off remainder to whatever rest was.
                t, b = _split_at_natural_break(full_title)
                if b:
                    act["title"] = t
                    extra = (b + (" " + rest if rest else "")).strip()
                    act["body"] = extra[:200]
                else:
                    act["title"] = t[:200]
                    if rest:
                        act["body"] = rest
                logger.info(
                    "Auto-filled empty show_text_block in scene '%s' from narration",
                    scene.get("scene_id", "?"),
                )

        non_empty = [
            a for a in actions
            if a.get("type") and (
                a.get("title") or a.get("body") or a.get("text") or a.get("items")
                or a.get("type") in {
                    "flash_cut", "zoom_punch", "glitch_transition",
                    "scene_transition", "pulse_element", "shake_element",
                }
            )
        ]
        if not non_empty and narration:
            actions.append({
                "type": "show_text_block",
                "title": "",
                "body": narration[:200],
                "position": "center",
            })
            scene["actions"] = actions
            logger.info(
                "Injected default show_text_block in empty scene '%s' (narration fallback)",
                scene.get("scene_id", "?"),
            )

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
        long_title = (
            getattr(long_form_script, "video_title", "")
            or getattr(long_form_script, "topic", "")
            or topic
        )
        long_excerpt = (
            f"Long-form title: {long_title}\n"
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
                cached = _enrich_empty_actions(cached)
                cached = _split_long_titles(cached)
                cached = _inject_pattern_interrupts(cached)
                cached = _inject_ai_illustrations(cached, topic)
                cached = _inject_lottie_icons(cached)
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
            raw_dict = _enrich_empty_actions(raw_dict)
            raw_dict = _split_long_titles(raw_dict)
            raw_dict = _inject_pattern_interrupts(raw_dict)
            raw_dict = _inject_ai_illustrations(raw_dict, topic)
            raw_dict = _inject_lottie_icons(raw_dict)
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

    headline = (
        getattr(enriched, "video_title", "")
        or getattr(enriched, "topic", "")
        or topic
    )
    logger.info(
        "Generated shorts script: %d scenes for '%s'",
        len(enriched.scenes), headline,
    )
    return enriched
