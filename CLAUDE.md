# CoreDuation — Repo Guide for Claude

AI-driven educational video pipeline. An LLM emits a structured action JSON; a deterministic Manim renderer turns it into a polished MP4 with TTS narration, SFX, mood-matched music, branding, and (optionally) chrome, dubs, and YouTube upload.

## Two pipelines (same `main.py`)

| Engine | Flow | Status |
|---|---|---|
| `--engine legacy` | LLM → raw Manim code → `error_healer` → per-scene render → `video_stitcher` | Maintained but not the focus |
| `--engine semantic` | LLM → action JSON → `semantic_repair` → `semantic_validation` → TTS → whisper-align → `semantic_audio` → single Manim Scene → frame validator → auto-fix → vision QA → mux → chrome → thumbnail → YouTube export → dubs → YouTube upload | **Active** (`semantic-engine-v8`) |

Run: `python main.py --topic "TCP three-way handshake" --engine semantic --category networking`

## Semantic pipeline at a glance

1. **Script** — `llm_orchestrator_semantic.generate_semantic_script()` calls OpenAI with the matching specialty system prompt, sanitizes hallucinated action types, returns an `EnrichedVideoScript`. Cached via `caching.cached_llm_script`.
2. **Repair + validate** — `semantic_repair.repair_duplicate_ids()` then `semantic_validation.validate_semantic_script()`. Validation hard-fails on unknown ids in core actions (packets/topology) but only warns for retention actions (pulse/shake/dim/callout).
3. **Retention enrichment** — `retention.ensure_retention_beats()` injects pulse/focus/shake when a scene exceeds `MAX_IDLE_VISUAL_SECONDS`.
4. **TTS** — `tts_generator.generate_speech()` per scene; voice swapped by `scene.voice_mood`, speed by `scene.narration_pace`. OpenAI or ElevenLabs. Cached on `(text, voice, model, speed)` — **speed is part of the key, do not drop it**.
5. **Density check** — `narration_processor.validate_narration_density()` warns on >145 WPM scenes.
6. **Whisper alignment** — `whisper_align.align_words()` runs per scene when `ENABLE_SUBTITLE_ALIGNMENT` is on; populates `scene.whisper_words` so subtitle chunks anchor to real spoken-word timestamps in the rendering engine. Cached by audio hash.
7. **Audio mux** — `semantic_audio.build_semantic_narration_track()` concatenates per-scene MP3s, inserts `SCENE_GAP_SECONDS + scene.pause_after` of silence between scenes, overlays SFX (keyed by action type) and mood-matched background music (per-scene swap allowed).
8. **Render** — `rendering_engine.engine.render_full_semantic_video()` invokes Manim on a single Scene class (`rendering_engine.full_video_scene`) that processes every scene with cross-scene object persistence. The runner applies themed gradient + drifting particles + ambient margin decor before scene playback. Subtitles are scheduled per-scene via updaters that toggle visibility against `(scene.renderer.time - scene_start)`, so chunks track audio progression instead of post-action wait.
9. **Post** — `frame_validator` (deterministic per-scene frame sampling), `auto_fix` (retry loop for QA failures), `vision_qa` (GPT-4o frame sampling), `chrome_compositor` (Remotion intro/outro — **disabled by default**, since Manim already renders intro+title+outro inside `final_semantic.mp4`), `thumbnail_generator`, `youtube_upload_export` (copies output into `Youtube_Upload/videos/` for the standalone uploader), `dubs.generate_language_dubs`, `youtube_uploader`.

Output lands in `output/<YYYYMMDD_HHMMSS>_semantic_<slug>/`.

## Layout

```
main.py                        Pipeline orchestrator + CLI
config.py                      All env-var flags with safe defaults — touch this when adding a feature flag
models_semantic.py             Pydantic action vocabulary (CreateNode, SendPacket, ShowTable, PulseElement, ...)
llm_orchestrator_semantic.py   Script generation
semantic_repair.py             Globally unique ids
semantic_validation.py         Action legality, implicit connection ids
semantic_audio.py              Narration + SFX + music mux (pause_after-aware)
tts_generator.py               OpenAI / ElevenLabs TTS, voice + speed resolution
narration_processor.py         WPM density warnings
retention.py                   Idle-scene enrichment (auto-inject visual beats)
voice_moods.py                 mood → voice id mapping
caching.py                     diskcache wrapper (TTS / LLM scripts / generic JSON+bytes)
vision_qa.py                   GPT-4o frame audit
thumbnail_generator.py         Pillow / DALL-E composite (1280×720)
dubs.py                        Translation + per-language re-TTS + remux
chrome_compositor.py           ffmpeg concat with Remotion intro/outro
youtube_uploader.py            OAuth resumable upload + auto-chapters

prompts/
  _base.py                     SpecialtyPrompt dataclass + RETENTION_STRATEGY + NARRATION_HUMANIZATION + ACTION_VOCABULARY
  <category>.py                Per-domain persona, structure, examples (networking/databases/programming/...)

rendering_engine/
  engine.py                    SceneState (spatial registry, BBox, find_vacant_rect), action dispatch, run entrypoint
  full_video_scene.py          Manim Scene class — per-scene render loop, fade timing, subtitles
  full_video_runner.py         Subprocess Manim invoker
  styles.py                    Single source of truth for colors / fonts / timings / paddings
  presentation.py              Text blocks, bullet lists, code blocks, comparisons
  topology.py / topology_3d.py Network diagrams (star/mesh/ring/bus/tree)
  cloud.py                     AWS/GCP/Azure regions + services
  charts.py                    D3 → Playwright → PNG
  packets.py                   Packet animations
  sequence.py                  Sequence diagrams
  data_display.py              Tables
  subtitles.py                 Whisper-aligned scheduled subtitles + chunked fallback (`schedule_subtitles_for_scene`)
  branding.py                  Intro/outro/watermark + persistent "Created by Human & AI" credit label
  themes.py                    Per-category palettes + animated gradient + drifting particle field
  ambient.py                   Margin-zone drifting decor shapes (stars/polygons/circles, z=-60)
  keyword_overlay.py           Large faint background watermark word — **DISABLED** (`ENABLE_KEYWORD_BURST=False`); competes with content
  effects.py                   Pattern-interrupt cuts
  easing.py                    Cubic / back / anticipation easing
  broll.py                     DALL-E + Ken Burns
  retention.py                 Beat injection
  charts/ chrome/ dashboard/ assets/    Helper subprojects (D3, Remotion, Streamlit, audio assets)

frame_validator.py             Deterministic per-scene frame sampling for QA gates
auto_fix.py                    Retry loop that re-renders scenes failing frame validation
whisper_align.py               OpenAI Whisper word-level timestamps for subtitle alignment
youtube_upload_export.py       Bridge: copies pipeline output into Youtube_Upload/videos/ as stitched_video_set_<N>.{mp4,txt,png}

tests/
  test_spatial_registry.py     BBox, SceneState, parent/child containment
  test_retention_upgrade.py    New action parsing, validation, subtitle chunking, sample script load
```

## Conventions

- **Visual constants live in `rendering_engine/styles.py`** — never hardcode a color, font size, padding, or pause duration in renderers. Add a constant.
- **Env flags live in `config.py`** — every new feature gets an `ENABLE_X` flag with a safe default and graceful fallback. Pipelines must not crash when an optional dep is missing.
- **Cache keys are content-hashes**. When a new input affects output (e.g. `speed` for TTS), it must be in the key — bump the namespace tag (`tts-v1` → `tts-v2`) to invalidate.
- **Action vocabulary is closed**. To add an action: define a Pydantic model in `models_semantic.py`, register a renderer in `rendering_engine/engine.py`'s dispatch table, document it in `prompts/_base.py:ACTION_VOCABULARY`. Validation in `semantic_validation.py` controls whether unknown ids hard-fail or warn.
- **Specialty prompts are dataclasses** (`prompts/_base.py:SpecialtyPrompt`). Each category overrides persona / structure / preferred actions / example scene. Auto-detection lives in `prompts/__init__.py`.
- **Tests are pytest** under `tests/`. Run: `pytest tests/ -q`. They use mock mobjects (no Manim runtime needed) and Pydantic adapters for action parsing.

## Active branch

`semantic-engine-v8` — last shipped (Track 5):
- Whisper-aligned subtitles: per-scene word timestamps drive scheduled subtitle mobjects with time-based opacity updaters; subtitle chunks now follow narration audio progression, not post-action wait.
- Ambient visuals: drifting particle field (themes), margin-zone decor shapes (ambient.py), isometric drop-shadows on cards/topology (`make_isometric_shadow`), persistent top-left credit label, always-on topic header.
- YouTube export bridge: pipeline outputs auto-copied into `Youtube_Upload/videos/` so the existing standalone uploader picks them up unchanged.
- OAuth multi-path: in-pipeline uploader now searches both root and `Youtube_Upload/` for `client_secret(s).json` and reuses cached `token.pickle` from the standalone uploader.
- Track 4: per-scene frame validator + auto-fix retry loop + structured-output QA.

Visual rule (per user feedback): full diagram OR text — never "diagram + text awkwardly stacked". `_avoid_collision` in `presentation.py` either relocates text to a vacant region or hides the topology entirely; both paths wrap the result in a card with isometric shadow.

## Running

```bash
# Tests
pytest tests/ -q

# Pipeline
python main.py --topic "TCP three-way handshake" --engine semantic --category networking

# Dashboard preview UI
streamlit run dashboard/app.py
```

Required: `OPENAI_API_KEY`. Optional: `ELEVENLABS_API_KEY`, Google OAuth credentials for YouTube. See `.env.example`.
