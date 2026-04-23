"""Manim entrypoint: ``FullSemanticVideo`` — set ``SEMANTIC_DATA_JSON`` to a JSON path.

Run: ``python -m manim render -ql rendering_engine/full_video_runner.py FullSemanticVideo``
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from manim import Scene

from rendering_engine.full_video_scene import run_full_video_construct
from rendering_engine.styles import BG_COLOR


class FullSemanticVideo(Scene):
    def construct(self) -> None:
        self.camera.background_color = BG_COLOR
        path = os.environ.get("SEMANTIC_DATA_JSON")
        if not path or not Path(path).is_file():
            raise RuntimeError("Set SEMANTIC_DATA_JSON to the script JSON file path")
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        run_full_video_construct(self, data)
