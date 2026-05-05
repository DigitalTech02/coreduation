"""Manim entrypoint for vertical 9:16 shorts (YouTube Shorts / IG Reels / TikTok).

Mirrors ``full_video_runner.FullSemanticVideo`` but with:

- Tall canvas: ``frame_width=8.0``, ``frame_height=14.222`` (matches 1080x1920
  pixel resolution at the same density Manim uses for 16:9).
- No ambient margin decor: there are no margins on a vertical canvas to fill.
- The construct function reads ``data["mode"] == "shorts"`` and skips the
  intro / title / outro / persistent-header / corner-decorations chrome so
  the 50-second budget goes entirely to content.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

# IMPORTANT: must reshape the Manim global config BEFORE importing Scene
# classes that read it during initialization.  Manim's ``MovingCameraScene``
# pulls ``frame_width`` and ``frame_height`` from config when constructing
# the camera frame, so we set them at module load.
from manim import config as manim_config

manim_config.frame_width = 8.0
manim_config.frame_height = 14.222

from manim import MovingCameraScene  # noqa: E402

from rendering_engine.full_video_scene import run_full_video_construct  # noqa: E402
from rendering_engine.styles import BG_COLOR  # noqa: E402
from rendering_engine.themes import apply_themed_background  # noqa: E402

logger = logging.getLogger(__name__)


class ShortsSemanticVideo(MovingCameraScene):
    """Vertical short scene.  Reuses run_full_video_construct in shorts mode."""

    def construct(self) -> None:
        path = os.environ.get("SEMANTIC_DATA_JSON")
        if not path or not Path(path).is_file():
            raise RuntimeError("Set SEMANTIC_DATA_JSON to the script JSON file path")
        data = json.loads(Path(path).read_text(encoding="utf-8"))

        # Force shorts mode regardless of what the engine wrote — a vertical
        # render with intro/outro chrome would burn ~9s of the 50s budget.
        data["mode"] = "shorts"

        category = (data.get("category") or "").strip()
        try:
            from config import ENABLE_THEMED_BACKGROUNDS
        except Exception:
            ENABLE_THEMED_BACKGROUNDS = True

        if ENABLE_THEMED_BACKGROUNDS:
            apply_themed_background(self, category)
        else:
            self.camera.background_color = BG_COLOR

        # Skip ambient margin decor — no margins on vertical.

        # Tall camera frame.  set_height drives both axes so the frame matches
        # the 9:16 aspect we configured at module load.
        self.camera.frame.set_height(14.222)
        self.camera.frame.move_to([0, 0, 0])

        run_full_video_construct(self, data)
