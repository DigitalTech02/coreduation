# CoreDuation — Changelog

## v4.0 — Reliability + Shorts (May 2026)

Four numbered tracks shipped on `semantic-engine-v6` → `v9` over April–May 2026. Shifts the project from "polished single-deliverable pipeline" to "guaranteed-AV-synced multi-platform content engine." All work additive and gated by feature flags / CLI flags.

### Track 4 — Per-scene frame validation + auto-fix (Apr 2026)

| # | Feature | Modules |
|---|---|---|
| 1 | **Deterministic frame validator** — samples each scene at known timestamps, asserts visible content matches the script's expected ids/text. Cheap (no LLM), runs every render. | `frame_validator.py`, `tests/test_frame_validator.py` |
| 2 | **Scene QA structured-output audit** — optional GPT-4o per-scene check with structured-output JSON for blank/overlap/cutoff/illegibility issues. Gated by `ENABLE_SCENE_QA`. | `vision_qa.py:run_scene_qa` |
| 3 | **Auto-fix retry loop** — collects failed scenes, re-asks the LLM for revised actions, re-renders just those scenes, re-stitches. Gated by `ENABLE_AUTO_FIX`. | `auto_fix.py`, `tests/test_auto_fix.py` |

### Track 5 — Whisper subtitles + ambient visuals + YouTube bridge (May 2026)

| # | Feature | Modules |
|---|---|---|
| 4 | **Whisper-aligned scheduled subtitles** — `whisper_align.py` returns word-level timestamps; `subtitles.schedule_subtitles_for_scene` pre-creates subtitle mobjects with per-frame opacity updaters bound to `(scene.renderer.time - scene_start)`. Subtitles track narration audio progression in real time, not the post-action wait. Min-3-words rule + forward/backward merge eliminates "So", "Now", "But wait" fragments. | `whisper_align.py`, `rendering_engine/subtitles.py`, `rendering_engine/full_video_scene.py` |
| 5 | **Drifting particle field** — 22 dots scattered across the canvas, biased to the margins, faded to 35 % inside the safe area. Per-particle sin-wave drift so the field never pulses in lockstep. | `rendering_engine/themes.py:_add_particle_field` |
| 6 | **Margin-zone ambient decor** — slow-rotating stars/polygons/circles in the side strips outside the safe area. | `rendering_engine/ambient.py` |
| 7 | **Isometric drop shadows** — stacked dark offset copies behind cards/topology nodes via `make_isometric_shadow`. Cheap depth illusion. | `rendering_engine/styles.py`, `rendering_engine/topology.py`, `rendering_engine/presentation.py` |
| 8 | **Always-on persistent topic header** — never hidden mid-video so a viewer joining late always knows the topic. | `rendering_engine/full_video_scene.py:_toggle_persistent_topic_header` |
| 9 | **Persistent credit label** — dim "Created by Human & AI" anchored to the camera frame's top-left corner. | `rendering_engine/branding.py:add_credit_label` |
| 10 | **YouTube export bridge** — pipeline output auto-copied into `Youtube_Upload/videos/` as `stitched_video_set_<N>.{mp4,txt,png}` so the standalone `Youtube_Upload/youtubeupload4.py` uploader picks it up unchanged. | `youtube_upload_export.py` |
| 11 | **OAuth multi-path search** — in-pipeline uploader searches both root and `Youtube_Upload/` for `client_secret(s).json` and reuses cached `token.pickle` from the standalone uploader. | `youtube_uploader.py` |
| 12 | **Selective music + lower volume** — `MUSIC_PLAYBACK_MODE` flag (default `selective`); music plays only on intro/outro stings + scenes whose `music_mood` is in `MUSIC_HIGHLIGHT_MOODS` (default: `tense`). `MUSIC_VOLUME_DB` lowered −28 → −36 dB. Drops continuous music coverage from ~100 % to ~8 % of typical video length. | `config.py`, `semantic_audio.py:_build_music_track_from_manifest` |
| 13 | **Hybrid layout collision rule** — `_avoid_collision` two-state: full diagram OR text-on-card; never "diagram + text awkwardly stacked". Path 1 relocates text to a vacant region; Path 2 hides the topology and centers the text on a fully opaque card with isometric shadow. | `rendering_engine/presentation.py` |
| 14 | **Disabled keyword burst** — built and shipped behind `ENABLE_KEYWORD_BURST=false`. Even relocated to a vacant region the giant dimmed background word competed with content. Kept for future experiments. | `rendering_engine/keyword_overlay.py` |
| 15 | **Cinematic SFX** — `flash_cut` → `suspenseful_boom.mp3`, `zoom_punch` / `glitch_transition` → `cinematic_impact_hit.mp3`, `scene_transition` upgraded to `whoosh_cinematic.mp3`. | `assets/sfx/`, `semantic_audio.SFX_MAP` |

### Track 6 — Manifest-driven AV alignment (May 2026, fix for chronic ~17s drift)

The structural fix for narration/subtitle desync that grew across long videos.

**Root cause** (memory: `feedback_av_sync_drift.md`): two independent timelines with no shared source of truth for scene boundaries. Audio mux assumed each scene ran for `audio_dur + pause_after + SCENE_GAP_SECONDS`; renderer actually took `max(actions_elapsed, audio_dur + pause_after − 0.30) + 0.30 + 0.15`. When LLM-emitted action `run_time`s exceeded the budget, every scene overshot — drift accumulated to 17.12 s by the end of a 19-scene render. The `_pad_audio_to_video` band-aid hid the symptom at t=0 and made it maximal at t=end.

**Fix:**

| # | Feature | Modules |
|---|---|---|
| 16 | **Renderer manifest** — `run_full_video_construct` writes `scene_timings.json` with each scene's actual `video_start_seconds` and `video_end_seconds`. Path coordinated via `SEMANTIC_TIMING_MANIFEST` env var. | `rendering_engine/full_video_scene.py`, `rendering_engine/engine.py` |
| 17 | **Manifest-aligned audio mux** — `build_narration_track_from_manifest` overlays each scene's TTS at exactly its declared `video_start_seconds`. Total length = `manifest.total_video_duration` by construction. SFX positioned at scene-relative action offsets. Music swaps at the manifest's scene boundaries. Falls back to legacy cumulative builder only if the manifest is missing (defensive). | `semantic_audio.py:build_narration_track_from_manifest` |
| 18 | **Drift-invariant tests** — irregular per-scene boundaries (simulating arbitrary overshoots) prove narration always lands at declared positions. 10 new tests in `tests/test_manifest_aligned_audio.py`. | `tests/` |

**Why subtitles stay aligned for free:** Track 5's subtitle scheduler already anchored to `scene.renderer.time` inside the renderer, which is the exact same source as `video_start_seconds` in the manifest. Once narration aligns with the renderer's clock, subtitles align with narration automatically.

### Track 7 — Shorts pipeline (May 2026)

Vertical 50-second 9:16 short for YouTube Shorts / Instagram Reels / TikTok generated alongside (or instead of) the long-form. Designed to drive cross-platform traffic to the long-form video.

| # | Feature | Modules |
|---|---|---|
| 19 | **Viral 4-scene prompt** — hard structure (HOOK 3-5s / TENSION 10-15s / PAYOFF 20-25s / CTA 5-7s), word-count ceilings, forbidden openers ("Today we'll learn", "In this video"). | `prompts/shorts.py:SHORTS_SYSTEM_PROMPT` |
| 20 | **Vertical action whitelist** — 11 actions safe on a 1080×1920 canvas. Anything else (topology, sequence, comparisons, tables, charts, cloud, layer stacks) stripped before Pydantic validation so the LLM cannot violate the layout invariant. | `prompts/shorts.py:VERTICAL_ACTION_WHITELIST` |
| 21 | **Shorts orchestrator** — single LLM call distills topic into a `<=4`-scene `EnrichedVideoScript`. Cached under `shorts::<topic>` namespace so the short cache doesn't collide with the long-form cache. | `shorts_orchestrator.py` |
| 22 | **Vertical Manim runner** — `ShortsSemanticVideo` (MovingCameraScene) reshapes `manim.config.frame_width=8.0` and `frame_height=14.222` at module load. Forces `data["mode"] = "shorts"` so the construct skips intro/title/outro/header/decorations. | `rendering_engine/shorts_runner.py` |
| 23 | **Shorts render entrypoint** — `render_shorts_video()` invokes Manim with `-r 1080,1920 --fps 30`, copies the manifest. | `rendering_engine/engine.py:render_shorts_video` |
| 24 | **Shared construct, two modes** — `run_full_video_construct` reads `data["mode"]`; in `"shorts"` skips the chrome that would burn ~9s of the 50s budget. Single function, two pipelines. | `rendering_engine/full_video_scene.py` |
| 25 | **Platform-named output copies** — `youtube_short.mp4`, `instagram_reel.mp4`, `tiktok.mp4` — same content, renamed for upload convenience. Gated by `SHORTS_EMIT_PLATFORM_COPIES`. | `main.py:run_shorts_pipeline` |
| 26 | **CLI flags** — `--shorts` (long-form + short) and `--shorts-only` (skip long-form). | `main.py` |
| 27 | **Inherits Tracks 5+6 for free** — whisper-aligned subtitles, manifest-driven audio mux, theme system, ambient particles, selective music — all unchanged for shorts. Only the prompt and the camera frame differ. | (everywhere) |

### Test count

148 tests at end of Track 6 → **158 tests at end of Track 7**, all passing in ~1.5 s.

### Schema additions (since v3.0)

`EnrichedScene`:
- `whisper_words: list[dict]` — Whisper word-level timestamps populated after TTS

`scene_timings.json` (new artifact, not part of Pydantic schema):
- `intro_card_end_seconds`, `title_card_end_seconds`, `outro_start_seconds`, `outro_end_seconds`, `total_video_duration`
- `scenes: [{scene_id, video_start_seconds, video_end_seconds, audio_duration, pause_after}, …]`

### New env flags (since v3.0)

```bash
# AV alignment
ENABLE_SUBTITLE_ALIGNMENT=True

# Visual polish
ENABLE_AMBIENT_DECOR=True            AMBIENT_DECOR_COUNT=6
ENABLE_BACKGROUND_PARTICLES=True     BACKGROUND_PARTICLE_COUNT=22
ENABLE_ISOMETRIC_SHADOW=True
ENABLE_KEYWORD_BURST=False           # disabled by user feedback
ENABLE_3D_TOPOLOGY=True              # default flipped from False
ENABLE_REMOTION_CHROME=False         # default flipped — Manim already handles intro/outro

# Music
MUSIC_VOLUME_DB=-36                  # was -28
MUSIC_PLAYBACK_MODE=selective        # selective | continuous | off
MUSIC_HIGHLIGHT_MOODS=tense          # comma-separated music_mood values
MUSIC_INCLUDE_INTRO_OUTRO_BEDS=True

# YouTube bridge
ENABLE_YOUTUBE_UPLOAD_EXPORT=True

# Shorts
ENABLE_SHORTS=False                  # opt-in via CLI flag
SHORTS_TARGET_DURATION=50.0
SHORTS_EMIT_PLATFORM_COPIES=True
```

---

## v3.0 — Engagement Upgrade (Apr 2026)

Goes from "polished retention-focused explainer" to "broadcast-grade YouTube educational channel" — adds AI vision QA, branding chrome, multi-voice + multi-language, AI imagery, real D3 charts, pattern interrupts, and full distribution automation. **All features are opt-in via env flags and degrade gracefully when dependencies are missing.**

### Phase 1 — Quick Wins (in-engine)

| # | Feature | Modules |
|---|---|---|
| 1 | **GPT-4o vision QA loop** — sample silent video frames every N seconds, ask GPT-4o vision for blank/overlap/cutoff/illegibility issues, write `vision_qa.json` report | `vision_qa.py` |
| 2 | **Disk caching layer** — TTS audio + LLM scripts + translations + B-roll cached by content hash via `diskcache` (≈10× faster iteration) | `caching.py`, `tts_generator.py`, `llm_orchestrator_semantic.py` |
| 3 | **Channel branding** — animated intro card, outro Subscribe CTA, persistent corner watermark anchored to camera frame | `rendering_engine/branding.py` |
| 4 | **Per-category visual themes** — full color palettes (bg gradient + primary + secondary + accent) per category, animated vertical gradient background | `rendering_engine/themes.py` |
| 5 | **Whisper kinetic typography** — word-level audio alignment via OpenAI Whisper, karaoke-style subtitles with per-word reveal/highlight | `whisper_align.py`, `rendering_engine/subtitles.py` |
| 6 | **Multi-voice TTS** — per-scene `voice_mood` (`narrator`, `excited`, `dramatic`, `calm`, `analytical`, `urgent`, `hook`) drives OpenAI/ElevenLabs voice swap with heuristic fallback | `voice_moods.py`, `tts_generator.py` |
| 7 | **Mood-matched background music** — per-scene `music_mood` swaps/crossfades looped tracks dynamically | `semantic_audio.py` |
| 8 | **Easing curves + parallax** — `cubic_ease_in_out` / `back_ease_out`, slow camera drift on title card and persistent topology scenes | `rendering_engine/easing.py`, `full_video_scene.py` |

### Phase 2 — Hybrid Stack & AI Visuals

| # | Feature | Modules |
|---|---|---|
| 9 | **AI-generated B-roll** — `show_image` action; DALL-E 3 generates topical illustrations, optional `rembg` background removal, Manim renders Ken Burns pan/zoom | `broll_generator.py`, `rendering_engine/broll.py` |
| 10 | **Remotion chrome layer** — Node/React project for broadcast-quality intro / outro / lower-thirds; ffmpeg concats around the Manim core | `chrome/` (Node), `chrome_compositor.py` |
| 11 | **Real D3 charts** — `show_chart` action renders true SVG bar/line/donut charts in headless Chromium via Playwright, screencaps to PNG, displays in Manim | `charts/renderer.py`, `rendering_engine/charts.py` |
| 12 | **Pattern-interrupt effects** — `flash_cut`, `zoom_punch`, `glitch_transition` actions; auto-injected every `PATTERN_INTERRUPT_INTERVAL` seconds via `retention.py` | `rendering_engine/effects.py`, `retention.py` |
| 13 | **Pseudo-3D topology** — depth shading + slow orbit drift on tree/mesh layouts when `ENABLE_3D_TOPOLOGY=true` | `rendering_engine/topology_3d.py` |

### Phase 3 — Distribution & Scale

| # | Feature | Modules |
|---|---|---|
| 14 | **YouTube auto-upload** — Google Data API v3 OAuth flow, resumable upload, auto-chapters from scene durations, custom thumbnail upload, SEO tags + description | `youtube_uploader.py` |
| 15 | **Auto-thumbnail generator** — 1280×720 Pillow composite (themed gradient or DALL-E AI background, bold drop-shadow title, accent stripe, channel watermark) | `thumbnail_generator.py` |
| 16 | **Multi-language dubs** — translate narration with GPT-4o, re-run TTS per language, remux silent video → `final_<lang>.mp4` (cached translations + audio) | `dubs.py` |
| 17 | **Streamlit preview dashboard** — generate / pick / edit a run, fast TTS-only re-render via cache, full Manim re-render, inline preview of video + thumbnail + dubs + vision-QA report | `dashboard/app.py` |

### Schema additions

`SemanticVideoScript` / `EnrichedVideoScript`:

- `suggested_youtube_tags: list[str]` — SEO tags for upload
- `suggested_youtube_description: str` — opening 2-3 sentences (chapters appended automatically)

`SemanticScene` / `EnrichedScene`:

- `voice_mood: str` — drives per-scene TTS voice
- `music_mood: str` — drives background-music swap
- `image_prompt: str` — DALL-E prompt for B-roll

New action models in `models_semantic.py`: `ShowImage`, `ShowChart`, `FlashCut`, `ZoomPunch`, `GlitchTransition`.

### New env flags (defaults shown)

```bash
# Vision QA
ENABLE_VISION_QA=false           # GPT-4o-vision frame QA after render
VISION_QA_SAMPLE_SECONDS=8
VISION_QA_MODEL=gpt-4o

# Caching
ENABLE_CACHE=true                # diskcache for TTS, LLM, translations, B-roll

# Branding
ENABLE_BRANDING=true
ENABLE_INTRO_CARD=true
ENABLE_OUTRO_CARD=true
ENABLE_WATERMARK=true
CHANNEL_NAME=CoreDuation
CHANNEL_TAGLINE="Engineering, explained."

# Themes
ENABLE_THEMED_BACKGROUNDS=true
ENABLE_GRADIENT_BACKGROUND=true

# Kinetic typography
ENABLE_KINETIC_SUBTITLES=false   # requires openai-whisper

# Multi-voice TTS
ENABLE_MULTI_VOICE=true

# Mood music
ENABLE_MOOD_MUSIC=true

# Easing & parallax
ENABLE_PARALLAX=true

# Pattern interrupts
ENABLE_PATTERN_INTERRUPTS=true
PATTERN_INTERRUPT_INTERVAL=35

# Remotion chrome (requires `cd chrome && npm install`)
ENABLE_REMOTION_CHROME=false
REMOTION_INTRO_DURATION=3.0
REMOTION_OUTRO_DURATION=4.0

# AI B-roll
ENABLE_AI_BROLL=false
BROLL_IMAGE_MODEL=dall-e-3

# 3D topology
ENABLE_3D_TOPOLOGY=false

# YouTube upload (requires client_secret.json + youtube_token.json)
ENABLE_YOUTUBE_UPLOAD=false
YOUTUBE_PRIVACY_STATUS=private   # private | unlisted | public
YOUTUBE_CATEGORY_ID=27           # 27 = Education

# Thumbnails
ENABLE_THUMBNAIL_GEN=true
THUMBNAIL_USE_AI_BG=false

# Dubs
ENABLE_DUBS=false
DUB_LANGUAGES=                   # comma-separated, e.g. "es,hi,fr"
OPENAI_TRANSLATION_MODEL=gpt-4o
```

### New dependencies (all optional / fail-soft)

```text
diskcache              # caching
openai-whisper         # kinetic subtitles
pillow                 # thumbnails
rembg                  # B-roll bg removal
playwright             # D3 chart rendering (run `playwright install chromium` once)
google-api-python-client / google-auth-httplib2 / google-auth-oauthlib  # YouTube upload
streamlit              # preview dashboard
```

### Pipeline flow (updated)

```
Topic
  └── LLM script (cached)
        └── Repair / Validate / Retention beats / Pattern-interrupt injection
              └── Voice-mood annotation
                    └── TTS per scene (multi-voice, cached)
                          └── Audio mux (mood-matched music + SFX)
                                └── Manim render (themed bg + branding + parallax + Whisper subtitles)
                                      └── Vision QA (GPT-4o)
                                            └── Mux audio + Remotion chrome concat
                                                  └── Thumbnail (Pillow / DALL-E)
                                                        └── Multi-language dubs
                                                              └── YouTube upload (chapters + SEO + thumbnail)
```

The Streamlit dashboard (`streamlit run dashboard/app.py`) provides a UI over every step — pick a run, edit narration / mood / B-roll prompt, hit *Re-render TTS only* (cache-fast) or *Re-render full video*, preview the final MP4 + thumbnail + QA report.

---

## v2.0 — Retention Upgrade (Apr 2026)

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
