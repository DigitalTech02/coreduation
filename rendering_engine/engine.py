"""Central rendering engine — stateful scene manager and full-video Manim run."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, NamedTuple

from manim import FadeOut, VGroup

from models_semantic import EnrichedScene, EnrichedVideoScript

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Spatial bounding box
# ---------------------------------------------------------------------------

class BBox(NamedTuple):
    """Axis-aligned bounding box: left, right, bottom, top."""

    left: float
    right: float
    bottom: float
    top: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.top - self.bottom

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2

    @property
    def center_y(self) -> float:
        return (self.bottom + self.top) / 2

    def overlaps(self, other: BBox, margin: float = 0.0) -> bool:
        """True if this bbox overlaps *other* (with optional margin)."""
        return not (
            self.right + margin < other.left
            or other.right + margin < self.left
            or self.top + margin < other.bottom
            or other.top + margin < self.bottom
        )

    def contains(self, other: BBox) -> bool:
        return (
            self.left <= other.left
            and self.right >= other.right
            and self.bottom <= other.bottom
            and self.top >= other.top
        )

    def union(self, other: BBox) -> BBox:
        return BBox(
            min(self.left, other.left),
            max(self.right, other.right),
            min(self.bottom, other.bottom),
            max(self.top, other.top),
        )

OUTPUT_DIR = Path("output/video")
MANIM_QUALITY = os.getenv("MANIM_QUALITY", "m")

# Manim's per-quality output directory under media/videos/<runner>/.
# Used by the ffmpeg concat fallback to find partial mp4s when Manim's
# combine_files step crashes (PyAV/Python 3.12 bug).
MANIM_QUALITY_DIR_MAP = {
    "l": "480p15",
    "m": "720p30",
    "h": "1080p60",
    "p": "1440p60",
    "k": "2160p60",
}

RUNNER = Path(__file__).resolve().parent / "full_video_runner.py"
RUNNER_CLASS = "FullSemanticVideo"


def _run_manim_with_crash_watch(
    cmd: list[str],
    log_path: Path,
    env: dict,
    timeout: int = 3600,
    poll_interval: float = 2.0,
):
    """Run Manim, monitoring its log for the combine_files crash signature.

    On certain PyAV/Python combos Manim's CLI crashes during the final
    combine step with a FileNotFoundError on partial_movie_file_list.txt,
    *and then fails to actually exit* — it wedges in interpreter shutdown
    waiting on a thread lock that will never release.  ``subprocess.run``
    blocks forever in that state.

    We tail the log here; when we see the crash signature we send SIGKILL
    so the parent can move on to the ffmpeg-concat fallback.

    Returns a CompletedProcess-like namespace with .returncode and
    .killed_by_crash_watch (True iff we sent the kill ourselves).
    """
    import time

    # The combine crash is a FileNotFoundError specifically on
    # partial_movie_file_list.txt.  Earlier we matched only the filename,
    # but that string can also appear in ordinary INFO log lines (e.g.
    # progress messages about partial movie writing) — yielding false-positive
    # SIGKILLs that truncate a perfectly-fine render mid-scene.  Require both
    # the exception name AND the filename, on the same line, near the end of
    # the log, so we only trip on the actual exception.
    crash_re = re.compile(
        r"FileNotFoundError.*partial_movie_file_list\.txt", re.DOTALL,
    )
    # Idle timeout: how long Manim can sit with no log activity after we've
    # already seen the crash before we conclude the process is wedged.
    idle_after_crash = 15.0

    with open(log_path, "w", encoding="utf-8") as logf:
        proc = subprocess.Popen(
            cmd,
            stdout=logf,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=env,
            cwd=str(Path.cwd()),
        )

    start = time.time()
    crash_detected_at: float | None = None
    last_log_size = 0
    last_log_change = time.time()
    killed_by_crash_watch = False

    try:
        while True:
            rc = proc.poll()
            if rc is not None:
                break

            now = time.time()
            if now - start > timeout:
                logger.error("Manim exceeded timeout (%ds); killing.", timeout)
                proc.kill()
                proc.wait()
                break

            try:
                size = log_path.stat().st_size
            except FileNotFoundError:
                size = 0
            if size != last_log_size:
                last_log_size = size
                last_log_change = now

            if crash_detected_at is None:
                # Cheap pre-check before reading the file.
                if size > 0 and (now - last_log_change) < poll_interval * 3:
                    try:
                        # Read only the last 16 KB so an INFO message that
                        # mentions the path but isn't the actual crash can't
                        # poison the watcher for the rest of the run.
                        with open(log_path, "rb") as f:
                            f.seek(0, 2)
                            tail_pos = max(0, f.tell() - 16 * 1024)
                            f.seek(tail_pos)
                            tail_bytes = f.read()
                        text = tail_bytes.decode("utf-8", errors="replace")
                        if crash_re.search(text):
                            crash_detected_at = now
                            logger.warning(
                                "Detected Manim combine crash in %s; will kill if "
                                "subprocess does not exit within %.0fs.",
                                log_path, idle_after_crash,
                            )
                    except Exception:
                        pass
            else:
                # Crash signature seen — give Manim a brief grace period to
                # exit on its own, then kill if it's still alive.
                if (
                    now - crash_detected_at >= idle_after_crash
                    or now - last_log_change >= idle_after_crash
                ):
                    logger.warning(
                        "Manim is wedged in shutdown after combine crash; "
                        "sending SIGKILL so the engine can fall back to "
                        "ffmpeg concat.",
                    )
                    proc.kill()
                    proc.wait(timeout=10)
                    killed_by_crash_watch = True
                    break

            time.sleep(poll_interval)
    except KeyboardInterrupt:
        proc.kill()
        proc.wait()
        raise

    class _Result:
        pass

    result = _Result()
    result.returncode = proc.returncode
    result.killed_by_crash_watch = killed_by_crash_watch
    return result


def _verify_concat_matches_manifest(video: Path, manifest_path: Path) -> None:
    """Reconcile the concat'd silent video with the timing manifest.

    Manim advances ``scene.renderer.time`` by REQUESTED ``run_time``/``wait``
    arguments, but actually-rendered frames get quantized to FPS boundaries —
    a ``run_time=0.45s`` call at 30 fps becomes 13 frames = 0.433s.  Across
    ~230 ``play()``/``wait()`` calls that ~0.02s per-call rounding loss adds
    up to 4–5 seconds.  ``renderer.time`` (and thus our manifest) reports
    235.13s but the actual silent mp4 is 230.47s.

    Re-encoding doesn't help — frames that were never written can't be
    recovered.  Instead, STRETCH the silent video's timestamps so its
    duration equals ``manifest.total_video_duration``.  Same frame count,
    each frame held very slightly longer on the playback clock — viewer
    sees ~2% time dilation, totally imperceptible.  Audio mux can then place
    every per-scene narration at its ORIGINAL ``video_start_seconds`` and
    every cue lands on the correct frame.  No more rescale / no more
    accumulating drift.
    """
    if not manifest_path.is_file():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_total = float(manifest.get("total_video_duration", 0.0))
    except Exception as e:
        logger.debug("Could not read manifest for verification: %s", e)
        return
    if manifest_total <= 0:
        return
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error",
             "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1",
             str(video)],
            capture_output=True, text=True, timeout=20,
        )
        actual = float(result.stdout.strip())
    except Exception as e:
        logger.debug("Could not probe concat'd video: %s", e)
        return

    delta = abs(manifest_total - actual)
    if delta <= 0.2:
        logger.info(
            "Concat duration matches manifest within %.2fs (manifest=%.2fs, "
            "video=%.2fs)",
            delta, manifest_total, actual,
        )
        return

    if actual >= manifest_total:
        # Video is LONGER than manifest claimed (rare).  Trust the manifest;
        # ffmpeg's -t flag in the next encode would clip it.  For now just
        # warn and let it ride.
        logger.warning(
            "Concat'd video (%.2fs) is LONGER than manifest claimed (%.2fs); "
            "leaving manifest alone — audio mux will pad to manifest length.",
            actual, manifest_total,
        )
        return

    pts_factor = manifest_total / actual
    logger.warning(
        "AV-SYNC TIME-DILATE: concat'd video is %.2fs but manifest claims "
        "%.2fs (delta %.2fs).  Stretching playback timestamps by %.4fx so "
        "the silent video lasts exactly the duration the renderer tracked.  "
        "Same frames, each held ~%.1f%% longer on screen.",
        actual, manifest_total, delta, pts_factor, (pts_factor - 1) * 100,
    )

    stretched = video.with_suffix(".stretched.mp4")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video),
        "-vf", f"setpts={pts_factor:.6f}*PTS",
        "-r", "30",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-an",
        str(stretched),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if proc.returncode != 0:
        logger.error(
            "setpts time-dilation failed; leaving silent video at original "
            "duration (audio will drift):\n%s",
            (proc.stderr or "")[-2000:],
        )
        return
    try:
        video.unlink(missing_ok=True)
        stretched.rename(video)
    except Exception as e:
        logger.error("Could not swap stretched video into place: %s", e)
        return

    # Confirm.
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error",
             "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1",
             str(video)],
            capture_output=True, text=True, timeout=20,
        )
        new_actual = float(result.stdout.strip())
        logger.info(
            "Time-dilate complete: video is now %.2fs (manifest %.2fs, delta %.2fs)",
            new_actual, manifest_total, abs(manifest_total - new_actual),
        )
    except Exception:
        pass


def _mp4_is_valid(path: Path) -> bool:
    """Return True iff ffprobe can parse the file's container.

    Manim's broken combine_files step leaves a half-written
    FullSemanticVideo.mp4 (no moov atom) on disk before crashing.  Without
    this check the engine would happily pick that corpse up as the final
    rendered output and the audio-mux step would die with
    ``moov atom not found``.
    """
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-i", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
        )
        return result.returncode == 0
    except Exception:
        return False


def _ffmpeg_concat(partials: list[Path], output: Path) -> bool:
    """Concatenate Manim's per-animation mp4s into one file via ffmpeg.

    Returns True on success, False on failure.  Used as a fallback when
    Manim's own ``combine_files`` step crashes on certain PyAV/Python
    combinations after every animation has rendered successfully.

    We RE-ENCODE the video stream rather than using ``-c copy``.  Empirically,
    ``-c copy`` across many Manim partials silently shaves a frame or two at
    every concat boundary — across 232 partials that's ~4.8s of missing time
    per long-form render.  The loss is non-uniform (accumulates with each
    boundary crossed) so midway through the video, audio drifts ahead of
    visuals by 1–2 seconds and entire subtitle sentences can land on the
    wrong scene.  Re-encoding with libx264 fixes timestamps at every join,
    matching what Manim's own combine_files would have produced.  Costs
    ~30–60s extra wall time on a 4-minute video.  Worth it.
    """
    if not partials:
        return False
    list_fd, list_path = tempfile.mkstemp(suffix=".txt", prefix="concat_")
    try:
        with os.fdopen(list_fd, "w", encoding="utf-8") as listf:
            for p in partials:
                safe = str(p).replace("'", "'\\''")
                listf.write(f"file '{safe}'\n")
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_path,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if result.returncode != 0:
            logger.error("ffmpeg concat (re-encode) failed:\n%s", result.stderr[-4000:])
            return False
        logger.info("ffmpeg concat (re-encode) wrote %s (%d bytes)",
                    output, output.stat().st_size if output.exists() else 0)
        return output.exists()
    finally:
        Path(list_path).unlink(missing_ok=True)

# Actions that produce full-screen "slide" content — only one should be
# visible at a time.  Before rendering a new presentation action the engine
# auto-clears any previous presentation mobjects.
_PRESENTATION_TYPES = frozenset({
    "show_text_block",
    "show_bullet_list",
    "show_code_block",
    "show_comparison",
    "show_table",
    "show_layer_stack",
    "show_header_breakdown",
    "show_math",
    "show_sequence_diagram",
    "show_image",
    "show_lottie",
    "show_chart",
})

# Overlay actions that should be categorised as "presentation" (cleaned up
# at scene end or when the next _PRESENTATION_TYPE fires) but should NOT
# themselves trigger clear_presentation — they're overlays on existing content.
_SOFT_PRESENTATION_TYPES = frozenset({
    "emphasize_text",
})


class SceneState:
    """Tracks mobjects for cross-action use within a segment.

    Objects are tagged with a *category*:
    - ``"persistent"`` — spatial / topology items that should stay on-screen
      until explicitly removed or the scene ends (nodes, connections, regions).
    - ``"presentation"`` — full-screen slide content (text blocks, tables,
      bullet lists, diagrams).  Auto-cleared before the next presentation
      action so they don't pile up.

    Includes a **spatial registry** that caches bounding boxes and supports
    overlap queries, vacant-space searches, and parent/child containment.
    """

    def __init__(self) -> None:
        self.objects: dict[str, Any] = {}
        self._categories: dict[str, str] = {}
        self._hidden: set[str] = set()
        # --- Spatial registry ---
        self._bounds: dict[str, BBox] = {}
        self._parents: dict[str, str] = {}        # child_id → parent_id
        self._children: dict[str, list[str]] = {}  # parent_id → [child_ids]
        # --- Render mode: "long" (16:9) or "shorts" (9:16) ---
        # Set by ``run_full_video_construct`` from ``data["mode"]``.  Renderers
        # read it to scale fonts up and re-anchor content for the tall canvas.
        self.mode: str = "long"

    # -- registration ------------------------------------------------------

    def register(self, obj_id: str, mobject, category: str = "persistent",
                 *, parent_id: str | None = None) -> None:
        self.objects[obj_id] = mobject
        self._categories[obj_id] = category
        self._hidden.discard(obj_id)
        # Spatial: cache bbox
        self._bounds[obj_id] = self._compute_bbox(mobject)
        # Containment hierarchy
        if parent_id:
            self._parents[obj_id] = parent_id
            self._children.setdefault(parent_id, []).append(obj_id)

    def get(self, obj_id: str):
        return self.objects.get(obj_id)

    def is_hidden(self, obj_id: str) -> bool:
        return obj_id in self._hidden

    def unregister(self, obj_id: str) -> None:
        self.objects.pop(obj_id, None)
        self._categories.pop(obj_id, None)
        self._hidden.discard(obj_id)
        self._bounds.pop(obj_id, None)
        # Clean parent/child links
        parent = self._parents.pop(obj_id, None)
        if parent and parent in self._children:
            children = self._children[parent]
            if obj_id in children:
                children.remove(obj_id)
        for child_id in self._children.pop(obj_id, []):
            self._parents.pop(child_id, None)

    def clear(self) -> None:
        self.objects.clear()
        self._categories.clear()
        self._hidden.clear()
        self._bounds.clear()
        self._parents.clear()
        self._children.clear()

    # -- spatial helpers ---------------------------------------------------

    @staticmethod
    def _compute_bbox(mobject) -> BBox:
        """Extract an axis-aligned bounding box from a Manim mobject."""
        return BBox(
            left=float(mobject.get_left()[0]),
            right=float(mobject.get_right()[0]),
            bottom=float(mobject.get_bottom()[1]),
            top=float(mobject.get_top()[1]),
        )

    def refresh_bounds(self, obj_id: str) -> None:
        """Re-compute cached bbox after an object moves/resizes."""
        mob = self.objects.get(obj_id)
        if mob is not None:
            self._bounds[obj_id] = self._compute_bbox(mob)

    def refresh_all_bounds(self) -> None:
        """Re-compute all cached bboxes (call after batch moves)."""
        for obj_id, mob in self.objects.items():
            self._bounds[obj_id] = self._compute_bbox(mob)

    def bbox_of(self, obj_id: str) -> BBox | None:
        """Return cached bbox for a single object."""
        return self._bounds.get(obj_id)

    def visible_bounds(self, category: str | None = None,
                       exclude_internal: bool = True) -> list[tuple[str, BBox]]:
        """Return (id, bbox) pairs for all visible (non-hidden) objects."""
        results = []
        for obj_id, bbox in self._bounds.items():
            if obj_id in self._hidden:
                continue
            if exclude_internal and obj_id.startswith("__"):
                continue
            if category and self._categories.get(obj_id) != category:
                continue
            results.append((obj_id, bbox))
        return results

    def overlaps_any(self, bbox: BBox, margin: float = 0.15,
                     exclude: set[str] | None = None) -> list[str]:
        """Return IDs of visible objects whose bbox overlaps the given bbox."""
        exclude = exclude or set()
        return [
            obj_id for obj_id, obj_bbox in self.visible_bounds()
            if obj_id not in exclude and bbox.overlaps(obj_bbox, margin)
        ]

    def objects_in_rect(self, bbox: BBox) -> list[str]:
        """Return IDs of visible objects fully contained within bbox."""
        return [
            obj_id for obj_id, obj_bbox in self.visible_bounds()
            if bbox.contains(obj_bbox)
        ]

    def children_of(self, parent_id: str) -> list[str]:
        """Return child object IDs contained by parent_id."""
        return list(self._children.get(parent_id, []))

    def find_vacant_rect(self, width: float, height: float) -> tuple[float, float] | None:
        """Find a (center_x, center_y) for a rect of given size with no overlap.

        Scans vertical gaps between occupied bands within the safe area.
        Returns None if no space is available.
        """
        from rendering_engine.styles import (
            SAFE_AREA_BOTTOM, SAFE_AREA_LEFT, SAFE_AREA_RIGHT, SAFE_AREA_TOP,
        )

        occupied = [b for _, b in self.visible_bounds()]
        safe = BBox(SAFE_AREA_LEFT, SAFE_AREA_RIGHT, SAFE_AREA_BOTTOM, SAFE_AREA_TOP)

        if not occupied:
            return (safe.center_x, safe.center_y)

        # Merge overlapping vertical bands
        bands = sorted([(b.bottom, b.top) for b in occupied], key=lambda x: x[0])
        merged = [list(bands[0])]
        for bot, top in bands[1:]:
            if bot <= merged[-1][1] + 0.05:
                merged[-1][1] = max(merged[-1][1], top)
            else:
                merged.append([bot, top])

        # Collect vertical gaps within safe area
        candidates: list[tuple[float, float]] = []
        gap_bot = safe.bottom
        for m_bot, m_top in merged:
            if m_bot - gap_bot >= height:
                candidates.append((gap_bot, m_bot))
            gap_bot = m_top
        if safe.top - gap_bot >= height:
            candidates.append((gap_bot, safe.top))

        if not candidates:
            return None

        # Pick largest gap
        candidates.sort(key=lambda g: g[1] - g[0], reverse=True)
        best_bot, best_top = candidates[0]
        cy = (best_bot + best_top) / 2
        cx = safe.center_x

        # Verify no overlap, try horizontal shifts if needed
        for dx in [0, -1.5, 1.5, -3.0, 3.0]:
            test_cx = cx + dx
            if test_cx - width / 2 < safe.left or test_cx + width / 2 > safe.right:
                continue
            test = BBox(test_cx - width / 2, test_cx + width / 2,
                        cy - height / 2, cy + height / 2)
            if not self.overlaps_any(test):
                return (test_cx, cy)

        # Fallback: return center of best gap even with overlap
        return (cx, cy)

    def find_vacant_y(self, height: float = 1.5) -> float:
        """Find the best Y center for an overlay of given height.

        Replacement for the old module-level ``_find_vacant_y()``.
        """
        result = self.find_vacant_rect(width=10.0, height=height)
        if result is not None:
            return result[1]
        from rendering_engine.styles import SAFE_AREA_BOTTOM, SAFE_AREA_TOP
        return (SAFE_AREA_TOP + SAFE_AREA_BOTTOM) / 2

    # -- visibility helpers ------------------------------------------------

    def hide_persistent(self, scene) -> None:
        """Fade persistent objects to invisible (keep in state for later restore)."""
        to_hide = [
            (k, v) for k, v in self.objects.items()
            if self._categories.get(k) == "persistent"
            and k not in self._hidden
            and not k.startswith("__")
        ]
        if not to_hide:
            return
        scene.play(
            *[mob.animate.set_opacity(0) for _, mob in to_hide],
            run_time=0.3,
        )
        for k, _ in to_hide:
            self._hidden.add(k)

    def restore_persistent(self, scene) -> None:
        """Restore hidden persistent objects to full visibility."""
        to_show = [
            (k, self.objects[k]) for k in list(self._hidden)
            if k in self.objects
        ]
        if not to_show:
            return
        scene.play(
            *[mob.animate.set_opacity(1) for _, mob in to_show],
            run_time=0.3,
        )
        self._hidden.clear()

    def find_largest_vacant_region(
        self, min_width: float = 2.0, min_height: float = 1.0,
    ) -> BBox | None:
        """Return the biggest vacant axis-aligned rectangle in the safe area.

        Tries four candidate regions: above all occupied content, below it,
        and the left/right strips beside it. Returns the BBox with the
        largest area that meets the minimum dimensions, or None if no
        region qualifies. Callers then scale their content to fit and
        center it inside.
        """
        from rendering_engine.styles import (
            SAFE_AREA_BOTTOM, SAFE_AREA_LEFT, SAFE_AREA_RIGHT, SAFE_AREA_TOP,
        )

        occupied = [b for _, b in self.visible_bounds()]
        safe = BBox(SAFE_AREA_LEFT, SAFE_AREA_RIGHT, SAFE_AREA_BOTTOM, SAFE_AREA_TOP)
        if not occupied:
            return safe

        # Union extents of all visible content.
        u_left = min(b.left for b in occupied)
        u_right = max(b.right for b in occupied)
        u_bottom = min(b.bottom for b in occupied)
        u_top = max(b.top for b in occupied)

        margin = 0.25
        candidates: list[BBox] = []

        # ABOVE the union
        if safe.top - (u_top + margin) >= min_height:
            candidates.append(BBox(safe.left, safe.right, u_top + margin, safe.top))
        # BELOW the union
        if (u_bottom - margin) - safe.bottom >= min_height:
            candidates.append(BBox(safe.left, safe.right, safe.bottom, u_bottom - margin))
        # LEFT strip (full height, left of union)
        if (u_left - margin) - safe.left >= min_width:
            candidates.append(BBox(safe.left, u_left - margin, safe.bottom, safe.top))
        # RIGHT strip
        if safe.right - (u_right + margin) >= min_width:
            candidates.append(BBox(u_right + margin, safe.right, safe.bottom, safe.top))

        if not candidates:
            return None
        # Largest area wins
        return max(candidates,
                   key=lambda b: (b.right - b.left) * (b.top - b.bottom))

    # -- category helpers --------------------------------------------------

    def clear_presentation(self, scene) -> None:
        """Fade-out and remove all *presentation* mobjects."""
        pres = [(k, v) for k, v in self.objects.items()
                if self._categories.get(k) == "presentation"]
        if not pres:
            return
        scene.play(*[FadeOut(mob) for _, mob in pres], run_time=0.35)
        for k, _ in pres:
            self.unregister(k)

    def has_persistent(self) -> bool:
        return any(
            c == "persistent" and k not in self._hidden
            for k, c in self._categories.items()
        )

    def persistent_bbox(self) -> tuple[float, float, float, float] | None:
        """Return (left_x, right_x, bottom_y, top_y) of visible persistent objects."""
        bboxes = [b for _, b in self.visible_bounds(category="persistent")]
        if not bboxes:
            return None
        result = bboxes[0]
        for b in bboxes[1:]:
            result = result.union(b)
        return result.left, result.right, result.bottom, result.top

    # -- overlap avoidance -------------------------------------------------

    def avoid_overlap(self, new_ids: set[str]) -> None:
        """Shift newly-added presentation content to avoid ALL visible objects.

        Strategy (in order):
        1. Full-size ``find_vacant_rect`` (top / bottom / between bands)
        2. Scale to 70% and retry ``find_vacant_rect``
        3. Try dedicated top reserved zone (above ``DIAGRAM_ZONE_TOP``) with scaling
        4. Try dedicated bottom reserved zone (below ``DIAGRAM_ZONE_BOTTOM``) with scaling
        5. Final fallback: shift below lowest persistent object & scale
        """
        from rendering_engine.styles import (
            DIAGRAM_ZONE_BOTTOM,
            DIAGRAM_ZONE_TOP,
            SAFE_AREA_BOTTOM,
            SAFE_AREA_LEFT,
            SAFE_AREA_RIGHT,
            SAFE_AREA_TOP,
        )

        new_mobs = [self.objects[k] for k in new_ids if k in self.objects]
        if not new_mobs:
            return

        group = VGroup(*new_mobs)
        g_top = group.get_top()[1]

        # Clamp below safe area top (topic header zone)
        if g_top > SAFE_AREA_TOP:
            group.shift([0, SAFE_AREA_TOP - g_top, 0])
            g_top = group.get_top()[1]

        # -- helper: check overlap with existing objects -------------------
        def _overlaps() -> list[str]:
            gb = BBox(
                float(group.get_left()[0]), float(group.get_right()[0]),
                float(group.get_bottom()[1]), float(group.get_top()[1]),
            )
            return [
                oid for oid, bbox in self.visible_bounds()
                if gb.overlaps(bbox, margin=0.15) and oid not in new_ids
            ]

        hits = _overlaps()
        if not hits:
            for nid in new_ids:
                self.refresh_bounds(nid)
            return

        # --- 1. Full-size vacant rect search ------------------------------
        vacant = self.find_vacant_rect(group.width + 0.3, group.height + 0.3)
        if vacant is not None:
            group.move_to([vacant[0], vacant[1], 0])
            if not _overlaps():
                self._clamp_and_finish(group, new_ids, SAFE_AREA_TOP, SAFE_AREA_BOTTOM)
                return

        # --- 2. Scale to 70% and retry -----------------------------------
        original_height = group.height
        group.scale(0.7)
        vacant = self.find_vacant_rect(group.width + 0.3, group.height + 0.3)
        if vacant is not None:
            group.move_to([vacant[0], vacant[1], 0])
            if not _overlaps():
                self._clamp_and_finish(group, new_ids, SAFE_AREA_TOP, SAFE_AREA_BOTTOM)
                return
        # Restore scale for zone attempts
        group.scale(1.0 / 0.7)

        # --- 3. Try top reserved zone (above diagram, below header) ------
        top_zone_h = SAFE_AREA_TOP - DIAGRAM_ZONE_TOP  # ~0.8 units
        if top_zone_h > 0.3:
            scale = min(1.0, top_zone_h / group.height)
            if scale >= 0.35:
                group.scale(scale)
                zone_cy = (DIAGRAM_ZONE_TOP + SAFE_AREA_TOP) / 2
                group.move_to([0, zone_cy, 0])
                if not _overlaps():
                    self._clamp_and_finish(group, new_ids, SAFE_AREA_TOP, SAFE_AREA_BOTTOM)
                    return
                group.scale(1.0 / scale)

        # --- 4. Try bottom reserved zone (below diagram, above subtitle) -
        bot_zone_h = DIAGRAM_ZONE_BOTTOM - SAFE_AREA_BOTTOM  # ~0.8 units
        if bot_zone_h > 0.3:
            scale = min(1.0, bot_zone_h / group.height)
            if scale >= 0.35:
                group.scale(scale)
                zone_cy = (SAFE_AREA_BOTTOM + DIAGRAM_ZONE_BOTTOM) / 2
                group.move_to([0, zone_cy, 0])
                if not _overlaps():
                    self._clamp_and_finish(group, new_ids, SAFE_AREA_TOP, SAFE_AREA_BOTTOM)
                    return
                group.scale(1.0 / scale)

        # --- 5. Final fallback: shift below lowest persistent & scale -----
        hit_bounds = [self._bounds[pid] for pid in hits if pid in self._bounds]
        if hit_bounds:
            p_bot = min(b.bottom for b in hit_bounds)
            target_top = p_bot - 0.35
            group.shift([0, target_top - group.get_top()[1], 0])

            if group.get_bottom()[1] < SAFE_AREA_BOTTOM:
                available = target_top - SAFE_AREA_BOTTOM
                if available > 0.3 and group.height > available:
                    group.scale(available / group.height)
                    group.move_to([group.get_center()[0],
                                   target_top - group.height / 2, 0])

        self._clamp_and_finish(group, new_ids, SAFE_AREA_TOP, SAFE_AREA_BOTTOM)

    def _clamp_and_finish(self, group, new_ids: set[str],
                          sa_top: float, sa_bot: float) -> None:
        """Clamp group to safe area and refresh cached bounds."""
        if group.get_top()[1] > sa_top:
            group.shift([0, sa_top - group.get_top()[1], 0])
        if group.get_bottom()[1] < sa_bot:
            group.shift([0, sa_bot - group.get_bottom()[1], 0])
        for nid in new_ids:
            self.refresh_bounds(nid)


def _dispatch_action(scene, state: SceneState, action) -> None:
    """Route a single VisualAction to its renderer function."""
    from rendering_engine.cloud import (
        render_create_cloud_region,
        render_create_cloud_service,
        render_show_data_flow,
    )
    from rendering_engine.data_display import (
        render_show_header_breakdown,
        render_show_layer_stack,
        render_show_math,
        render_show_table,
    )
    from rendering_engine.packets import render_send_broadcast, render_send_packet
    from rendering_engine.presentation import (
        render_show_bullet_list,
        render_show_code_block,
        render_show_comparison,
        render_show_text_block,
    )
    from rendering_engine.retention import (
        render_add_callout,
        render_dim_except,
        render_emphasize_text,
        render_focus_camera,
        render_pulse_element,
        render_reset_camera,
        render_restore_opacity,
        render_scene_transition,
        render_shake_element,
        render_show_progress,
        render_update_progress,
    )
    from rendering_engine.sequence import render_show_sequence_diagram
    from rendering_engine.topology import (
        render_create_connection,
        render_create_node,
        render_create_topology,
        render_remove_element,
        render_update_node,
    )
    from rendering_engine.broll import render_show_image
    from rendering_engine.lottie_renderer import render_show_lottie
    from rendering_engine.effects import (
        render_flash_cut,
        render_glitch_transition,
        render_zoom_punch,
    )
    from rendering_engine.charts import render_show_chart

    dispatch = {
        "create_node": render_create_node,
        "create_connection": render_create_connection,
        "update_node": render_update_node,
        "remove_element": render_remove_element,
        "create_topology": render_create_topology,
        "send_packet": render_send_packet,
        "send_broadcast": render_send_broadcast,
        "show_sequence_diagram": render_show_sequence_diagram,
        "show_layer_stack": render_show_layer_stack,
        "show_header_breakdown": render_show_header_breakdown,
        "show_table": render_show_table,
        "show_math": render_show_math,
        "show_text_block": render_show_text_block,
        "show_code_block": render_show_code_block,
        "show_comparison": render_show_comparison,
        "show_bullet_list": render_show_bullet_list,
        "create_cloud_region": render_create_cloud_region,
        "create_cloud_service": render_create_cloud_service,
        "show_data_flow": render_show_data_flow,
        "pulse_element": render_pulse_element,
        "focus_camera": render_focus_camera,
        "reset_camera": render_reset_camera,
        "show_progress": render_show_progress,
        "update_progress": render_update_progress,
        "emphasize_text": render_emphasize_text,
        "shake_element": render_shake_element,
        "dim_except": render_dim_except,
        "restore_opacity": render_restore_opacity,
        "add_callout": render_add_callout,
        "scene_transition": render_scene_transition,
        "show_image": render_show_image,
        "show_lottie": render_show_lottie,
        "flash_cut": render_flash_cut,
        "zoom_punch": render_zoom_punch,
        "glitch_transition": render_glitch_transition,
        "show_chart": render_show_chart,
    }

    handler = dispatch.get(action.type)
    if handler is None:
        logger.warning("Unknown action type: %s — skipping", action.type)
        return

    is_pres = action.type in _PRESENTATION_TYPES
    is_soft_pres = action.type in _SOFT_PRESENTATION_TYPES

    if is_pres:
        state.clear_presentation(scene)

    pre_ids = set(state.objects)
    try:
        handler(scene, state, action)
    except Exception:
        logger.exception("Action '%s' crashed — skipping", action.type)
        return
    new_ids = set(state.objects) - pre_ids

    category = "presentation" if (is_pres or is_soft_pres) else "persistent"
    for nid in new_ids:
        state._categories[nid] = category

    if (is_pres or is_soft_pres) and new_ids:
        state.avoid_overlap(new_ids)


def _rebuild_action(action_dict: dict):
    """Reconstruct a typed VisualAction from a raw dict."""
    from models_semantic import VisualAction
    from pydantic import TypeAdapter

    adapter = TypeAdapter(VisualAction)
    try:
        return adapter.validate_python(action_dict)
    except Exception as e:
        logger.warning("Failed to rebuild action %s: %s", action_dict.get("type"), e)
        return None


def _serialize_script(script: EnrichedVideoScript) -> dict:
    return {
        "topic": script.topic,
        "title_card_subtitle": script.title_card_subtitle or "",
        "category": script.category or "",
        "video_title": script.video_title or "",
        "video_hook": script.video_hook or "",
        "emotional_tone": script.emotional_tone or "",
        "scenes": [
            {
                "scene_id": s.scene_id,
                "title": s.title,
                "narration": s.narration,
                "actions": [a.model_dump(by_alias=True) for a in s.actions],
                "audio_duration": s.audio_duration or s.estimated_duration,
                "audio_path": s.audio_path,
                # Critical for subtitle pacing: pause_after extends the
                # subtitle window past raw audio, whisper_words drives
                # exact subtitle-to-narration alignment.
                "pause_after": s.pause_after or 0.0,
                "whisper_words": list(getattr(s, "whisper_words", None) or []),
                # Voice/music mood — read by the shorts pipeline's
                # _add_shorts_scene_glow + warning_pulse + success_stamp
                # triggers.  Was the missing piece: without these in the
                # data dict, the Manim subprocess saw voice_mood='' for
                # every scene and the per-scene mood panel never painted
                # except on the last (CTA) scene where the mood is
                # forced to "excited".
                "voice_mood": getattr(s, "voice_mood", "") or "",
                "music_mood": getattr(s, "music_mood", "") or "",
            }
            for s in script.scenes
        ],
    }


def render_full_semantic_video(
    script: EnrichedVideoScript,
    output_dir: Path | str | None = None,
) -> str | None:
    """Single Manim pass: ``FullSemanticVideo`` in ``full_video_runner.py``.

    Returns path to the rendered silent ``.mp4``, or ``None`` on failure.
    """
    dest_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    data = _serialize_script(script)
    fd, json_path = tempfile.mkstemp(suffix=".json", prefix="semantic_data_")
    os.close(fd)
    Path(json_path).write_text(json.dumps(data), encoding="utf-8")

    work_dir = Path(tempfile.mkdtemp(prefix="semantic_render_"))
    media_dir = work_dir / "media"
    manifest_path = work_dir / "scene_timings.json"

    env = os.environ.copy()
    env["SEMANTIC_DATA_JSON"] = json_path
    env["SEMANTIC_TIMING_MANIFEST"] = str(manifest_path)

    cmd = [
        "python",
        "-m",
        "manim",
        "render",
        "-q",
        MANIM_QUALITY,
        "--media_dir",
        str(media_dir),
        "--disable_caching",
        str(RUNNER),
        RUNNER_CLASS,
    ]

    # Stream Manim's stdout/stderr to a log file rather than capturing in
    # memory (capture_output=True deadlocks on WSL when pipe buffers fill
    # faster than the parent drains them) AND watch that log for Manim's
    # combine-step crash signature so we can SIGKILL the wedged subprocess
    # without the user having to do it by hand.
    log_path = work_dir / "manim_render.log"
    logger.info("Full semantic render: %s", " ".join(cmd))
    logger.info("Manim stdout/stderr: %s (tail -f to watch)", log_path)

    try:
        # 2-hour render cap.  WSL-backed renders of full long-form videos
        # routinely take 50–80 minutes on lower-spec laptops; the previous
        # 60-minute cap was tripping a SIGKILL right before construct()
        # finished, leaving the manifest at scene 8 of 16.
        result = _run_manim_with_crash_watch(cmd, log_path, env=env, timeout=7200)
    finally:
        Path(json_path).unlink(missing_ok=True)

    # Look for the final mp4 Manim should have produced.  Validate it —
    # Manim's broken combine_files leaves a moov-less corpse on disk that
    # we must not mistake for the real output.
    rendered: Path | None = None
    for mp4 in media_dir.rglob(f"{RUNNER_CLASS}.mp4"):
        if "partial_movie_files" in str(mp4):
            continue
        if _mp4_is_valid(mp4):
            rendered = mp4
            break
        logger.warning("Ignoring corrupt %s (probably from a Manim combine crash)", mp4)
        try:
            mp4.unlink()
        except Exception:
            pass

    # Fallback: Manim's `combine_files` step crashes on certain
    # PyAV/Python combos (FileNotFoundError on partial_movie_file_list.txt)
    # AFTER all per-animation partials have been rendered successfully.
    # When that happens, concat the partials ourselves with ffmpeg so the
    # render is recoverable without manual intervention.
    if rendered is None:
        partial_dir = (
            media_dir / "videos" / "full_video_runner"
            / f"{MANIM_QUALITY_DIR_MAP.get(MANIM_QUALITY, '720p30')}"
            / "partial_movie_files" / RUNNER_CLASS
        )
        # Glob ALL .mp4 partials, not just uncached_*.  Manim writes
        # cached/hash-named files for some animations even with
        # --disable_caching (notably intro/title/outro cards), and missing
        # them causes the concat'd video to be shorter than the manifest
        # claims, which makes every downstream audio cue land on the
        # wrong frame.  Order by mtime — partials are write-once and in
        # render order, so mtime is a reliable index.
        partials = sorted(
            (p for p in partial_dir.glob("*.mp4") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
        ) if partial_dir.is_dir() else []

        if partials:
            logger.warning(
                "Manim's combine step did not produce %s.mp4 but %d partials "
                "are present — running ffmpeg concat fallback.",
                RUNNER_CLASS, len(partials),
            )
            rendered = partial_dir.parent / f"{RUNNER_CLASS}.mp4"
            if not _ffmpeg_concat(partials, rendered):
                rendered = None
            else:
                _verify_concat_matches_manifest(rendered, manifest_path)

    if rendered is None:
        if result.returncode != 0:
            try:
                tail = log_path.read_text(encoding="utf-8", errors="replace")[-6000:]
            except Exception:
                tail = "<failed to read manim log>"
            logger.error("Full semantic render failed:\n%s", tail)
        else:
            logger.error(
                "Render finished but %s.mp4 not found under %s and no "
                "partials available for fallback concat.",
                RUNNER_CLASS, media_dir,
            )
        return None

    out = dest_dir / "full_semantic_silent.mp4"
    out.unlink(missing_ok=True)
    # shutil.move falls back to copy2 across devices (/tmp -> /mnt/c) and
    # copy2 tries to mirror Linux timestamps, which Windows refuses.  Use
    # copyfile + unlink to dodge the chmod/utime traps.
    shutil.copyfile(str(rendered), str(out))
    Path(rendered).unlink(missing_ok=True)
    logger.info("Silent full video: %s", out)

    # Copy the timing manifest next to the silent video so the audio mux
    # can rebuild narration with per-scene boundaries that match the
    # actual rendered timeline (eliminates accumulated AV drift).
    # copyfile (not copy) — copy() tries chmod which fails on /mnt/c.
    if manifest_path.exists():
        try:
            shutil.copyfile(str(manifest_path), str(dest_dir / "scene_timings.json"))
            logger.info("Scene timing manifest: %s", dest_dir / "scene_timings.json")
        except Exception as e:
            logger.warning("Could not copy scene timing manifest: %s", e)

    return str(out)


# ---------------------------------------------------------------------------
# Shorts (vertical 9:16) render path
# ---------------------------------------------------------------------------

SHORTS_RUNNER = Path(__file__).resolve().parent / "shorts_runner.py"
SHORTS_RUNNER_CLASS = "ShortsSemanticVideo"

# 1080x1920 vertical at 30 fps.  Forced via Manim CLI flags so the user's
# MANIM_QUALITY env var (which targets 16:9) doesn't fight us.
SHORTS_PIXEL_W = 1080
SHORTS_PIXEL_H = 1920
SHORTS_FPS = 30


def render_shorts_video(
    script: EnrichedVideoScript,
    output_dir: Path | str | None = None,
) -> str | None:
    """Render a vertical 9:16 short via ``ShortsSemanticVideo``.

    Same data plumbing as ``render_full_semantic_video`` (script JSON written
    to a tempfile, scene_timings manifest written by the construct, copied
    to the output dir afterwards).  Differences:

    * Uses the ``shorts_runner.py`` module which sets ``frame_width=8`` and
      ``frame_height=14.222`` at module load.
    * Forces 1080x1920 @ 30fps via ``-r`` and ``--fps`` CLI flags.
    * The construct function detects ``data["mode"] == "shorts"`` and skips
      intro/title/outro chrome and the persistent topic header.

    Returns the path to the rendered silent ``.mp4`` (still vertical), or
    ``None`` on failure.  The audio mux happens upstream in ``main.py``.
    """
    dest_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    data = _serialize_script(script)
    data["mode"] = "shorts"
    fd, json_path = tempfile.mkstemp(suffix=".json", prefix="shorts_data_")
    os.close(fd)
    Path(json_path).write_text(json.dumps(data), encoding="utf-8")

    work_dir = Path(tempfile.mkdtemp(prefix="shorts_render_"))
    media_dir = work_dir / "media"
    manifest_path = work_dir / "scene_timings.json"

    env = os.environ.copy()
    env["SEMANTIC_DATA_JSON"] = json_path
    env["SEMANTIC_TIMING_MANIFEST"] = str(manifest_path)

    cmd = [
        "python",
        "-m",
        "manim",
        "render",
        "-r",
        f"{SHORTS_PIXEL_W},{SHORTS_PIXEL_H}",
        "--fps",
        str(SHORTS_FPS),
        "--media_dir",
        str(media_dir),
        "--disable_caching",
        str(SHORTS_RUNNER),
        SHORTS_RUNNER_CLASS,
    ]

    # See render_full_semantic_video — log to file and watch for the
    # combine-step crash so we can self-kill a wedged Manim.
    log_path = dest_dir / "manim_render.log"
    dest_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Shorts render: %s", " ".join(cmd))
    logger.info("Shorts subprocess log: %s (tail -f to watch)", log_path)

    try:
        result = _run_manim_with_crash_watch(cmd, log_path, env=env, timeout=1800)
    finally:
        Path(json_path).unlink(missing_ok=True)

    # Surface any "Shorts panel:" diagnostic warnings from the log to the
    # parent so they appear in the user's console without hunting.
    try:
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "Shorts panel" in line or "Shorts glow" in line:
                logger.warning("[manim subprocess] %s", line.strip())
    except Exception:
        pass

    # Look for the final mp4 Manim should have produced.  Validate it —
    # see render_full_semantic_video for why corrupt mp4s show up.
    rendered: Path | None = None
    for mp4 in media_dir.rglob(f"{SHORTS_RUNNER_CLASS}.mp4"):
        if "partial_movie_files" in str(mp4):
            continue
        if _mp4_is_valid(mp4):
            rendered = mp4
            break
        logger.warning("Ignoring corrupt %s (probably from a Manim combine crash)", mp4)
        try:
            mp4.unlink()
        except Exception:
            pass

    # Fallback: same PyAV/combine_files crash as the long-form pipeline.
    # Find the partial_movie_files dir via rglob (since the quality dir
    # name varies with the resolution flag) and concat with ffmpeg.
    if rendered is None:
        partial_dirs = [
            d for d in media_dir.rglob("partial_movie_files")
            if d.is_dir() and (d / SHORTS_RUNNER_CLASS).is_dir()
        ]
        partials: list[Path] = []
        scene_dir: Path | None = None
        if partial_dirs:
            scene_dir = partial_dirs[0] / SHORTS_RUNNER_CLASS
            # Glob all .mp4 partials (cached + uncached) ordered by mtime
            # — see render_full_semantic_video for why uncached_* alone
            # is not enough.
            partials = sorted(
                (p for p in scene_dir.glob("*.mp4") if p.is_file()),
                key=lambda p: p.stat().st_mtime,
            )

        if partials and scene_dir is not None:
            logger.warning(
                "Manim's combine step did not produce %s.mp4 but %d partials "
                "are present — running ffmpeg concat fallback.",
                SHORTS_RUNNER_CLASS, len(partials),
            )
            rendered = scene_dir.parent.parent / f"{SHORTS_RUNNER_CLASS}.mp4"
            if not _ffmpeg_concat(partials, rendered):
                rendered = None
            else:
                _verify_concat_matches_manifest(rendered, manifest_path)

    if rendered is None:
        if result.returncode != 0:
            try:
                tail = log_path.read_text(encoding="utf-8", errors="replace")[-6000:]
            except Exception:
                tail = "<failed to read manim log>"
            logger.error("Shorts render failed:\n%s", tail)
        else:
            logger.error(
                "Shorts render finished but %s.mp4 not found under %s and no "
                "partials available for fallback concat.",
                SHORTS_RUNNER_CLASS, media_dir,
            )
        return None

    out = dest_dir / "shorts_silent.mp4"
    out.unlink(missing_ok=True)
    # See render_full_semantic_video — shutil.move dies on /tmp -> /mnt/c.
    shutil.copyfile(str(rendered), str(out))
    Path(rendered).unlink(missing_ok=True)
    logger.info("Silent vertical short: %s", out)

    # copyfile (not copy) — copy() tries chmod which fails on /mnt/c.
    if manifest_path.exists():
        try:
            shutil.copyfile(str(manifest_path), str(dest_dir / "scene_timings.json"))
            logger.info("Shorts timing manifest: %s", dest_dir / "scene_timings.json")
        except Exception as e:
            logger.warning("Could not copy shorts timing manifest: %s", e)

    return str(out)
