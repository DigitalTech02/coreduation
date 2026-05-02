"""Text-to-speech generation with dual-provider support (OpenAI TTS + ElevenLabs)."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from pydub import AudioSegment

from models import TTSProvider

load_dotenv()

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output/audio")

_PACE_TO_SPEED = {"slow": 0.92, "normal": 1.0, "fast": 1.05}


def _ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _measure_duration(audio_path: str) -> float:
    """Return audio duration in seconds using pydub."""
    audio = AudioSegment.from_file(audio_path)
    return len(audio) / 1000.0


def _resolve_voice_settings(
    provider_enum: "TTSProvider",
    voice: str | None = None,
    mood: str | None = None,
) -> tuple[str, str]:
    """Pick (model, voice) for the given provider, optionally overridden
    by a per-scene mood (see :mod:`voice_moods`)."""
    if provider_enum == TTSProvider.openai:
        model = os.getenv("OPENAI_TTS_MODEL", "tts-1")
        chosen = voice or os.getenv("OPENAI_TTS_VOICE", "alloy")
        if mood:
            try:
                from voice_moods import voice_for_mood
                chosen = voice_for_mood("openai", mood, default=chosen)
            except Exception:
                pass
        return model, chosen
    if provider_enum == TTSProvider.elevenlabs:
        model = os.getenv("ELEVENLABS_MODEL_ID", "eleven_v3")
        chosen = voice or os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
        if mood:
            try:
                from voice_moods import voice_for_mood
                chosen = voice_for_mood("elevenlabs", mood, default=chosen)
            except Exception:
                pass
        return model, chosen
    return "", ""


def generate_speech(
    text: str,
    output_path: str,
    provider: str | None = None,
    mood: str | None = None,
    voice: str | None = None,
    speed: float = 1.0,
) -> float:
    """Convert text to speech and save to output_path.

    Returns the measured audio duration in seconds.

    *mood* (optional) selects a voice variant per-scene (e.g. ``"excited"``,
    ``"dramatic"``, ``"narrator"``); see :mod:`voice_moods`.
    *voice* explicitly overrides the resolved voice.

    Caches the audio bytes by ``(text, voice, model)`` so repeated runs are
    instant.
    """
    _ensure_output_dir()

    if provider is None:
        provider = os.getenv("TTS_PROVIDER", "openai")

    provider_enum = TTSProvider(provider)
    model, resolved_voice = _resolve_voice_settings(provider_enum, voice=voice, mood=mood)

    try:
        from caching import cache_tts_result, cached_tts
        cached = cached_tts(text, resolved_voice, model, output_path)
        if cached is not None:
            return cached
    except Exception as e:
        logger.debug("TTS cache lookup failed (continuing): %s", e)

    logger.info(
        "Generating speech with provider: %s (voice=%s, model=%s, mood=%s) -> %s",
        provider_enum.value, resolved_voice, model, mood or "default", output_path,
    )

    if provider_enum == TTSProvider.openai:
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY is not set")
        client = OpenAI(api_key=api_key)
        response = client.audio.speech.create(model=model, voice=resolved_voice, input=text, speed=speed)
        response.stream_to_file(output_path)
    elif provider_enum == TTSProvider.elevenlabs:
        from elevenlabs.client import ElevenLabs
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            raise EnvironmentError("ELEVENLABS_API_KEY is not set")
        client = ElevenLabs(api_key=api_key)
        audio = client.text_to_speech.convert(
            text=text,
            voice_id=resolved_voice,
            model_id=model,
            output_format="mp3_44100_128",
        )
        with open(output_path, "wb") as f:
            for chunk in audio:
                if isinstance(chunk, bytes):
                    f.write(chunk)
    else:
        raise ValueError(f"Unknown TTS provider: {provider}")

    duration = _measure_duration(output_path)
    logger.info("Audio generated: %.2fs -> %s", duration, output_path)

    try:
        from caching import cache_tts_result
        cache_tts_result(text, resolved_voice, model, output_path, duration)
    except Exception as e:
        logger.debug("TTS cache store failed: %s", e)

    return duration
