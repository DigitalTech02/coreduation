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


def _ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _measure_duration(audio_path: str) -> float:
    """Return audio duration in seconds using pydub."""
    audio = AudioSegment.from_file(audio_path)
    return len(audio) / 1000.0


def _generate_openai_tts(text: str, output_path: str) -> None:
    """Generate speech using OpenAI TTS API."""
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY is not set")

    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_TTS_MODEL", "tts-1")
    voice = os.getenv("OPENAI_TTS_VOICE", "alloy")

    logger.info("OpenAI TTS: model=%s, voice=%s, length=%d chars", model, voice, len(text))

    response = client.audio.speech.create(model=model, voice=voice, input=text)
    response.stream_to_file(output_path)


def _generate_elevenlabs_tts(text: str, output_path: str) -> None:
    """Generate speech using ElevenLabs API."""
    from elevenlabs.client import ElevenLabs

    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise EnvironmentError("ELEVENLABS_API_KEY is not set")

    client = ElevenLabs(api_key=api_key)
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
    model_id = os.getenv("ELEVENLABS_MODEL_ID", "eleven_v3")

    logger.info("ElevenLabs TTS: model=%s, voice=%s, length=%d chars", model_id, voice_id, len(text))

    audio = client.text_to_speech.convert(
        text=text,
        voice_id=voice_id,
        model_id=model_id,
        output_format="mp3_44100_128",
    )

    with open(output_path, "wb") as f:
        for chunk in audio:
            if isinstance(chunk, bytes):
                f.write(chunk)


def generate_speech(
    text: str, output_path: str, provider: str | None = None
) -> float:
    """Convert text to speech and save to output_path.

    Returns the measured audio duration in seconds.
    """
    _ensure_output_dir()

    if provider is None:
        provider = os.getenv("TTS_PROVIDER", "openai")

    provider_enum = TTSProvider(provider)

    logger.info("Generating speech with provider: %s -> %s", provider_enum.value, output_path)

    if provider_enum == TTSProvider.openai:
        _generate_openai_tts(text, output_path)
    elif provider_enum == TTSProvider.elevenlabs:
        _generate_elevenlabs_tts(text, output_path)
    else:
        raise ValueError(f"Unknown TTS provider: {provider}")

    duration = _measure_duration(output_path)
    logger.info("Audio generated: %.2fs -> %s", duration, output_path)
    return duration
