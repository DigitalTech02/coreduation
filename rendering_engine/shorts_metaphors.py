"""Visual metaphor primitives for vertical 9:16 shorts.

Each function returns a Manim ``VGroup`` sized for the upper third of a
1080x1920 canvas (roughly 4 units wide, 3 units tall).  Designed to fill
the empty space above the text card so the short never has dead canvas.

Routing: ``pick_shorts_metaphor`` picks one based on scene position +
voice_mood so any topic gets a coherent story-arc visual progression
regardless of whether it's TLS or B-tree indexes.

The metaphors are deliberately built from Manim primitives (Arc, Line,
RoundedRectangle, Triangle, Text) rather than imported assets — keeps the
shorts pipeline reproducible from a fresh clone with no extra files.
"""

from __future__ import annotations

import logging
from typing import Any

from manim import (
    BLUE,
    DOWN,
    GREEN,
    LEFT,
    ORANGE,
    PI,
    RED,
    RIGHT,
    UP,
    WHITE,
    YELLOW,
    Arc,
    Circle,
    FadeIn,
    Indicate,
    Line,
    RoundedRectangle,
    Text,
    Triangle,
    VGroup,
)

from rendering_engine.styles import BG_COLOR, CATEGORY_ACCENT, MUTED, PRIMARY

logger = logging.getLogger(__name__)

# Vertical position of all metaphors — top of the safe content area, well
# above where the text card sits in shorts mode.
_METAPHOR_CENTER_Y = 4.2

# Scale applied to every built metaphor before placing on canvas.  Larger
# values produce more dominant icons.  Tuned so even the simplest icon
# (warning triangle) feels like a hero element, not decoration.
_METAPHOR_SCALE = 1.95

# Color override per metaphor — the icon color tells a STORY independent
# of category accent: danger=yellow, fail=red, secure=green, success=gold.
# Otherwise (e.g.) a security-category render produces a red shield, which
# reads as "broken" instead of "protected".
_METAPHOR_COLOR: dict[str, str] = {
    "warning":      "#ffd23f",   # yellow — danger
    "broken_lock":  "#ff3b30",   # red — failure
    "handshake":    "#3fdca1",   # green — secured
    "shield":       "#3fdca1",   # green — protected
    "swipe_arrow":  "#ffd23f",   # gold — call to action
    "lightbulb":    "#ffd23f",   # yellow — insight
}


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

def _build_warning() -> VGroup:
    """Yellow warning triangle with pulsing exclamation mark.

    Use case: the HOOK — "something is at risk", danger framing.
    """
    triangle = Triangle(color=YELLOW, stroke_width=10)
    triangle.scale(1.4)
    triangle.set_fill(YELLOW, opacity=0.18)

    bang = Text("!", font_size=120, color=YELLOW, weight="BOLD")
    bang.move_to(triangle.get_center() + DOWN * 0.05)

    return VGroup(triangle, bang)


def _build_broken_lock() -> VGroup:
    """Red padlock with cracked / split shackle — 'security failed'.

    Use case: TENSION — what goes wrong without protection.
    """
    body = RoundedRectangle(
        width=1.9, height=1.5, corner_radius=0.20,
        color=RED, stroke_width=8,
        fill_color=RED, fill_opacity=0.30,
    )
    body.shift(DOWN * 0.4)

    # Two cracked halves of the shackle, offset to look broken
    left_half = Arc(
        radius=0.65, angle=PI / 2, start_angle=PI / 2,
        color=RED, stroke_width=8,
    )
    left_half.move_to(body.get_top() + UP * 0.4 + LEFT * 0.18)

    right_half = Arc(
        radius=0.65, angle=PI / 2, start_angle=0,
        color=RED, stroke_width=8,
    )
    right_half.move_to(body.get_top() + UP * 0.4 + RIGHT * 0.18)
    right_half.rotate(0.35)  # tilt the broken half

    # Crack indicator — a small jagged line
    crack = Line(
        body.get_top() + UP * 0.0 + LEFT * 0.05,
        body.get_top() + UP * 0.35 + RIGHT * 0.05,
        color=YELLOW, stroke_width=4,
    )

    # Keyhole on body
    keyhole = Circle(radius=0.10, color=RED, stroke_width=0)
    keyhole.set_fill(RED, opacity=1.0)
    keyhole.move_to(body.get_center() + UP * 0.05)
    keyslot = Line(
        keyhole.get_center(), keyhole.get_center() + DOWN * 0.32,
        color=RED, stroke_width=5,
    )

    return VGroup(left_half, right_half, crack, body, keyhole, keyslot)


def _build_handshake(accent_color=GREEN) -> VGroup:
    """Two circles (browser ↔ server) joined by a line + a lock in the middle.

    Use case: PAYOFF — "they connect, then secure".  Generic enough to fit
    most distributed-system topics, not just TLS.
    """
    left_circle = Circle(radius=0.55, color=BLUE, stroke_width=6)
    left_circle.set_fill(BLUE, opacity=0.4)
    left_circle.shift(LEFT * 1.65)
    left_label = Text("Client", font_size=34, color=WHITE, weight="BOLD")
    left_label.next_to(left_circle, DOWN, buff=0.22)

    right_circle = Circle(radius=0.55, color=ORANGE, stroke_width=6)
    right_circle.set_fill(ORANGE, opacity=0.4)
    right_circle.shift(RIGHT * 1.65)
    right_label = Text("Server", font_size=34, color=WHITE, weight="BOLD")
    right_label.next_to(right_circle, DOWN, buff=0.22)

    line = Line(
        left_circle.get_right(), right_circle.get_left(),
        color=accent_color, stroke_width=5,
    )

    # Mini padlock in the middle of the connection
    lock_body = RoundedRectangle(
        width=0.55, height=0.45, corner_radius=0.07,
        color=accent_color, stroke_width=4,
        fill_color=accent_color, fill_opacity=0.92,
    )
    lock_arc = Arc(radius=0.18, angle=PI, color=accent_color, stroke_width=4)
    lock_arc.next_to(lock_body, UP, buff=-0.02)
    lock = VGroup(lock_arc, lock_body)
    lock.move_to(line.get_center() + UP * 0.05)

    return VGroup(left_circle, right_circle, line, lock, left_label, right_label)


def _build_shield_check(accent_color=GREEN) -> VGroup:
    """Heraldic shield outline with a chunky checkmark — 'protected'.

    Built from a Polygon so the silhouette is a real shield (rounded top,
    point at the bottom) instead of a square stuck to a triangle.
    """
    from manim import Polygon

    # Shield silhouette: 8 points forming a rounded-top, pointed-bottom shape.
    pts = [
        [-1.0,  0.95, 0],   # top-left
        [ 1.0,  0.95, 0],   # top-right
        [ 1.0,  0.20, 0],   # right shoulder
        [ 0.90, -0.40, 0],
        [ 0.55, -0.95, 0],
        [ 0.0,  -1.20, 0],  # bottom point
        [-0.55, -0.95, 0],
        [-0.90, -0.40, 0],
        [-1.0,  0.20, 0],   # left shoulder
    ]
    shield = Polygon(*pts, color=accent_color, stroke_width=10)
    shield.set_fill(accent_color, opacity=0.28)

    check = Text("✓", font_size=130, color=accent_color, weight="BOLD")
    check.move_to(shield.get_center() + DOWN * 0.05)

    return VGroup(shield, check)


def _build_swipe_arrow(accent_color=GREEN) -> VGroup:
    """Mini video-thumbnail tile + bouncing up-arrow — 'watch the full video'.

    Use case: CTA scene.  The tile's play-triangle reads as "this is video
    content"; the up-arrow reads as "swipe up / link in description".
    """
    # Thumbnail tile
    tile = RoundedRectangle(
        width=2.6, height=1.7, corner_radius=0.14,
        color=accent_color, stroke_width=5,
        fill_color=BG_COLOR, fill_opacity=0.95,
    )
    play = Triangle(color=accent_color, stroke_width=0)
    play.set_fill(accent_color, opacity=0.98)
    play.scale(0.45)
    play.rotate(-PI / 2)  # point right
    play.move_to(tile.get_center())

    arrow_shaft = Line(
        tile.get_bottom() + DOWN * 0.65, tile.get_bottom() + DOWN * 0.10,
        color=accent_color, stroke_width=12,
    )
    arrow_head = Triangle(color=accent_color, stroke_width=0)
    arrow_head.set_fill(accent_color, opacity=1.0)
    arrow_head.scale(0.22)
    arrow_head.move_to(arrow_shaft.get_end() + UP * 0.05)

    return VGroup(tile, play, arrow_shaft, arrow_head)


def _build_lightbulb_idea(accent_color=YELLOW) -> VGroup:
    """Lightbulb with rays — 'aha moment / insight'.

    Use case: payoff/insight scenes for non-security topics
    (programming, data structures, etc).
    """
    bulb = Circle(radius=0.55, color=accent_color, stroke_width=6)
    bulb.set_fill(accent_color, opacity=0.30)

    base = RoundedRectangle(
        width=0.55, height=0.30, corner_radius=0.06,
        color=accent_color, stroke_width=5,
        fill_color=accent_color, fill_opacity=0.55,
    )
    base.next_to(bulb, DOWN, buff=-0.02)

    # Light rays
    rays = VGroup()
    import math
    for angle_deg in (10, 50, 90, 130, 170, 200, 250, 290, 330):
        a = math.radians(angle_deg)
        if 200 < angle_deg < 340:
            continue  # skip the bottom rays (where the base is)
        start = bulb.get_center() + 0.75 * RIGHT * math.cos(a) + 0.75 * UP * math.sin(a)
        end = bulb.get_center() + 1.05 * RIGHT * math.cos(a) + 1.05 * UP * math.sin(a)
        ray = Line(start, end, color=accent_color, stroke_width=4)
        rays.add(ray)

    return VGroup(rays, bulb, base)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_BUILDERS = {
    "warning": _build_warning,
    "broken_lock": _build_broken_lock,
    "handshake": _build_handshake,
    "shield": _build_shield_check,
    "swipe_arrow": _build_swipe_arrow,
    "lightbulb": _build_lightbulb_idea,
}


def pick_shorts_metaphor(
    scene_index: int,
    total_scenes: int,
    voice_mood: str = "",
    category: str = "",
) -> str | None:
    """Heuristic: pick a metaphor name by scene position + mood + category.

    Story arc:
      * Scene 0 (HOOK) → warning  ("there's danger / a problem")
      * TENSION / dramatic / urgent → broken_lock  ("here's what fails")
      * PAYOFF / narrator / analytical → handshake (security topics) or
                                          shield (defensive) or
                                          lightbulb (non-security)
      * Last scene (CTA, regardless of mood) → swipe_arrow
    """
    mood = (voice_mood or "").lower()
    cat = (category or "").lower()

    # Last scene is always the CTA arrow
    if scene_index == total_scenes - 1:
        return "swipe_arrow"

    # First scene: warning sets the stakes
    if scene_index == 0:
        return "warning"

    # Tension scenes
    if mood in ("dramatic", "urgent"):
        return "broken_lock"

    # Payoff scenes — pick by category
    if mood in ("narrator", "analytical", "calm", "excited"):
        if cat in ("security", "networking", "system-design"):
            # Second-to-last in security: handshake; else shield
            if scene_index == total_scenes - 2:
                return "handshake"
            return "shield"
        return "lightbulb"

    # Default: shield
    return "shield"


def render_shorts_metaphor(
    scene: Any,
    state: Any,
    metaphor_name: str,
    category: str = "",
) -> Any | None:
    """Build the named metaphor, position it, fade it in, return the mobject.

    Returns None if the name is unknown.  Caller should clear the metaphor
    via ``_clear_scene`` (it's tagged ``"presentation"`` so it's auto-cleared
    between scenes).
    """
    builder = _BUILDERS.get(metaphor_name)
    if builder is None:
        logger.debug("Unknown shorts metaphor: %s", metaphor_name)
        return None

    # Use the metaphor-specific story color (yellow for warning, red for
    # broken, green for protected, gold for CTA) instead of the category
    # accent.  Otherwise a "security" category produces a red shield,
    # which reads as "broken" not "protected".
    color = _METAPHOR_COLOR.get(metaphor_name, CATEGORY_ACCENT.get(category, PRIMARY))

    if metaphor_name in ("handshake", "shield", "swipe_arrow", "lightbulb"):
        try:
            mob = builder(color)
        except TypeError:
            mob = builder()
    else:
        try:
            mob = builder()
        except Exception as e:
            logger.debug("Metaphor builder failed for %s: %s", metaphor_name, e)
            return None

    # Scale up so the metaphor reads as a hero element, not decoration.
    try:
        mob.scale(_METAPHOR_SCALE)
    except Exception:
        pass
    mob.move_to([0, _METAPHOR_CENTER_Y, 0])
    mob.set_z_index(20)

    try:
        scene.play(FadeIn(mob, shift=DOWN * 0.4), run_time=0.45)
    except Exception:
        scene.add(mob)

    # Optional pulse for warning + broken_lock to draw the eye
    if metaphor_name in ("warning", "broken_lock"):
        try:
            scene.play(Indicate(mob, scale_factor=1.12, color=None), run_time=0.45)
        except Exception:
            pass

    # Register with a CUSTOM category (not "presentation") + ``__`` prefix.
    # This is critical: ``state.clear_presentation`` runs before every
    # show_text_block / show_bullet_list and wipes anything tagged
    # "presentation" — which would erase the metaphor the moment the text
    # card renders.  Custom category survives both clear_presentation AND
    # _clear_scene's persistent-keep logic; we manually remove between
    # scenes via clear_shorts_metaphor() called from the per-scene loop.
    key = "__shorts_metaphor"
    state.objects[key] = mob
    state._categories[key] = "shorts_chrome"
    return mob


def clear_shorts_metaphor(scene: Any, state: Any) -> None:
    """Fade-out and remove the current scene's metaphor before the next one."""
    key = "__shorts_metaphor"
    mob = state.objects.get(key)
    if mob is None:
        return
    try:
        from manim import FadeOut
        scene.play(FadeOut(mob, shift=DOWN * 0.2), run_time=0.25)
    except Exception:
        pass
    try:
        scene.remove(mob)
    except Exception:
        pass
    state.objects.pop(key, None)
    state._categories.pop(key, None)
