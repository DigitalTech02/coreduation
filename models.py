"""Pydantic models for the AI video generation pipeline.

Defines the shared data contracts used across all pipeline stages:
LLM output -> TTS -> Animation -> Stitching.
"""

from enum import Enum

from pydantic import BaseModel


class SceneType(str, Enum):
    concept = "concept"
    code = "code"
    visualization = "visualization"


class TTSProvider(str, Enum):
    openai = "openai"
    elevenlabs = "elevenlabs"


class LLMScene(BaseModel):
    """Strict scene schema returned by the LLM (all fields required, no defaults).

    Used as the OpenAI structured output response_format.
    """

    scene_id: str
    title: str
    type: SceneType
    narration: str
    visual_description: str
    manim_code: str
    estimated_duration: float


class LLMVideoScript(BaseModel):
    """Strict video script schema returned by the LLM.

    Used directly as response_format for OpenAI structured output.
    All fields required — no defaults allowed.
    """

    topic: str
    scenes: list[LLMScene]


class Scene(BaseModel):
    """Full scene model used internally after TTS and rendering enrichment."""

    scene_id: str
    title: str
    type: SceneType
    narration: str
    visual_description: str
    manim_code: str
    estimated_duration: float
    audio_path: str | None = None
    audio_duration: float | None = None
    video_path: str | None = None


class VideoScript(BaseModel):
    """Full video script model used throughout the pipeline."""

    topic: str
    scenes: list[Scene]

    @classmethod
    def from_llm_output(cls, llm_script: LLMVideoScript) -> "VideoScript":
        """Convert strict LLM output into the richer internal model."""
        return cls(
            topic=llm_script.topic,
            scenes=[Scene(**s.model_dump()) for s in llm_script.scenes],
        )
