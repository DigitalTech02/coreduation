"""Shared visual constants for the rendering engine.

All renderers import from here so the entire video has a consistent look.
"""

from __future__ import annotations

from manim import (
    BLUE,
    BLUE_B,
    BLUE_D,
    DARK_BLUE,
    GREEN,
    GREEN_B,
    GREY,
    GREY_A,
    GREY_B,
    GREY_D,
    ORANGE,
    RED,
    RED_B,
    RIGHT,
    TEAL,
    WHITE,
    YELLOW,
    YELLOW_B,
    ManimColor,
    RoundedRectangle,
    VGroup,
)

# ---------------------------------------------------------------------------
# Background
# ---------------------------------------------------------------------------
BG_COLOR = "#0f1117"

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
PRIMARY = BLUE_B
SECONDARY = TEAL
ACCENT = YELLOW_B
POSITIVE = GREEN_B
NEGATIVE = RED_B
MUTED = GREY_B
HIGHLIGHT = YELLOW

# Named-color lookup used when the LLM specifies a color string.
COLOR_MAP: dict[str, ManimColor] = {
    "blue": BLUE_B,
    "green": GREEN_B,
    "red": RED_B,
    "yellow": YELLOW_B,
    "orange": ORANGE,
    "teal": TEAL,
    "cyan": BLUE,
    "grey": GREY_B,
    "gray": GREY_B,
    "white": WHITE,
    "dark_blue": DARK_BLUE,
    "": PRIMARY,
}


def resolve_color(name: str) -> ManimColor:
    """Map an LLM-provided color name to a ManimColor."""
    return COLOR_MAP.get(name.lower().strip(), PRIMARY)


# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------
FONT_MONO = "Monospace"
FONT_SANS = "Sans"

TITLE_FONT_SIZE = 40
SUBTITLE_FONT_SIZE = 32
BODY_FONT_SIZE = 26
SMALL_FONT_SIZE = 22
CODE_FONT_SIZE = 22
LABEL_FONT_SIZE = 20
SUBLABEL_FONT_SIZE = 16

# ---------------------------------------------------------------------------
# Node dimensions & spacing
# ---------------------------------------------------------------------------
NODE_WIDTH = 1.7
NODE_HEIGHT = 1.0
NODE_CORNER_RADIUS = 0.15
NODE_STROKE_WIDTH = 2.5
NODE_BUFF = 0.6

ICON_SCALE = 0.55

# ---------------------------------------------------------------------------
# Packet animation
# ---------------------------------------------------------------------------
PACKET_WIDTH = 1.2
PACKET_MAX_WIDTH = 3.0  # Auto-grow cap when label is long; text scales down past this
PACKET_HEIGHT = 0.45
PACKET_SPEED_BASE = 2.0  # Manim units per second

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------
CONNECTION_STROKE_WIDTH = 2.5
CONNECTION_TIP_SCALE = 0.2

# ---------------------------------------------------------------------------
# Layer stack / header
# ---------------------------------------------------------------------------
LAYER_HEIGHT = 0.7
LAYER_WIDTH = 4.0
HEADER_FIELD_HEIGHT = 0.6

# ---------------------------------------------------------------------------
# Table
# ---------------------------------------------------------------------------
TABLE_CELL_BUFF = 0.3
TABLE_HEADER_COLOR = BLUE_D
TABLE_ROW_ALT_COLOR = GREY_D
TABLE_HIGHLIGHT_COLOR = YELLOW

# ---------------------------------------------------------------------------
# Cloud architecture
# ---------------------------------------------------------------------------
REGION_STROKE_WIDTH = 2.0
REGION_CORNER_RADIUS = 0.25
REGION_PADDING = 0.8

# ---------------------------------------------------------------------------
# Sequence diagram
# ---------------------------------------------------------------------------
SEQ_PARTICIPANT_GAP = 3.0
SEQ_MESSAGE_GAP = 0.8
SEQ_LIFELINE_COLOR = GREY_A

# ---------------------------------------------------------------------------
# Timing defaults (seconds)
# ---------------------------------------------------------------------------
FADE_DURATION = 0.5
WRITE_DURATION = 0.8
PACKET_TRAVEL_DURATION = 1.5
SHORT_PAUSE = 0.3
MEDIUM_PAUSE = 0.6
LONG_PAUSE = 1.0
BULLET_ITEM_PAUSE = 0.45  # seconds between progressive bullet reveals

# Full-video semantic pipeline (title + scene boundaries)
TITLE_CARD_SECONDS = 2.5
TITLE_FADE_IN = 0.45
TITLE_FADE_OUT = 0.4
SCENE_FADE_OUT_SECONDS = 0.30
SCENE_GAP_SECONDS = 0.15

# Progress UI
PROGRESS_BAR_HEIGHT = 0.06
PROGRESS_BAR_WIDTH = 3.0
PROGRESS_LABEL_FONT_SIZE = 16
PROGRESS_Y_OFFSET = -3.55
PROGRESS_COLOR = BLUE_B
PROGRESS_BG_COLOR = GREY_D

# Subtitle
SUBTITLE_FONT_SIZE_DISPLAY = 28
SUBTITLE_BG_OPACITY = 0.65
SUBTITLE_Y_OFFSET = -2.85
SUBTITLE_MAX_WIDTH = 11.0

# Callout
CALLOUT_FONT_SIZE = 18
CALLOUT_LINE_COLOR = YELLOW_B
CALLOUT_BG_OPACITY = 0.75

# Emphasis text
EMPHASIS_FONT_SIZE = 38

# Category accent colors
CATEGORY_ACCENT: dict[str, ManimColor] = {
    "networking": BLUE,
    "data-structures": "#b388ff",
    "programming": GREEN_B,
    "cloud-architecture": "#4fc3f7",
    "system-design": ORANGE,
    "databases": YELLOW_B,
    "security": RED_B,
    "business-analysis": TEAL,
}

# ---------------------------------------------------------------------------
# Icon shapes — simple geometric representations for node types
# These return (shape_constructor_name, default_color) pairs.
# ---------------------------------------------------------------------------
ICON_THEME: dict[str, tuple[str, ManimColor]] = {
    "computer": ("rectangle", BLUE_B),
    "server": ("rectangle", GREEN),
    "router": ("circle", ORANGE),
    "switch": ("diamond", TEAL),
    "firewall": ("rectangle", RED),
    "cloud": ("ellipse", GREY_A),
    "phone": ("rectangle", BLUE),
    "database": ("cylinder", GREEN_B),
    "load_balancer": ("diamond", TEAL),
    "generic": ("rectangle", GREY_B),
}


# ---------------------------------------------------------------------------
# Visual effect constants
# ---------------------------------------------------------------------------

SHADOW_COLOR = "#000000"
SHADOW_OPACITY = 0.12
SHADOW_OFFSET = (0.07, -0.07)

GLOW_SCALE = 1.35
GLOW_OPACITY = 0.14

SHEEN_FACTOR = 0.15
SHEEN_DIRECTION = RIGHT


# ---------------------------------------------------------------------------
# Visual effect helpers
# ---------------------------------------------------------------------------

def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    h = hex_str.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{max(0,min(255,r)):02x}{max(0,min(255,g)):02x}{max(0,min(255,b)):02x}"


def _color_to_hex(color) -> str:
    """Convert a ManimColor or hex string to a normalised ``#RRGGBB`` string."""
    if isinstance(color, str):
        hex_str = color
    elif hasattr(color, "to_hex"):
        hex_str = color.to_hex()
    else:
        hex_str = str(color)
    if not hex_str.startswith("#"):
        hex_str = f"#{hex_str}"
    return hex_str


def darken_color(color, factor: float = 0.35) -> str:
    """Return a darker hex shade of *color* (ManimColor or hex string)."""
    hex_str = _color_to_hex(color)
    r, g, b = _hex_to_rgb(hex_str)
    return _rgb_to_hex(int(r * (1 - factor)), int(g * (1 - factor)), int(b * (1 - factor)))


def lighten_color(color, factor: float = 0.3) -> str:
    """Return a lighter hex shade of *color*."""
    hex_str = _color_to_hex(color)
    r, g, b = _hex_to_rgb(hex_str)
    return _rgb_to_hex(
        int(r + (255 - r) * factor),
        int(g + (255 - g) * factor),
        int(b + (255 - b) * factor),
    )


def make_shadow(mobject, opacity: float = SHADOW_OPACITY) -> VGroup:
    """Create a dark, offset copy behind *mobject* to simulate a drop shadow.

    Returns a VGroup(shadow, original) so the shadow renders behind.
    """
    shadow = mobject.copy()
    shadow.set_color(SHADOW_COLOR)
    shadow.set_fill(SHADOW_COLOR, opacity=opacity)
    shadow.set_stroke(width=0)
    shadow.shift(SHADOW_OFFSET[0] * RIGHT + SHADOW_OFFSET[1] * RIGHT.rotate(90))
    return VGroup(shadow, mobject)


def make_glow(mobject, color=None, scale: float = GLOW_SCALE, opacity: float = GLOW_OPACITY):
    """Create a larger, semi-transparent copy behind *mobject* as a glow halo.

    Returns a VGroup(glow, original).
    """
    glow = mobject.copy()
    glow.scale(scale)
    glow.move_to(mobject.get_center())
    if color:
        glow.set_color(color)
    glow.set_fill(opacity=opacity)
    glow.set_stroke(width=0)
    return VGroup(glow, mobject)


def make_isometric_shadow(mobject, depth: float = 0.18, layers: int = 3,
                           opacity: float = 0.22) -> VGroup:
    """Stack *layers* dark offset copies behind *mobject* for a 3D-card look.

    Each successive copy shifts further down-right (south-east), producing
    the classic stacked-card / extruded-block illusion without needing a
    real ThreeDScene.  Returns ``VGroup(*shadows, original)`` so the
    shadows render behind the original.
    """
    try:
        from config import ENABLE_ISOMETRIC_SHADOW
    except Exception:
        ENABLE_ISOMETRIC_SHADOW = True
    if not ENABLE_ISOMETRIC_SHADOW:
        return VGroup(mobject)

    shadows = []
    for i in range(1, max(1, layers) + 1):
        s = mobject.copy()
        s.set_color(SHADOW_COLOR)
        s.set_fill(SHADOW_COLOR, opacity=opacity * (1.0 - (i - 1) * 0.25))
        s.set_stroke(width=0)
        s.shift([depth * i, -depth * i, 0])
        shadows.append(s)
    return VGroup(*shadows, mobject)


# ---------------------------------------------------------------------------
# Safe area — usable rendering area excluding topic header & subtitle zones
# ---------------------------------------------------------------------------
SAFE_AREA_TOP = 2.9       # Below topic header (~3.5)
SAFE_AREA_BOTTOM = -2.5   # Above subtitle area (~-2.85)
SAFE_AREA_LEFT = -6.5
SAFE_AREA_RIGHT = 6.5

# Diagram zone — constrains persistent objects (nodes, regions) to the
# middle 70% of the safe area, reserving top/bottom 15% for titles/text.
DIAGRAM_ZONE_TOP = 2.1
DIAGRAM_ZONE_BOTTOM = -1.7


# ---------------------------------------------------------------------------
# Layout zones — explicit Y-band partitioning of the 720p canvas
#
# Manim coordinate space: y in [-4, +4]. Each zone is (y_min, y_max).
# Renderers MUST place their output inside the zone matching their role and
# never bleed across boundaries.
# ---------------------------------------------------------------------------
HEADER_ZONE = (3.3, 3.95)      # Persistent topic header (small, top edge)
TITLE_ZONE = (2.35, 3.2)       # Scene-level title text
CONTENT_ZONE = (-1.7, 2.3)     # Diagrams, tables, code blocks, body text
FOOTER_ZONE = (-3.95, -2.5)    # Subtitles, watermark, progress bar

# Minimum font sizes for YouTube readability at 720p.
# Below MIN_FONT_LABEL is allowed only for tertiary annotations.
MIN_FONT_TITLE = 36
MIN_FONT_BODY = 22
MIN_FONT_LABEL = 18
MIN_FONT_CODE = 20


def is_in_zone(y_min: float, y_max: float, zone: tuple[float, float]) -> bool:
    """Return True iff [y_min, y_max] sits fully inside *zone*."""
    return y_min >= zone[0] and y_max <= zone[1]


def clamp_to_zone(mobject, zone: tuple[float, float], padding: float = 0.05):
    """Shift *mobject* vertically so its bbox sits inside *zone*.

    If the mobject is taller than the zone, anchor its top to the zone top.
    """
    z_lo, z_hi = zone
    bottom = mobject.get_bottom()[1]
    top = mobject.get_top()[1]
    height = top - bottom

    if height > (z_hi - z_lo):
        # Too tall: anchor top to zone top
        delta = (z_hi - padding) - top
    elif top > z_hi - padding:
        delta = (z_hi - padding) - top
    elif bottom < z_lo + padding:
        delta = (z_lo + padding) - bottom
    else:
        return mobject

    from manim import UP
    mobject.shift(delta * UP)
    return mobject


def zones_overlap(a: tuple[float, float], b: tuple[float, float]) -> bool:
    """Return True iff Y-bands *a* and *b* overlap."""
    return not (a[1] <= b[0] or b[1] <= a[0])


def apply_sheen(mobject, factor: float = SHEEN_FACTOR, direction=None):
    """Apply a directional sheen to a VMobject for a glossy look."""
    d = direction if direction is not None else SHEEN_DIRECTION
    try:
        mobject.set_sheen(factor, d)
    except Exception:
        pass
    return mobject
