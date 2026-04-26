"""D3-rendered charts via Playwright headless Chromium.

Public entry point: :func:`render_chart_to_image`.
"""

from .renderer import render_chart_to_image

__all__ = ["render_chart_to_image"]
