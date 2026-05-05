# CoreDuation — Repo Guide for Claude

AI-driven educational video pipeline. An LLM emits a structured action JSON; a deterministic Manim renderer turns it into a polished MP4 with TTS narration, SFX, mood-matched music, branding, and (optionally) chrome, dubs, and YouTube upload.

## Two pipelines (same `main.py`)

| Engine | Flow | Status |
|---|---|---|
| `--engine legacy` | LLM → raw Manim code → `error_healer` → per-scene render → `video_stitcher` | Maintained but not the focus |
| `--engine semantic` | LLM → action JSON → `semantic_repair` → `semantic_validation` → TTS → whisper-align → render silent video → manifest-aligned audio mux → frame validator → auto-fix → vision QA → final mux → thumbnail → YouTube export → dubs → YouTube upload | **Active** (`semantic-engine-v9`) |
| `--shorts` / `--shorts-only` | Same long-form pipeline (when not `-only`), then: `shorts_orchestrator` distills topic → 4-scene viral script → TTS → whisper-align → vertical 1080×1920 render → manifest-aligned audio → mux → platform-named copies | Active alongside long-form |

Run:
```
python main.py --topic "TCP three-way handshake" --engine semantic --category networking
python main.py --topic "TLS Handshake" --category security --shorts          # long + short
python main.py --topic "TLS Handshake" --category security --shorts-only     # short only
```

## Semantic pipeline at a glance

1. **Script** — `llm_orchestrator_semantic.generate_semantic_script()` calls OpenAI with the matching specialty system prompt, sanitizes hallucinated action types, returns an `EnrichedVideoScript`. Cached via `caching.cached_llm_script`.
2. **Repair + validate** — `semantic_repair.repair_duplicate_ids()` then `semantic_validation.validate_semantic_script()`. Validation hard-fails on unknown ids in core actions (packets/topology) but only warns for retention actions (pulse/shake/dim/callout).
3. **Retention enrichment** — `retention.ensure_retention_beats()` injects pulse/focus/shake when a scene exceeds `MAX_IDLE_VISUAL_SECONDS`.
4. **TTS** — `tts_generator.generate_speech()` per scene; voice swapped by `scene.voice_mood`, speed by `scene.narration_pace`. OpenAI or ElevenLabs. Cached on `(text, voice, model, speed)` — **speed is part of the key, do not drop it**.
5. **Density check** — `narration_processor.validate_narration_density()` warns on >145 WPM scenes.
6. **Whisper alignment** — `whisper_align.align_words()` runs per scene when `ENABLE_SUBTITLE_ALIGNMENT` is on; populates `scene.whisper_words` so subtitle chunks anchor to real spoken-word timestamps in the rendering engine. Cached by audio hash.
7. **Render** — `rendering_engine.engine.render_full_semantic_video()` invokes Manim on a single Scene class (`rendering_engine.full_video_scene`) that processes every scene with cross-scene object persistence. The runner applies themed gradient + drifting particles + ambient margin decor before scene playback. Subtitles are scheduled per-scene via updaters that toggle visibility against `(scene.renderer.time - scene_start)`, so chunks track audio progression instead of post-action wait. **The renderer writes `scene_timings.json`** capturing each scene's actual `video_start_seconds` and `video_end_seconds` — this is the single source of truth for AV alignment.
8. **Audio mux** — `semantic_audio.build_narration_track_from_manifest()` overlays each scene's TTS mp3 at exactly its `video_start_seconds` from the manifest. Total length matches the silent video by construction; no `_pad_audio_to_video` band-aid needed. SFX positioned at `video_start + (action_idx/n_actions) * audio_duration`. Music in selective mode (default) plays only during intro/outro stings + scenes whose `music_mood` is in `MUSIC_HIGHLIGHT_MOODS` (default: `tense`); volume default `-36 dB`. Falls back to legacy cumulative-estimate `build_semantic_narration_track()` only if the manifest is missing.
9. **Post** — `frame_validator` (deterministic per-scene frame sampling), `auto_fix` (retry loop for QA failures), `vision_qa` (GPT-4o frame sampling), `chrome_compositor` (Remotion intro/outro — **disabled by default**, since Manim already renders intro+title+outro inside `final_semantic.mp4`), `thumbnail_generator`, `youtube_upload_export` (copies output into `Youtube_Upload/videos/` for the standalone uploader), `dubs.generate_language_dubs`, `youtube_uploader`.

## Shorts pipeline (Track 7)

A parallel pipeline produces 50-second vertical 9:16 videos for YouTube Shorts / Instagram Reels / TikTok using the **same** audio mux, manifest, subtitle scheduler, and theme system. Differences:

- `shorts_orchestrator.generate_shorts_script()` — single LLM call distills the topic into a 4-scene viral script (hook → tension → payoff → CTA) using `prompts/shorts.py:SHORTS_SYSTEM_PROMPT`. Hard-strips actions outside `VERTICAL_ACTION_WHITELIST` (no topology, no comparisons, no charts — anything assuming horizontal width).
- `rendering_engine/shorts_runner.py` — Manim Scene that reshapes `manim.config.frame_width=8.0` and `frame_height=14.222` at module load, before `MovingCameraScene` instantiates.
- `rendering_engine/engine.render_shorts_video()` — passes `-r 1080,1920 --fps 30` to Manim CLI.
- `data["mode"] = "shorts"` is read by `run_full_video_construct` to skip intro card, title card, outro card, persistent topic header, credit label, and corner decorations (would burn ~9s of the 50s budget).
- Output: `output/<run>/shorts/short.mp4` plus identical platform-named copies (`youtube_short.mp4`, `instagram_reel.mp4`, `tiktok.mp4`) when `SHORTS_EMIT_PLATFORM_COPIES=true`.

Output lands in `output/<YYYYMMDD_HHMMSS>_semantic_<slug>/`.

## Layout

```
main.py                        Pipeline orchestrator + CLI (--shorts, --shorts-only)
config.py                      All env-var flags with safe defaults — touch this when adding a feature flag
models_semantic.py             Pydantic action vocabulary (CreateNode, SendPacket, ShowTable, PulseElement, ...)
llm_orchestrator_semantic.py   Long-form script generation
shorts_orchestrator.py         Vertical 4-scene shorts script generation (viral hook → tension → payoff → CTA)
semantic_repair.py             Globally unique ids
semantic_validation.py         Action legality, implicit connection ids
semantic_audio.py              Manifest-driven narration mux + SFX + selective music (Track 6)
tts_generator.py               OpenAI / ElevenLabs TTS, voice + speed resolution
narration_processor.py         WPM density warnings, closing-CTA scrubbing
retention.py                   Idle-scene enrichment (auto-inject visual beats)
voice_moods.py                 mood → voice id mapping
caching.py                     diskcache wrapper (TTS / LLM scripts / generic JSON+bytes)
vision_qa.py                   GPT-4o frame audit
frame_validator.py             Deterministic per-scene frame sampling for QA gates
auto_fix.py                    Retry loop that re-renders scenes failing frame validation
whisper_align.py               OpenAI Whisper word-level timestamps for subtitle alignment
thumbnail_generator.py         Pillow / DALL-E composite (1280×720)
dubs.py                        Translation + per-language re-TTS + remux
chrome_compositor.py           ffmpeg concat with Remotion intro/outro (disabled by default)
youtube_uploader.py            OAuth resumable upload + auto-chapters
youtube_upload_export.py       Bridge: copies pipeline output into Youtube_Upload/videos/ for the standalone uploader

prompts/
  _base.py                     SpecialtyPrompt dataclass + RETENTION_STRATEGY + NARRATION_HUMANIZATION + ACTION_VOCABULARY
  <category>.py                Per-domain persona, structure, examples (networking/databases/programming/...)
  shorts.py                    Viral 4-scene vertical prompt + VERTICAL_ACTION_WHITELIST

rendering_engine/
  engine.py                    SceneState + action dispatch + render_full_semantic_video + render_shorts_video
  full_video_scene.py          Per-scene render loop. Reads data["mode"] ("long"/"shorts") and writes scene_timings.json manifest.
  full_video_runner.py         Long-form 16:9 Manim subprocess entrypoint (FullSemanticVideo)
  shorts_runner.py             Vertical 9:16 Manim subprocess entrypoint (ShortsSemanticVideo, frame 8.0×14.222)
  styles.py                    Single source of truth for colors / fonts / timings / paddings + make_isometric_shadow
  presentation.py              Text blocks, bullet lists, code blocks, comparisons (with `_avoid_collision` two-state rule)
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

tests/
  test_spatial_registry.py            BBox, SceneState, parent/child containment
  test_retention_upgrade.py           Action parsing, validation, subtitle chunking, sample script load
  test_layout_zones.py                Zone-based collision detection
  test_action_sanitization.py         Long-form action whitelist
  test_narration_processor.py         WPM warnings, CTA scrubbing
  test_semantic_audio_pauses.py       Legacy cumulative-builder pause math
  test_manifest_aligned_audio.py      AV-sync invariant: manifest-driven narration placement
  test_shorts_orchestrator.py         Vertical action whitelist + 4-scene cap + canvas reshape
  test_frame_validator.py             Deterministic per-scene frame sampling
  test_auto_fix.py                    Retry-loop fix collection
```

Run: `pytest tests/ -q` — 158 tests, all passing as of Track 7.

## Conventions

- **Visual constants live in `rendering_engine/styles.py`** — never hardcode a color, font size, padding, or pause duration in renderers. Add a constant.
- **Env flags live in `config.py`** — every new feature gets an `ENABLE_X` flag with a safe default and graceful fallback. Pipelines must not crash when an optional dep is missing.
- **Cache keys are content-hashes**. When a new input affects output (e.g. `speed` for TTS), it must be in the key — bump the namespace tag (`tts-v1` → `tts-v2`) to invalidate.
- **Action vocabulary is closed**. To add an action: define a Pydantic model in `models_semantic.py`, register a renderer in `rendering_engine/engine.py`'s dispatch table, document it in `prompts/_base.py:ACTION_VOCABULARY`. Validation in `semantic_validation.py` controls whether unknown ids hard-fail or warn.
- **Specialty prompts are dataclasses** (`prompts/_base.py:SpecialtyPrompt`). Each category overrides persona / structure / preferred actions / example scene. Auto-detection lives in `prompts/__init__.py`.
- **Tests are pytest** under `tests/`. Run: `pytest tests/ -q`. They use mock mobjects (no Manim runtime needed) and Pydantic adapters for action parsing.

## Active branch

`semantic-engine-v9`. Track history (most recent first):

- **Track 7 — Shorts pipeline** (vertical 9:16 for YT Shorts / IG Reels / TikTok). New `--shorts` and `--shorts-only` CLI flags. Reuses Tracks 5/6 infrastructure; only the prompt + camera frame differ.
- **Track 6 — Manifest-driven AV alignment**. The renderer writes `scene_timings.json`; audio mux places each scene's TTS at its actual `video_start_seconds`. Eliminates the chronic ~17s drift that accumulated when action animations overshot their declared budget. See `feedback_av_sync_drift.md` in memory for the diagnosis and why "tuning" doesn't fix it.
- **Track 5 — Whisper-aligned subtitles + ambient visuals + YouTube bridge + selective music**. Per-scene word timestamps drive scheduled subtitle mobjects with time-based opacity updaters; drifting particle field, margin decor, isometric shadows; pipeline output auto-copied to `Youtube_Upload/videos/`; OAuth dual-path search; music narrowed to `tense`-mood scenes plus intro/outro stings at -36 dB.
- **Track 4 — Frame validator + auto-fix + scene QA**. Deterministic per-scene frame sampling, retry loop for QA failures, GPT-4o structured-output per-scene audit.
- **Track 3 — Storytelling**: hooks, key_phrase, mini-drama, real final takeaway.
- **Track 2 — Visual polish**: ghost-free titles, semantic colors, smarter persistent toggle.
- **Track 1 — Layout engine + narration polish**: zones, collision avoidance, validators.

Visual rules (from user feedback, captured in memory):
- Full diagram OR text — never "diagram + text awkwardly stacked". `_avoid_collision` in `presentation.py` either relocates text to a vacant region or hides the topology entirely; both paths wrap the result in a card with isometric shadow.
- Music is accent, not score. Selective playback default; `tense_loop.mp3` only on hook scenes; `MUSIC_VOLUME_DB=-36`.
- Background continuous score "irritates" — opt into `MUSIC_PLAYBACK_MODE=continuous` only when explicitly desired.

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
