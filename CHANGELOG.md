# Retention Upgrade — Changelog

## Overview

Transforms generated videos from "static educational lecture" into "high-retention YouTube educational explainer" while keeping the deterministic Semantic JSON + Manim engine architecture intact.

---

## Files Changed (18 modified, 7 new)

### Modified

| File | Changes |
|---|---|
| `models_semantic.py` | 11 new Pydantic action models + 9 optional metadata fields on script models |
| `semantic_validation.py` | Validation for `target_id` / `target_ids` references in new actions |
| `rendering_engine/engine.py` | Dispatch table expanded with all 11 new action types; narration + category passed in serializer |
| `rendering_engine/styles.py` | New constants: progress UI, subtitle, callout, emphasis, category accent colors |
| `rendering_engine/full_video_scene.py` | Camera reset between scenes, subtitle integration, category-accent title card, `target_id`/`target_ids` in future refs |
| `rendering_engine/full_video_runner.py` | Upgraded from `Scene` to `MovingCameraScene` for camera zoom/pan |
| `semantic_audio.py` | SFX track builder, background music looper, integrated into narration builder |
| `main.py` | Retention enrichment step added; scene actions passed to audio builder |
| `prompts/_base.py` | `RETENTION_STRATEGY` block, new actions in `ACTION_VOCABULARY`, metadata in `OUTPUT_FORMAT`, new rules in `SHARED_RULES` |
| `prompts/data_structures.py` | Retention-first video structure, retention tools in preferred actions, updated example scene |
| `prompts/networking.py` | Retention tools added to preferred actions |
| `prompts/programming.py` | Retention tools added to preferred actions |
| `prompts/security.py` | Retention tools added to preferred actions |
| `prompts/system_design.py` | Retention tools added to preferred actions |
| `prompts/databases.py` | Retention tools added to preferred actions |
| `prompts/cloud_architecture.py` | Retention tools added to preferred actions |
| `prompts/business_analysis.py` | Retention tools added to preferred actions |
| `.env.example` | All new config variables documented |

### New Files

| File | Purpose |
|---|---|
| `config.py` | Centralized env-var configuration with safe defaults |
| `retention.py` | `ensure_retention_beats()` — 3-second visual change rule enforcer |
| `rendering_engine/retention.py` | Renderers for all 11 new actions (pulse, shake, camera, progress, emphasize, dim, restore, callout, transition) |
| `rendering_engine/subtitles.py` | Phrase-chunked lower-third subtitle renderer |
| `tests/test_retention_upgrade.py` | 29 tests covering parsing, validation, backward compat, subtitles, config, sample script |
| `samples/binary_search_sample.json` | Full 13-scene sample demonstrating all new features |
| `assets/sfx/.gitkeep` + `assets/music/.gitkeep` | Placeholder directories for audio assets |

---

## What Was Added

### 1. New Visual Actions (11 types)

| Action | Purpose |
|---|---|
| `pulse_element` | Make an existing object briefly pulse/glow to draw attention |
| `focus_camera` | Zoom/pan camera to an object or area (conservative 1.1–1.35 range) |
| `reset_camera` | Return to normal full-frame view |
| `show_progress` | Show a persistent progress indicator (e.g. "Step 1 of 5: Find middle") |
| `update_progress` | Update the progress indicator text and bar |
| `emphasize_text` | Show a large kinetic phrase briefly for impact |
| `shake_element` | Shake an element to indicate failure, error, or wrong choice |
| `dim_except` | Dim all elements except specified targets to spotlight them |
| `restore_opacity` | Restore all elements to normal opacity after dim |
| `add_callout` | Small explanatory label pointing to an element |
| `scene_transition` | Polished transition between major sections |

### 2. Script Metadata

Optional top-level JSON fields for better video discoverability:

- `video_title` — catchy video title
- `video_hook` — the opening hook line
- `open_loop_question` — unresolved question posed early
- `open_loop_resolution_scene_id` — scene where the open loop is resolved
- `retention_beats` — array of re-hook phrases used in narration
- `target_audience` — e.g. "CS students", "junior developers"
- `emotional_tone` — e.g. "curious and energetic"
- `suggested_thumbnail_text` — short punchy thumbnail text
- `suggested_youtube_title` — optimized YouTube title

### 3. Moving Camera

- Scene class upgraded from `Scene` to `MovingCameraScene`
- `focus_camera` zooms into specific objects or coordinates
- `reset_camera` smoothly returns to default view
- Camera auto-resets between scenes to prevent disorientation
- Default zoom range: 1.1–1.35 (configurable)

### 4. Retention-First Prompting

Every LLM-generated script now follows:

- **High-stakes hook** — Scene 1 opens with a real-world problem or curiosity gap
- **Open loop** — An unresolved question introduced early, resolved near the end
- **Failure-first teaching** — Show the wrong/slow approach before the solution
- **Re-hooks every 45–60 seconds** — Attention reset phrases in narration
- **Conversational tone** — Direct and energetic, not textbook
- All 8 domain prompts updated with retention tool guidance

### 5. Progress UI

- Persistent progress bar at screen bottom
- Subtle, sleek, non-distracting
- Works across scenes via `show_progress` / `update_progress`
- Configurable via `ENABLE_PROGRESS_UI`

### 6. Subtitles

- Scene-level subtitles from narration text
- Phrase-chunked: 3–7 words per subtitle
- High-contrast lower-third positioning
- Avoids covering main diagram content
- Configurable: `ENABLE_SUBTITLES`, `SUBTITLE_MODE`, `SUBTITLE_MAX_WORDS`

### 7. SFX & Background Music

| Action | Sound File |
|---|---|
| `create_node` | `soft_pop.wav` |
| `create_connection` | `connect_click.wav` |
| `send_packet` | `whoosh.wav` |
| `send_broadcast` | `multi_whoosh.wav` |
| `show_table` | `click.wav` |
| `show_code_block` | `keyboard_tick.wav` |
| `show_math` | `sparkle_ping.wav` |
| `shake_element` | `error_buzz.wav` |
| `scene_transition` | `transition_sweep.wav` |
| `emphasize_text` | `impact_pop.wav` |

Background music loops: `curious_loop.mp3`, `explain_loop.mp3`, `reveal_loop.mp3`

All audio assets are optional — pipeline logs warnings and continues if missing.

### 8. 3-Second Visual Change Rule

- `ensure_retention_beats()` analyzes each scene's narration duration vs visual activity
- If a scene would be visually dormant for more than 3 seconds, subtle beats are injected
- Currently injects `pulse_element` on the most recently referenced object
- Configurable via `RETENTION_MODE` and `MAX_IDLE_VISUAL_SECONDS`

### 9. Category Accent Colors

| Category | Accent Color |
|---|---|
| `networking` | Blue / Cyan |
| `data-structures` | Purple |
| `programming` | Green |
| `cloud-architecture` | Sky Blue |
| `system-design` | Orange |
| `databases` | Yellow / Gold |
| `security` | Red |
| `business-analysis` | Teal |

Applied to title cards automatically based on detected category.

### 10. Backward Compatibility

- All new fields are optional with safe defaults
- Old scripts render without modification
- Missing SFX/music assets log warnings but do not crash
- Missing `target_id` in retention actions logs a warning and skips
- Validation understands all new action types
- Pipeline works with all features disabled

---

## Configuration

All options via environment variables (or `.env` file):

```bash
# Retention
RETENTION_MODE=true              # Auto-inject visual beats in dormant scenes
MAX_IDLE_VISUAL_SECONDS=3        # Max seconds before injecting a visual beat

# Camera
ENABLE_CAMERA_MOTION=true        # Enable focus_camera / reset_camera
CAMERA_DEFAULT_ZOOM=1.2          # Default zoom level for focus_camera
CAMERA_MAX_ZOOM=1.35             # Maximum allowed zoom

# Progress UI
ENABLE_PROGRESS_UI=true          # Enable show_progress / update_progress

# Subtitles
ENABLE_SUBTITLES=true            # Enable scene-level subtitles
SUBTITLE_MODE=phrase             # "phrase" or "word"
SUBTITLE_POSITION=bottom         # "bottom" or "center"
SUBTITLE_MAX_WORDS=7             # Max words per subtitle chunk

# Sound Effects
ENABLE_SFX=true                  # Enable action-mapped sound effects
SFX_VOLUME_DB=-16                # SFX volume in dB (relative to narration)

# Background Music
ENABLE_BACKGROUND_MUSIC=true     # Enable looped background music
MUSIC_VOLUME_DB=-28              # Music volume in dB (ducked under narration)
```

---

## How to Run

### Standard Run (all features enabled by default)

```bash
python main.py --topic "Binary Search" --category data-structures
```

### Auto-Detect Category

```bash
python main.py --topic "How DNS Resolution Works"
```

### With Explicit Category

```bash
python main.py --topic "TCP Three-Way Handshake" --category networking
python main.py --topic "AWS VPC Design" --category cloud-architecture
python main.py --topic "B-Tree Indexes" --category databases
```

### Disable Specific Features

```bash
# Disable subtitles and SFX
ENABLE_SUBTITLES=false ENABLE_SFX=false python main.py --topic "Hash Maps"

# Disable all new features (legacy-equivalent rendering)
RETENTION_MODE=false ENABLE_SUBTITLES=false ENABLE_SFX=false ENABLE_BACKGROUND_MUSIC=false ENABLE_PROGRESS_UI=false python main.py --topic "Sorting Algorithms"
```

### Run Tests

```bash
python -m pytest tests/test_retention_upgrade.py -v
```

### Test Coverage

- 29 tests covering:
  - Pydantic parsing of all 11 new action types
  - Validation of target references (valid + invalid)
  - Backward compatibility with old scripts
  - Subtitle phrase chunking
  - Config defaults
  - Sample script loading and validation
  - Retention beat enrichment

---

## Assets Required (Optional)

The pipeline works without any audio assets. To enable SFX and music:

### Sound Effects

Place `.wav` files in `assets/sfx/`:

```
assets/sfx/
├── soft_pop.wav
├── connect_click.wav
├── whoosh.wav
├── multi_whoosh.wav
├── click.wav
├── keyboard_tick.wav
├── sparkle_ping.wav
├── error_buzz.wav
├── transition_sweep.wav
└── impact_pop.wav
```

### Background Music

Place `.mp3` loops in `assets/music/`:

```
assets/music/
├── curious_loop.mp3
├── explain_loop.mp3
└── reveal_loop.mp3
```

Royalty-free sources: [Pixabay](https://pixabay.com/music/), [Freesound](https://freesound.org/), [Mixkit](https://mixkit.co/free-sound-effects/).

---

## Limitations

- **SFX/music** require actual audio files in `assets/` — gracefully skipped if missing
- **Subtitle timing** is estimated from narration chunking, not word-level TTS timestamps; can be enhanced later with TTS word-timestamp APIs
- **Camera motion** uses `MovingCameraScene` which may have minor visual differences from plain `Scene` for certain Manim effects
- **Retention beats** auto-injection is conservative (only adds pulses); the LLM prompt system handles most retention via scripting quality
- **Background music ducking** is volume-based (constant level), not dynamic sidechain ducking

---

## Architecture Preserved

The core architecture remains unchanged:

```
Topic (CLI)
    │
    ▼
Category Detection → Specialty Prompt → LLM (GPT-4.1)
    │                                        │
    ▼                                        ▼
Semantic JSON Script ← ─ ─ ─ ─ ─ ─ ─ ─  Structured Actions
    │
    ├──→ Repair IDs → Validate → Retention Beats (NEW)
    │
    ├──→ TTS → Narration + SFX + Music (NEW)
    │
    ├──→ Manim Render (MovingCameraScene + Subtitles + Progress UI) (UPGRADED)
    │
    └──→ ffmpeg Mux → Final MP4
```

The LLM never writes code. All rendering is deterministic. All new features are additive and optional.
