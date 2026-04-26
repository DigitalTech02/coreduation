"""Multi-language dubs — translate narration + re-render TTS + remux silent video.

For each requested target language we:
  1. Translate every scene's narration with GPT-4o (fall back to gpt-4o-mini).
  2. Re-render TTS using the existing ``tts_generator.generate_speech`` (multi-
     voice + caching applies automatically).
  3. Stitch a per-language narration track using
     ``semantic_audio.build_semantic_narration_track``.
  4. Mux the original silent video with the new audio → ``final_<lang>.mp4``.

Translations and per-language audio are cached on disk so the only repeat cost
is the final ffmpeg mux step.

Languages are ISO codes ("es", "hi", "fr", …); free-form names also work.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


_LANGUAGE_NAMES = {
    "en": "English",
    "es": "Spanish (Latin American)",
    "hi": "Hindi",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese (Brazilian)",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Mandarin Chinese (Simplified)",
    "ar": "Arabic",
    "ru": "Russian",
    "tr": "Turkish",
    "id": "Indonesian",
    "vi": "Vietnamese",
}


def _translate_scene(text: str, language: str, client) -> str:
    from caching import cache_json, cached_json

    cached = cached_json("translations", language, text)
    if cached and "text" in cached:
        return cached["text"]

    pretty = _LANGUAGE_NAMES.get(language.lower(), language)
    system = (
        f"You translate educational YouTube narration into {pretty}. "
        "Preserve technical terms (acronyms, code identifiers, proper nouns) "
        "in their original form. Keep sentence rhythm so a TTS narrator can "
        "read it naturally. Output ONLY the translation, no commentary."
    )

    try:
        try:
            from config import OPENAI_TRANSLATION_MODEL
            model = OPENAI_TRANSLATION_MODEL
        except Exception:
            model = "gpt-4o"

        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
            temperature=0.2,
        )
        translated = (resp.choices[0].message.content or "").strip()
        if not translated:
            translated = text
    except Exception as e:
        logger.warning("Translation to %s failed: %s — falling back to source text", language, e)
        translated = text

    cache_json("translations", {"text": translated}, language, text)
    return translated


def generate_language_dubs(
    *,
    script,
    silent_video: str,
    run_dir: str | Path,
    languages: Iterable[str],
) -> dict[str, str]:
    """Render ``final_<lang>.mp4`` for each language in *languages*.

    Returns a mapping ``lang -> final_path`` for whichever dubs succeeded.
    """
    from openai import OpenAI

    from config import OPENAI_API_KEY
    from semantic_audio import build_semantic_narration_track, mux_video_with_audio
    from tts_generator import generate_speech

    if not OPENAI_API_KEY:
        logger.warning("Dub generation skipped: OPENAI_API_KEY not configured")
        return {}

    run_dir = Path(run_dir)
    client = OpenAI(api_key=OPENAI_API_KEY)
    results: dict[str, str] = {}

    for raw_lang in languages:
        lang = raw_lang.strip().lower()
        if not lang or lang == "en":
            continue
        pretty = _LANGUAGE_NAMES.get(lang, lang)
        logger.info("--- Dubbing into %s (%s) ---", pretty, lang)

        audio_dir = run_dir / f"audio_{lang}"
        audio_dir.mkdir(parents=True, exist_ok=True)

        scene_audio_paths: list[str] = []
        scene_moods: list[str] = []
        scene_action_dumps: list[list[dict]] = []

        for scene in script.scenes:
            translated = _translate_scene(scene.narration, lang, client)
            audio_path = str(audio_dir / f"{scene.scene_id}.mp3")
            mood = getattr(scene, "voice_mood", "") or None
            try:
                generate_speech(translated, audio_path, mood=mood)
            except Exception as e:
                logger.error("TTS for scene %s (%s) failed: %s", scene.scene_id, lang, e)
                continue
            scene_audio_paths.append(audio_path)
            scene_moods.append(mood or "")
            scene_action_dumps.append(
                [a.model_dump(by_alias=True) if hasattr(a, "model_dump") else dict(a)
                 for a in scene.actions]
            )

        if not scene_audio_paths:
            logger.warning("No scene audio produced for %s; skipping", lang)
            continue

        narration_path = str(run_dir / f"full_narration_{lang}.mp3")
        try:
            build_semantic_narration_track(
                scene_audio_paths=scene_audio_paths,
                output_path=narration_path,
                scene_actions=scene_action_dumps,
                category=getattr(script, "category", "") or "",
                scene_moods=scene_moods,
            )
        except Exception as e:
            logger.error("Narration assembly failed for %s: %s", lang, e)
            continue

        final_out = str(run_dir / f"final_{lang}.mp4")
        try:
            mux_video_with_audio(silent_video, narration_path, final_out)
            results[lang] = final_out
            logger.info("Dub complete: %s -> %s", pretty, final_out)
        except Exception as e:
            logger.error("Muxing failed for %s: %s", lang, e)

    if results:
        logger.info("Generated %d language dub(s): %s", len(results), ", ".join(results.keys()))
    return results
