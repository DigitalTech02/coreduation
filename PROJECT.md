# CoreDuation — AI Video Generation Pipeline

An automated pipeline that turns any educational topic into a fully narrated, animated video — long-form (16:9) for YouTube and a matching vertical short (9:16) for YouTube Shorts, Instagram Reels, and TikTok.

## How It Works

```
Topic (CLI)
    │
    ▼
┌─────────────────────────────────┐
│ 1. Category detection (auto)    │  Fast LLM call classifies into 1 of 8 domains
└─────────────────┬───────────────┘
                  │
                  ▼
┌─────────────────────────────────┐
│ 2. Long-form script (semantic   │  Domain-specific prompt + GPT-4.1 → JSON
│    JSON, 10–18 scenes)          │  actions, retention beats injected
└─────────────────┬───────────────┘
                  │
                  ▼
┌─────────────────────────────────┐
│ 3. TTS per scene (multi-voice)  │  OpenAI / ElevenLabs, voice swapped by mood
└─────────────────┬───────────────┘
                  │
                  ▼
┌─────────────────────────────────┐
│ 4. Whisper word-level alignment │  scene.whisper_words drives subtitle timing
└─────────────────┬───────────────┘
                  │
                  ▼
┌─────────────────────────────────┐
│ 5. Manim render (single Scene)  │  Writes scene_timings.json manifest with
│                                 │  per-scene actual video_start_seconds.
└─────────────────┬───────────────┘
                  │
                  ▼
┌─────────────────────────────────┐
│ 6. Manifest-aligned audio mux   │  Track 6: TTS placed at actual video times
│    (narration + SFX + music)    │  → AV cannot drift across scenes
└─────────────────┬───────────────┘
                  │
                  ▼
┌─────────────────────────────────┐
│ 7. ffmpeg final mux             │  → final_semantic.mp4
└─────────────────┬───────────────┘
                  │
                  ▼ (optional)
┌─────────────────────────────────┐
│ 8. QA / thumbnail / dubs /      │  frame_validator → vision_qa → thumbnail
│    YouTube export / upload      │     → dubs → YouTube upload
└─────────────────┬───────────────┘
                  │
                  ▼ (with --shorts)
┌─────────────────────────────────┐
│ 9. Shorts pipeline (Track 7)    │  Distill topic → 4-scene viral script →
│                                 │  vertical render → manifest-aligned mux →
│                                 │  short.mp4 + youtube_short / instagram_reel /
│                                 │  tiktok.mp4 copies
└─────────────────────────────────┘
```

## Architecture

The pipeline uses a **"Semantic JSON + Deterministic Engine"** architecture. The LLM never writes code — it outputs structured JSON actions (e.g. `create_node`, `send_packet`, `show_table`), and a hand-written Python rendering engine translates those into Manim animations deterministically.

### Why this approach?

- **Zero code hallucinations** — the LLM only picks from a fixed action vocabulary
- **Stateful rendering** — objects persist across scenes (topology stays while packets fly)
- **Perfect layouts** — spatial math handled in Python, not guessed by the LLM
- **Timing-driven** — animations paced to match narration duration
- **AV-sync-by-construction** — renderer manifest is the single source of truth for scene boundaries; audio adapts to it

## Project Structure

```
coreduation/
├── main.py                        # CLI + pipeline orchestration (long-form + shorts)
├── llm_orchestrator_semantic.py   # Long-form LLM script generation
├── shorts_orchestrator.py         # Vertical 4-scene viral short generation
├── models_semantic.py             # Pydantic action models + EnrichedVideoScript / EnrichedScene
├── semantic_validation.py         # Pre-render validation (IDs, references)
├── semantic_repair.py             # Post-generation ID deduplication
├── semantic_audio.py              # Manifest-driven audio mux + SFX + selective music
├── tts_generator.py               # OpenAI / ElevenLabs TTS
├── whisper_align.py               # Whisper word-level timestamp extraction
├── narration_processor.py         # WPM warnings, CTA scrubbing
├── retention.py                   # Idle-scene visual beat injection
├── voice_moods.py                 # mood → voice id mapping
├── caching.py                     # diskcache wrapper
├── frame_validator.py             # Deterministic per-scene frame QA
├── auto_fix.py                    # Retry loop for failed scenes
├── vision_qa.py                   # GPT-4o frame audit
├── thumbnail_generator.py         # 1280×720 Pillow / DALL-E
├── dubs.py                        # Translation + per-language re-TTS + remux
├── chrome_compositor.py           # Remotion intro/outro concat (off by default)
├── youtube_uploader.py            # In-pipeline OAuth resumable upload
├── youtube_upload_export.py       # Bridge to Youtube_Upload/videos/ folder
│
├── prompts/                       # Specialty + shorts prompt registry
│   ├── _base.py                   # SpecialtyPrompt dataclass + RETENTION_STRATEGY + ACTION_VOCABULARY
│   ├── shorts.py                  # Viral 4-scene vertical prompt + VERTICAL_ACTION_WHITELIST
│   ├── networking.py              # Networking & protocols
│   ├── data_structures.py         # DSA & algorithms
│   ├── programming.py             # Programming concepts
│   ├── cloud_architecture.py      # Cloud & infrastructure
│   ├── system_design.py           # System design interviews
│   ├── business_analysis.py       # Business frameworks
│   ├── databases.py               # Database engineering
│   └── security.py                # Cybersecurity & protocols
│
├── rendering_engine/              # Deterministic Manim rendering
│   ├── engine.py                  # SceneState + dispatch + render_full_semantic_video / render_shorts_video
│   ├── full_video_scene.py        # Per-scene loop, writes scene_timings.json, reads data["mode"]
│   ├── full_video_runner.py       # Long-form 16:9 entrypoint (FullSemanticVideo)
│   ├── shorts_runner.py           # Vertical 9:16 entrypoint (ShortsSemanticVideo)
│   ├── styles.py                  # Colors, fonts, sizes, timings, paddings + make_isometric_shadow
│   ├── topology.py / topology_3d.py
│   ├── packets.py / sequence.py / data_display.py / cloud.py / charts.py
│   ├── presentation.py            # Text blocks, bullet lists, code, comparisons (with `_avoid_collision`)
│   ├── subtitles.py               # Whisper-aligned scheduled subtitles + chunked fallback
│   ├── branding.py                # Intro / outro / watermark / credit label
│   ├── themes.py                  # Per-category palettes + animated gradient + drifting particle field
│   ├── ambient.py                 # Margin-zone drifting decor shapes
│   ├── keyword_overlay.py         # Background watermark word — DISABLED (competes with content)
│   ├── effects.py                 # Pattern-interrupt cuts (flash_cut / zoom_punch / glitch_transition)
│   ├── easing.py                  # Cubic / back / anticipation easing
│   ├── broll.py                   # DALL-E + Ken Burns
│   └── retention.py               # Beat-injection renderers
│
├── tests/                         # 158 pytest tests (Track 7 baseline)
├── assets/                        # SFX + music files
├── chrome/                        # Optional Remotion (Node) intro/outro project
├── dashboard/                     # Streamlit preview UI
├── COMMANDS.md                    # CLI usage reference
├── PROJECT.md                     # This file
├── CHANGELOG.md                   # Track-by-track history
├── CLAUDE.md                      # Repo guide for Claude (project conventions + active branch)
├── requirements.txt
├── .env.example
└── .gitignore
```

## Visual Action Vocabulary (~36 types)

The LLM selects from this fixed vocabulary. The rendering engine handles all Manim code.

| Category | Actions |
|---|---|
| **Topology** | `create_node`, `create_connection`, `create_topology`, `update_node`, `remove_element` |
| **Packet flow** | `send_packet`, `send_broadcast` |
| **Sequence diagram** | `show_sequence_diagram` |
| **Data / protocol** | `show_layer_stack`, `show_header_breakdown`, `show_table`, `show_math` |
| **Presentation** | `show_text_block`, `show_code_block`, `show_comparison`, `show_bullet_list` |
| **Cloud** | `create_cloud_region`, `create_cloud_service`, `show_data_flow` |
| **Camera + retention** | `pulse_element`, `focus_camera`, `reset_camera`, `show_progress`, `update_progress`, `emphasize_text`, `shake_element`, `dim_except`, `restore_opacity`, `add_callout`, `scene_transition`, `show_image` |
| **Pattern interrupts** | `flash_cut`, `zoom_punch`, `glitch_transition` |
| **Charts** | `show_chart` (D3 → Playwright → PNG) |

The shorts pipeline restricts the LLM to a **vertical-friendly subset** (text blocks, bullet lists, emphasis, pattern interrupts, narrow code, B-roll images, scene transitions). Wide actions (topology, sequence, comparisons, tables, charts) are stripped before render to enforce the 9:16 layout.

## Specialty Prompt System

Each long-form domain has a dedicated prompt with persona / video structure / narration style / preferred actions / example scene / title-card subtitle.

### 8 Categories

| Category | Best For |
|---|---|
| `networking` | TCP, DNS, BGP, routing, protocols |
| `data-structures` | Arrays, trees, linked lists, hash maps, binary search |
| `programming` | Recursion, Big-O, design patterns, language concepts |
| `cloud-architecture` | AWS VPC, serverless, multi-region, CDN |
| `system-design` | URL shortener, chat system, load balancer design |
| `business-analysis` | SWOT, requirements gathering, use case modeling |
| `databases` | Normalization, B-tree indexes, ACID, SQL queries |
| `security` | TLS handshake, OAuth2, firewall rules, encryption |

The shorts pipeline uses a **single non-specialty prompt** (`prompts/shorts.py`). Shorts deliberately don't get domain-specific pedagogy — they're a single self-contained beat (hook → tension → payoff → CTA), not a structured lesson.

## Visual Effects

Applied automatically across every video:

- **Animated gradient backdrop** — slow hue drift behind every scene
- **Drifting particle field** — 22 dots scattered across the canvas with per-particle sin-wave drift (`ENABLE_BACKGROUND_PARTICLES`)
- **Margin-zone ambient decor** — slow-rotating stars/polygons/circles in the side strips outside the safe area (`ENABLE_AMBIENT_DECOR`)
- **Isometric drop shadows** — stacked dark offset copies behind cards/topology nodes (`make_isometric_shadow`)
- **Glow halos** on highlighted nodes
- **Per-category accent colors** on title cards
- **Whisper-aligned subtitles** — bold lower-third text, fade-in/out per chunk, anchored to actual spoken-word timestamps

## CLI Usage

```bash
# Long-form only (default)
python main.py --topic "TLS Handshake" --category security

# Long-form + matching vertical short
python main.py --topic "TLS Handshake" --category security --shorts

# Shorts only (skip long-form)
python main.py --topic "TLS Handshake" --category security --shorts-only

# Auto-detect category
python main.py --topic "How DNS Resolution Works"
```

### CLI Flags

| Flag | Default | Description |
|---|---|---|
| `--topic` | `"TCP Three-Way Handshake"` | The educational topic |
| `--engine` | `semantic` | `semantic` (recommended) or `legacy` |
| `--category` | `auto` | One of the 8 categories, or `auto` for LLM detection |
| `--shorts` | off | Also generate a 50s vertical short alongside the long-form |
| `--shorts-only` | off | Skip the long-form and only generate the short |

## Output

```
output/<YYYYMMDD_HHMMSS>_semantic_<slug>/
├── script.json                         # Full long-form semantic script
├── audio/<scene_id>.mp3                # Per-scene TTS
├── full_narration.mp3                  # Manifest-aligned combined narration
├── video/
│   ├── full_semantic_silent.mp4        # Silent Manim render
│   └── scene_timings.json              # Per-scene video_start_seconds (Track 6)
├── final_semantic.mp4                  # ← long-form 16:9 deliverable
├── thumbnail.jpg                       # 1280×720
├── frame_validation.json               # Track 4 deterministic QA report
├── vision_qa.json                      # (when ENABLE_VISION_QA=true)
└── shorts/                             # ← only when --shorts / --shorts-only
    ├── script.json                     # 4-scene viral script
    ├── audio/<scene_id>.mp3            # Per-scene TTS for the short
    ├── narration.mp3                   # Manifest-aligned short narration
    ├── video/
    │   ├── shorts_silent.mp4           # Silent vertical render
    │   └── scene_timings.json
    ├── short.mp4                       # ← canonical short
    ├── youtube_short.mp4               # Same content, renamed for upload
    ├── instagram_reel.mp4              # Same content
    └── tiktok.mp4                      # Same content
```

## Tech Stack

| Component | Library | Purpose |
|---|---|---|
| LLM | `openai` | GPT-4.1 for script generation, GPT-4o for vision QA, DALL-E 3 for thumbnails / B-roll |
| Data models | `pydantic` (>=2.10) | Strict schemas, discriminated unions |
| Animation | `manim` (>=0.20) | Manim Community Edition |
| TTS | `openai`, `elevenlabs` | Multi-voice |
| Word alignment | `openai-whisper` | Subtitle timing |
| Audio | `pydub`, `ffmpeg` | Mix + mux |
| Caching | `diskcache` | TTS / LLM scripts / translations |
| Charts | `playwright` (chromium) | D3 → SVG → PNG |
| Thumbnails | `pillow`, `rembg` (optional) | 1280×720 composite |
| Upload | `google-api-python-client`, `google-auth-oauthlib` | YouTube Data API v3 |
| Chrome (optional) | Remotion (Node) | Intro/outro polish (off by default) |
| Dashboard | `streamlit` | Preview / re-render UI |

### System Requirements

- **Python** 3.12+
- **ffmpeg** on PATH
- **LaTeX** (optional, for `MathTex`; gracefully falls back)
- **Node.js LTS** (only if using Remotion chrome)

## Environment Variables (selected)

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | Required for LLM, TTS, vision QA |
| `OPENAI_MODEL` | `gpt-4.1` | Override LLM model |
| `MANIM_QUALITY` | `m` | Long-form Manim quality flag (`l` / `m` / `h`) |
| `ENABLE_SUBTITLE_ALIGNMENT` | `True` | Whisper word-level alignment |
| `MUSIC_VOLUME_DB` | `-36` | Music volume relative to narration |
| `MUSIC_PLAYBACK_MODE` | `selective` | `selective` / `continuous` / `off` |
| `MUSIC_HIGHLIGHT_MOODS` | `tense` | Comma-separated `music_mood` values that get music |
| `MUSIC_INCLUDE_INTRO_OUTRO_BEDS` | `True` | Brief stings under intro / outro |
| `ENABLE_3D_TOPOLOGY` | `True` | Pseudo-3D depth shading |
| `ENABLE_ISOMETRIC_SHADOW` | `True` | Stacked drop shadows on cards |
| `ENABLE_REMOTION_CHROME` | `False` | Off — Manim already renders intro/outro |
| `ENABLE_VISION_QA` | `False` | GPT-4o frame audit (~$0.10–0.30/video) |
| `ENABLE_THUMBNAIL_GEN` | `True` | 1280×720 thumbnail |
| `ENABLE_DUBS` / `DUB_LANGUAGES` | off | Multi-language re-TTS + remux |
| `ENABLE_YOUTUBE_UPLOAD` | `False` | In-pipeline auto-upload |
| `ENABLE_YOUTUBE_UPLOAD_EXPORT` | `True` | Copy output to `Youtube_Upload/videos/` for the standalone uploader |
| `ENABLE_SHORTS` | `False` | Opt-in via `--shorts` / `--shorts-only` |
| `SHORTS_TARGET_DURATION` | `50.0` | Seconds — capped at 60 for cross-platform safety |
| `SHORTS_EMIT_PLATFORM_COPIES` | `True` | Emit `youtube_short.mp4` / `instagram_reel.mp4` / `tiktok.mp4` |

See `.env.example` for the full list.

## Running Tests

```bash
pytest tests/ -q          # 158 tests, runs in ~1.5s (no Manim subprocess)
```

## Streamlit Preview Dashboard

```bash
pip install streamlit
streamlit run dashboard/app.py
```

Pick any run under `output/`, edit per-scene narration / voice mood / music mood / B-roll prompt, hit *Re-render TTS only* (cache-fast) or *Re-render full video*. Mirrors every CLI feature flag.
