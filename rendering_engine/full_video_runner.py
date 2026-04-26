"""Manim entrypoint: ``FullSemanticVideo`` — set ``SEMANTIC_DATA_JSON`` to a JSON path.

Run: ``python -m manim render -ql rendering_engine/full_video_runner.py FullSemanticVideo``

Uses ``MovingCameraScene`` when camera motion is enabled so that ``focus_camera``
and ``reset_camera`` actions can zoom/pan.  Falls back to ``Scene`` gracefully.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from manim import MovingCameraScene

from rendering_engine.full_video_scene import run_full_video_construct
from rendering_engine.styles import BG_COLOR
from rendering_engine.themes import apply_themed_background, get_theme

logger = logging.getLogger(__name__)


class FullSemanticVideo(MovingCameraScene):
    def construct(self) -> None:
        path = os.environ.get("SEMANTIC_DATA_JSON")
        if not path or not Path(path).is_file():
            raise RuntimeError("Set SEMANTIC_DATA_JSON to the script JSON file path")
        data = json.loads(Path(path).read_text(encoding="utf-8"))

        category = (data.get("category") or "").strip()
        try:
            from config import ENABLE_THEMED_BACKGROUNDS
        except Exception:
            ENABLE_THEMED_BACKGROUNDS = True

        if ENABLE_THEMED_BACKGROUNDS:
            apply_themed_background(self, category)
        else:
            self.camera.background_color = BG_COLOR

        self.camera.frame.set_width(14.2)

        run_full_video_construct(self, data)
