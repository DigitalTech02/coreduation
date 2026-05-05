"""Scene-level subtitle renderer — phrase-chunked lower-third captions.

Subtitles are generated from the narration text of each scene and displayed
as short phrase chunks during the scene's animation.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from manim import DOWN, FadeIn, FadeOut, RoundedRectangle, Text, VGroup

from rendering_engine.styles import (
    BG_COLOR,
    MUTED,
    SUBTITLE_BG_OPACITY,
    SUBTITLE_FONT_SIZE_DISPLAY,
    SUBTITLE_MAX_WIDTH,
    SUBTITLE_Y_OFFSET,
    WHITE,
)

logger = logging.getLogger(__name__)


_MIN_CHUNK_WORDS = 3


def chunk_narration(text: str, max_words: int = 7) -> list[str]:
    """Split narration into phrase chunks of 3..max_words words each.

    Two-pass: first split on sentence + comma + dash boundaries to get
    natural phrase candidates, then merge any chunk shorter than
    ``_MIN_CHUNK_WORDS`` into the next chunk so we never emit a 1- or
    2-word fragment ("So", "Now", "But wait"). Long phrases get split
    into ``max_words``-word slices.
    """
    text = text.strip()
    if not text:
        return []

    sentences = re.split(r'(?<=[.!?])\s+', text)

    raw_chunks: list[str] = []
    for sentence in sentences:
        parts = re.split(r',\s*|\s*—\s*|\s*–\s*', sentence)
        for part in parts:
            words = part.split()
            if not words:
                continue
            while words:
                chunk_words = words[:max_words]
                words = words[max_words:]
                if chunk_words:
                    raw_chunks.append(" ".join(chunk_words))

    # Merge short chunks into their neighbour so no chunk is < 3 words.
    # Forward-merge first (short chunk + next), then backward-merge any
    # tail fragment into the previous chunk. When the left side already
    # ends in sentence punctuation, separate with a single space; else
    # use ", " to preserve the original phrase break.
    def _join(left: str, right: str) -> str:
        left = left.strip()
        right = right.strip()
        if not left:
            return right
        if not right:
            return left
        if left[-1] in ".!?:;":
            return f"{left} {right}"
        return f"{left}, {right}"

    merged: list[str] = []
    i = 0
    while i < len(raw_chunks):
        cur = raw_chunks[i]
        cur_n = len(cur.split())
        if cur_n < _MIN_CHUNK_WORDS and i + 1 < len(raw_chunks):
            merged.append(_join(cur, raw_chunks[i + 1]))
            i += 2
        else:
            merged.append(cur)
            i += 1

    if len(merged) >= 2 and len(merged[-1].split()) < _MIN_CHUNK_WORDS:
        tail = merged.pop()
        merged[-1] = _join(merged[-1], tail)

    return merged


def play_subtitles_for_scene(
    scene: Any,
    narration: str,
    duration: float,
    max_words: int = 7,
    position_y: float = SUBTITLE_Y_OFFSET,
    audio_path: str | None = None,
) -> None:
    """Display subtitles across the scene duration.

    When ``audio_path`` is provided and ``ENABLE_KINETIC_SUBTITLES`` is on,
    Whisper word-level timestamps drive a karaoke-style word-by-word reveal.
    Otherwise we fall back to evenly-spaced phrase chunks.
    """
    try:
        from config import ENABLE_KINETIC_SUBTITLES
    except Exception:
        ENABLE_KINETIC_SUBTITLES = False

    if ENABLE_KINETIC_SUBTITLES and audio_path:
        try:
            from whisper_align import align_words
            words = align_words(audio_path)
            if words:
                _play_kinetic_subtitles(scene, words, duration, max_words, position_y)
                return
        except Exception as e:
            logger.debug("Kinetic subtitle path failed (%s); falling back to chunks", e)

    _play_chunked_subtitles(scene, narration, duration, max_words, position_y)


# ---------------------------------------------------------------------------
# Whisper-grounded chunk timing
# ---------------------------------------------------------------------------

def _normalise_token(s: str) -> str:
    """Lowercase, strip non-alphanumerics — for fuzzy word comparison."""
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def chunks_from_whisper(
    whisper_words: list[dict], max_words: int = 7,
) -> list[tuple[str, float, float]]:
    """Build subtitle chunks DIRECTLY from whisper-transcribed words.

    Each chunk is (text, audio_start, audio_end) where text is exactly
    what the speaker said (whisper transcript) and start/end are real
    audio timestamps.  This is the gold path: zero matching, zero drift,
    subtitle text guaranteed to match narration audio.

    Chunking strategy:
      - Break on sentence end punctuation (. ! ?) — whisper preserves these
      - Break when a comma falls past min_words_per_chunk
      - Break when current chunk would exceed max_words
    """
    if not whisper_words:
        return []

    min_words = 3
    chunks: list[tuple[str, float, float]] = []

    cur_words: list[str] = []
    cur_start: float | None = None
    cur_end: float | None = None

    def _flush():
        nonlocal cur_words, cur_start, cur_end
        if cur_words and cur_start is not None and cur_end is not None:
            chunks.append((" ".join(cur_words).strip(), cur_start, cur_end))
        cur_words = []
        cur_start = None
        cur_end = None

    for w in whisper_words:
        text = (w.get("text") or "").strip()
        if not text:
            continue
        start = float(w["start"])
        end = float(w["end"])

        if cur_start is None:
            cur_start = start
        cur_words.append(text)
        cur_end = end

        last_char = text[-1] if text else ""
        is_sentence_end = last_char in ".!?"
        is_comma_break = last_char in ",;:" and len(cur_words) >= min_words
        is_at_max = len(cur_words) >= max_words

        if is_sentence_end or is_comma_break or is_at_max:
            _flush()

    _flush()

    # Merge any tiny tail chunk into its predecessor.
    if len(chunks) >= 2 and len(chunks[-1][0].split()) < min_words:
        prev_text, prev_start, _ = chunks[-2]
        tail_text, _, tail_end = chunks[-1]
        joiner = " " if prev_text.endswith((".", "!", "?", ":", ";")) else " "
        chunks[-2] = (f"{prev_text}{joiner}{tail_text}", prev_start, tail_end)
        chunks.pop()

    return chunks


def _resolve_chunk_timings(
    chunks: list[str],
    whisper_words: list[dict],
    fallback_total: float,
) -> list[tuple[float, float]]:
    """Map each subtitle chunk to its real (start, end) in scene-audio time.

    Walks ``whisper_words`` linearly, matching each chunk's token sequence
    against successive whisper tokens.  Handles three real-world wobble cases:

    1. **One-to-many split** — narration says "ClientHello" but whisper
       transcribes "client hello" as two tokens.  We try matching against
       a glued pair (concat of next 2 whisper tokens) when single-token
       match fails.
    2. **Skipped word** — whisper drops a word.  We allow skipping up to
       ``_MAX_SKIP`` whisper tokens looking for the next match.
    3. **Inserted word** — whisper adds a word the narrator didn't say.
       Same skip allowance handles this from the other direction.

    When matching fails for a whole chunk, returns ``None`` for that slot;
    the gap-filler later interpolates between known anchors so the
    timeline is monotonic.
    """
    if not chunks:
        return []
    if not whisper_words:
        return _proportional_timings(chunks, fallback_total)

    _MAX_SKIP = 4  # max consecutive whisper words to skip during matching

    # Pre-tokenise whisper words once.
    w_tokens = [(_normalise_token(w["text"]), float(w["start"]), float(w["end"]))
                for w in whisper_words]

    def _find_match(target: str, start_idx: int, max_skip: int) -> int:
        """Return whisper index where *target* matches (with split handling).

        First tries exact token match in window. Then tries glue-2 match
        (concat of two consecutive whisper tokens) for ClientHello-style
        camel-case words. Returns -1 if neither found.
        """
        end_idx = min(start_idx + max_skip + 1, len(w_tokens))
        for j in range(start_idx, end_idx):
            if w_tokens[j][0] == target:
                return j
        # glue-2: target might be split across two whisper tokens
        for j in range(start_idx, end_idx - 1):
            glued = w_tokens[j][0] + w_tokens[j + 1][0]
            if glued == target:
                return j  # caller will need to advance by 2 — encoded below
        return -1

    cursor = 0
    timings: list[tuple[float, float] | None] = []

    for chunk in chunks:
        chunk_tokens = [_normalise_token(t) for t in chunk.split() if _normalise_token(t)]
        if not chunk_tokens:
            timings.append(None)
            continue

        # Find anchor for chunk start.
        match_start_idx = _find_match(chunk_tokens[0], cursor, _MAX_SKIP)
        if match_start_idx < 0:
            # Try later chunk tokens as anchor — first word might be lost.
            for offset, ct in enumerate(chunk_tokens[1:4], start=1):
                idx = _find_match(ct, cursor, _MAX_SKIP)
                if idx >= 0:
                    match_start_idx = idx
                    break
        if match_start_idx < 0:
            timings.append(None)
            continue

        chunk_first = w_tokens[match_start_idx][1]
        chunk_last_end = w_tokens[match_start_idx][2]
        wi = match_start_idx

        for ct in chunk_tokens:
            # Look ahead up to _MAX_SKIP for a match of ct or a glue-2.
            end_window = min(wi + _MAX_SKIP + 1, len(w_tokens))
            found = -1
            advance = 1
            for k in range(wi, end_window):
                if w_tokens[k][0] == ct:
                    found = k
                    advance = 1
                    break
                if k + 1 < len(w_tokens) and w_tokens[k][0] + w_tokens[k + 1][0] == ct:
                    found = k
                    advance = 2  # consumed two whisper tokens
                    break
            if found >= 0:
                # Use end of the LAST whisper token consumed.
                end_idx = found + advance - 1
                if end_idx < len(w_tokens):
                    chunk_last_end = max(chunk_last_end, w_tokens[end_idx][2])
                wi = found + advance
            # If not found, leave wi alone — next chunk_token may match.

        timings.append((chunk_first, chunk_last_end))
        cursor = wi

    # Fill any None gaps with linear interpolation between known anchors.
    resolved: list[tuple[float, float]] = []
    last_end = 0.0
    for i, t in enumerate(timings):
        if t is not None:
            # Don't allow timeline to go backwards.
            start, end = t
            if start < last_end:
                start = last_end
            if end < start + 0.1:
                end = start + 0.4
            resolved.append((start, end))
            last_end = end
        else:
            # Look ahead for next known anchor; fill gap with even split.
            next_start = fallback_total
            for j in range(i + 1, len(timings)):
                if timings[j] is not None:
                    next_start = timings[j][0]
                    break
            gap_chunks = 1
            for j in range(i + 1, len(timings)):
                if timings[j] is None:
                    gap_chunks += 1
                else:
                    break
            chunk_dur = max(0.4, (next_start - last_end) / max(1, gap_chunks))
            start = last_end
            end = start + chunk_dur
            resolved.append((start, end))
            last_end = end

    return resolved


def _proportional_timings(
    chunks: list[str], total: float,
) -> list[tuple[float, float]]:
    """Word-count proportional time slices (used when whisper unavailable)."""
    word_counts = [max(1, len(c.split())) for c in chunks]
    total_words = sum(word_counts)
    out: list[tuple[float, float]] = []
    cursor = 0.0
    for w in word_counts:
        dur = total * (w / total_words)
        out.append((cursor, cursor + dur))
        cursor += dur
    return out


# ---------------------------------------------------------------------------
# Scheduled subtitles — runs in parallel with actions via updaters
# ---------------------------------------------------------------------------

def schedule_subtitles_for_scene(
    scene: Any,
    narration: str,
    *,
    audio_duration: float,
    max_words: int = 7,
    whisper_words: list[dict] | None = None,
) -> list:
    """Pre-create all subtitle mobjects with time-based visibility updaters.

    Call this at scene start (BEFORE running any actions). Each subtitle
    mobject sits invisibly on the scene with an updater that toggles its
    opacity based on (current_scene_time - scene_start_time). As Manim
    advances time during action playback and the post-action wait, each
    subtitle appears for its time slice.

    Returns the list of subtitle VGroups so the caller can clean them up
    at scene end via :func:`clear_scheduled_subtitles`.

    Time slices are allocated proportional to chunk word count, summing
    to *audio_duration* — the same window the muxed audio plays in. So
    if the muxed audio says "Step 3" at audio-relative t=2.4s, the
    "Step 3" subtitle is on screen at scene-relative t=2.4s too.
    """
    if audio_duration <= 0.1:
        return []

    # Subtitle TEXT always comes from the original narration script —
    # this is what the user wrote, the source of truth.  Whisper's
    # transcription of the TTS audio can mishear technical terms
    # ("ClientHello" → "client hello", or worse hallucinate phrases),
    # so we never use it as subtitle text.
    chunks = chunk_narration(narration, max_words=max_words)
    if not chunks:
        return []

    # Subtitle TIMING comes from whisper word timestamps when available —
    # those are the real moments each word is spoken in the muxed audio.
    # When whisper is unavailable, we fall back to word-count proportional
    # estimates summed to audio_duration.
    if whisper_words:
        slices = _resolve_chunk_timings(chunks, whisper_words, audio_duration)
        logger.info(
            "Subtitle timing: whisper-aligned for %d chunks (audio=%.2fs)",
            len(chunks), audio_duration,
        )
    else:
        slices = _proportional_timings(chunks, audio_duration)
        logger.info(
            "Subtitle timing: proportional fallback for %d chunks (audio=%.2fs)",
            len(chunks), audio_duration,
        )

    # Per-scene anchor — every scene resets to scene.renderer.time at this
    # point.  Within-scene drift cannot accumulate across scene boundaries.
    scene_start = float(scene.renderer.time)
    created: list = []

    # Detect vertical canvas — phone shorts need bigger captions and a
    # narrower max width since the canvas is only ~8 units wide.
    try:
        frame = scene.camera.frame
        is_vertical = frame.height > frame.width
    except Exception:
        is_vertical = False

    sub_font = int(SUBTITLE_FONT_SIZE_DISPLAY * 1.5) if is_vertical else SUBTITLE_FONT_SIZE_DISPLAY
    sub_max_w = 6.5 if is_vertical else SUBTITLE_MAX_WIDTH

    for chunk_text, (start, end) in zip(chunks, slices):
        txt = Text(
            chunk_text,
            font_size=sub_font,
            color=WHITE,
            weight="BOLD",
        )
        if txt.width > sub_max_w:
            txt.set_width(sub_max_w)

        bg = RoundedRectangle(
            width=txt.width + 0.5,
            height=txt.height + 0.25,
            corner_radius=0.1,
            color=BG_COLOR,
            fill_color=BG_COLOR,
            fill_opacity=SUBTITLE_BG_OPACITY,
            stroke_width=0,
        )
        bg.move_to(txt.get_center())

        group = VGroup(bg, txt)
        y = _subtitle_y(scene, 1.0)
        group.move_to([0, y, 0])
        group.set_z_index(60)
        group.set_opacity(0.0)

        # Crossfade window — the subtitle fades in over the first 0.15s of
        # its slice and out over the last 0.15s. Keeps it readable without
        # visible flicker.
        fade_w = 0.15

        def _toggle(mob, dt, _start=start, _end=end,
                    _scene_start=scene_start, _fade=fade_w, _scene=scene):
            elapsed = float(_scene.renderer.time) - _scene_start
            if elapsed < _start - 0.02 or elapsed > _end + 0.02:
                target = 0.0
            elif elapsed < _start + _fade:
                target = max(0.0, min(1.0, (elapsed - _start) / _fade))
            elif elapsed > _end - _fade:
                target = max(0.0, min(1.0, (_end - elapsed) / _fade))
            else:
                target = 1.0
            try:
                for sub in mob.submobjects:
                    sub.set_opacity(target)
                mob.set_opacity(target)
            except Exception:
                pass

        # Re-anchor Y on every frame so it tracks camera moves.
        def _reanchor(mob, dt, _scene=scene):
            try:
                y = _subtitle_y(_scene, 1.0)
                mob.move_to([0, y, mob.get_center()[2]])
            except Exception:
                pass

        group.add_updater(_toggle)
        group.add_updater(_reanchor)
        scene.add(group)
        created.append(group)

    return created


def clear_scheduled_subtitles(scene: Any, subtitles: list) -> None:
    """Remove updaters and detach subtitle mobjects from *scene*."""
    if not subtitles:
        return
    for mob in subtitles:
        try:
            mob.clear_updaters()
        except Exception:
            pass
        try:
            scene.remove(mob)
        except Exception:
            pass


def _subtitle_y(scene: Any, offset_from_bottom: float) -> float:
    """Get the absolute Y position for subtitles, anchored to the camera frame.

    *offset_from_bottom* is the distance UP from the visible frame bottom,
    so a positive value places the subtitle above the bottom edge.

    On vertical (9:16) shorts the bottom of the frame is hidden behind the
    platform UI (TikTok caption row, IG button bar, YouTube Shorts comments).
    Detect a tall canvas and lift the subtitle higher (~3 units up) so it
    sits comfortably in the lower-third instead of the literal bottom edge.
    """
    try:
        frame = scene.camera.frame
        is_vertical = frame.height > frame.width
        if is_vertical:
            offset_from_bottom = max(offset_from_bottom, 3.2)
        return frame.get_bottom()[1] + offset_from_bottom
    except Exception:
        from rendering_engine.styles import SUBTITLE_Y_OFFSET
        return SUBTITLE_Y_OFFSET


_FADE_IN = 0.12
_FADE_OUT = 0.12


def _play_chunked_subtitles(
    scene: Any,
    narration: str,
    duration: float,
    max_words: int,
    position_y: float,
) -> None:
    """Display narration as bottom-aligned subtitle chunks.

    Each chunk gets time proportional to its word count so a 3-word chunk
    doesn't linger as long as a 7-word one. Total dwell time fits inside
    *duration* (the available subtitle window). Fade-in/out cost is
    deducted up front so chunk dwell time is the time the chunk is fully
    on-screen.
    """
    chunks = chunk_narration(narration, max_words=max_words)
    if not chunks:
        return

    word_counts = [max(1, len(c.split())) for c in chunks]
    total_words = sum(word_counts)

    overhead_per_chunk = _FADE_IN + _FADE_OUT
    overhead_total = overhead_per_chunk * len(chunks)
    dwell_budget = max(0.0, duration - overhead_total)

    # Each chunk dwells in proportion to its word count, with a per-chunk
    # floor of 0.4s so tiny chunks are still readable.
    raw_dwell = [
        (dwell_budget * (w / total_words)) for w in word_counts
    ]
    dwell_times = [max(0.4, d) for d in raw_dwell]

    # If the floor pushed us over budget, scale down uniformly so the
    # final chunk still fits inside *duration*.
    used = sum(dwell_times) + overhead_total
    if used > duration > 0:
        scale = duration / used
        dwell_times = [max(0.25, d * scale) for d in dwell_times]

    for chunk_text, dwell in zip(chunks, dwell_times):
        txt = Text(
            chunk_text,
            font_size=SUBTITLE_FONT_SIZE_DISPLAY,
            color=WHITE,
            weight="BOLD",
        )
        if txt.width > SUBTITLE_MAX_WIDTH:
            txt.set_width(SUBTITLE_MAX_WIDTH)

        bg = RoundedRectangle(
            width=txt.width + 0.5,
            height=txt.height + 0.25,
            corner_radius=0.1,
            color=BG_COLOR,
            fill_color=BG_COLOR,
            fill_opacity=SUBTITLE_BG_OPACITY,
            stroke_width=0,
        )
        bg.move_to(txt.get_center())

        subtitle = VGroup(bg, txt)
        y = _subtitle_y(scene, 1.0)
        subtitle.move_to([0, y, 0])
        subtitle.set_z_index(60)  # always above ambient/keyword/decor

        scene.play(FadeIn(subtitle), run_time=_FADE_IN)
        scene.wait(dwell)
        scene.play(FadeOut(subtitle), run_time=_FADE_OUT)


def _play_kinetic_subtitles(
    scene: Any,
    words,  # list[WordTiming]
    duration: float,
    max_words: int,
    position_y: float,
) -> None:
    """Word-by-word karaoke reveal driven by Whisper timings.

    Words are grouped into rolling phrases of up to ``max_words``; each word
    in a phrase highlights briefly when spoken, and the whole phrase fades
    out before the next phrase begins.
    """
    if not words:
        return

    phrases: list[list] = []
    current: list = []
    for w in words:
        current.append(w)
        if len(current) >= max_words or w.text.endswith((".", "!", "?")):
            phrases.append(current)
            current = []
    if current:
        phrases.append(current)

    last_end = 0.0
    for phrase in phrases:
        if not phrase:
            continue
        phrase_text = " ".join(w.text for w in phrase)
        txt = Text(phrase_text, font_size=SUBTITLE_FONT_SIZE_DISPLAY, color=WHITE, weight="BOLD")
        if txt.width > SUBTITLE_MAX_WIDTH:
            txt.set_width(SUBTITLE_MAX_WIDTH)

        bg = RoundedRectangle(
            width=txt.width + 0.5,
            height=txt.height + 0.25,
            corner_radius=0.1,
            color=BG_COLOR,
            fill_color=BG_COLOR,
            fill_opacity=SUBTITLE_BG_OPACITY,
            stroke_width=0,
        )
        bg.move_to(txt.get_center())
        group = VGroup(bg, txt)
        y = _subtitle_y(scene, 1.0)
        group.move_to([0, y, 0])

        wait_to = max(0.0, phrase[0].start - last_end - 0.05)
        if wait_to > 0:
            scene.wait(wait_to)
        scene.play(FadeIn(group), run_time=0.12)

        phrase_dur = max(0.4, phrase[-1].end - phrase[0].start)
        scene.wait(phrase_dur)
        scene.play(FadeOut(group), run_time=0.12)
        last_end = phrase[-1].end
