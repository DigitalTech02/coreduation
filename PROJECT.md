# CoreDuation — AI Video Generation Pipeline

An automated pipeline that transforms any educational topic into a fully narrated, animated video using LLM script generation, text-to-speech, and the Manim animation engine.

## How It Works

```
Topic (CLI)
    │
    ▼
┌──────────────────────────┐
│  1. Category Detection   │  Fast LLM call classifies the topic
│     (auto or explicit)   │  into one of 8 specialty domains
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  2. Script Generation    │  Domain-specific system prompt + GPT-4.1
│     (Semantic JSON)      │  produces structured visual actions
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  3. Validation & Repair  │  ID deduplication, reference checking,
│                          │  type coercion
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  4. Text-to-Speech       │  OpenAI TTS or ElevenLabs per scene
│                          │  → combined narration track
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  5. Manim Rendering      │  Deterministic engine translates
│     (single Scene)       │  semantic actions → animations
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  6. Audio/Video Mux      │  ffmpeg combines silent video
│                          │  with narration → final MP4
└──────────────────────────┘
```

## Architecture

The pipeline uses a **"Semantic JSON + Deterministic Engine"** architecture. The LLM never writes code — it outputs structured JSON actions (e.g. `create_node`, `send_packet`, `show_table`), and a hand-written Python rendering engine translates those into Manim animations deterministically.

### Why this approach?

- **Zero code hallucinations** — the LLM only picks from a fixed action vocabulary
- **Stateful rendering** — objects persist across scenes (topology stays while packets fly)
- **Perfect layouts** — spatial math is handled in Python, not guessed by the LLM
- **Timing-driven** — animations are paced to match narration duration

## Project Structure

```
coreduation/
├── main.py                        # Entry point, CLI, pipeline orchestration
├── llm_orchestrator_semantic.py   # LLM script generation (semantic engine)
├── llm_orchestrator.py            # Legacy LLM orchestrator (raw Manim code)
├── models_semantic.py             # Pydantic models: actions, scenes, scripts
├── models.py                      # Legacy Pydantic models
├── semantic_validation.py         # Pre-render validation (IDs, references)
├── semantic_repair.py             # Post-generation ID deduplication
├── semantic_audio.py              # Audio concatenation + ffmpeg muxing
├── tts_generator.py               # OpenAI / ElevenLabs TTS wrapper
├── animation_renderer.py          # Legacy per-scene Manim renderer
├── video_stitcher.py              # Legacy video concatenation
├── error_healer.py                # Legacy LLM-based Manim error healing
│
├── prompts/                       # Specialty prompt system
│   ├── __init__.py                # Registry: get_prompt(category), auto-detect
│   ├── _base.py                   # SpecialtyPrompt dataclass + shared assembler
│   ├── networking.py              # Networking & protocols
│   ├── data_structures.py         # DSA & algorithms
│   ├── programming.py             # Programming concepts
│   ├── cloud_architecture.py      # Cloud & infrastructure
│   ├── system_design.py           # System design interviews
│   ├── business_analysis.py       # Business frameworks
│   ├── databases.py               # Database engineering
│   └── security.py                # Cybersecurity & protocols
│
├── rendering_engine/              # Deterministic Manim rendering engine
│   ├── __init__.py
│   ├── engine.py                  # Core: SceneState, action dispatch, render orchestration
│   ├── full_video_scene.py        # Single-Scene animation loop, title card, cleanup
│   ├── full_video_runner.py       # Manim entry point (FullSemanticVideo class)
│   ├── styles.py                  # Colors, fonts, sizes, timing, visual effects
│   ├── topology.py                # Nodes, connections, layout algorithms
│   ├── packets.py                 # Packet/message flow animations
│   ├── sequence.py                # UML sequence diagrams
│   ├── data_display.py            # Layer stacks, headers, tables, math
│   ├── presentation.py            # Text blocks, bullet lists, code, comparisons
│   └── cloud.py                   # Cloud regions, services, data flows
│
├── COMMANDS.md                    # CLI usage reference
├── PROJECT.md                     # This file
├── requirements.txt               # Python dependencies
├── .env                           # API keys and config (not committed)
└── .gitignore
```

## Visual Action Vocabulary (19 types)

The LLM selects from these action types. The rendering engine handles all Manim code.

| Category | Actions |
|---|---|
| **Topology** | `create_node`, `create_connection`, `create_topology`, `update_node`, `remove_element` |
| **Packet Flow** | `send_packet`, `send_broadcast` |
| **Sequence Diagram** | `show_sequence_diagram` |
| **Data/Protocol** | `show_layer_stack`, `show_header_breakdown`, `show_table`, `show_math` |
| **Presentation** | `show_text_block`, `show_code_block`, `show_comparison`, `show_bullet_list` |
| **Cloud** | `create_cloud_region`, `create_cloud_service`, `show_data_flow` |

## Specialty Prompt System

Each content domain has a dedicated prompt with:

| Component | Purpose |
|---|---|
| **Persona** | Who the teacher is (network engineer, algorithms instructor, etc.) |
| **Video Structure** | Domain-specific scene flow (10-18 scenes) |
| **Narration Style** | Tone, vocabulary, pacing guidelines |
| **Preferred Actions** | Which visual actions to favor and avoid |
| **Example Scene** | Gold-standard JSON example (few-shot prompting) |
| **Title Card Subtitle** | Dynamic per-category (e.g. "Data Structures & Algorithms") |

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

## Visual Effects

The rendering engine includes visual polish applied automatically to every video:

- **Gradient fills** on topology nodes and cloud services (darker shade + sheen)
- **Glow halos** on highlighted nodes and the title card
- **Drop shadows** behind tables, text blocks, code blocks, comparisons, bullet lists
- **Sheen effect** on packet pills, layer stacks, header fields, table headers
- **Dark theme** with a consistent `#0f1117` background

## Tech Stack

| Component | Library | Version | Purpose |
|---|---|---|---|
| **LLM** | `openai` | >= 1.60.0 | GPT-4.1 for script generation and category detection |
| **Data Models** | `pydantic` | >= 2.10.0 | Strict schemas, discriminated unions, field validators |
| **Animation** | `manim` | >= 0.20.1 | Manim Community Edition for all visuals |
| **TTS (primary)** | `openai` | >= 1.60.0 | OpenAI TTS API (tts-1 / tts-1-hd) |
| **TTS (alt)** | `elevenlabs` | >= 1.20.0 | ElevenLabs as alternate TTS provider |
| **Audio** | `pydub` | >= 0.25.1 | Audio concatenation, silence padding |
| **Video** | `moviepy` | >= 2.0.0 | Legacy pipeline video stitching |
| **A/V Mux** | `ffmpeg` | (system) | Final audio+video muxing (subprocess) |
| **Config** | `python-dotenv` | >= 1.0.1 | Environment variable management |

### System Requirements

- **Python** 3.12+
- **ffmpeg** installed and on PATH
- **LaTeX** distribution (for MathTex rendering in Manim — optional, graceful fallback)

## CLI Usage

```bash
# Explicit category
python main.py --topic "Binary Search" --category data-structures
python main.py --topic "TCP Handshake" --category networking
python main.py --topic "AWS VPC Design" --category cloud-architecture

# Auto-detect (default — LLM classifies the topic)
python main.py --topic "How DNS Resolution Works"

# Legacy engine (raw Manim code generation — not recommended)
python main.py --topic "Sorting Algorithms" --engine legacy
```

### CLI Flags

| Flag | Default | Description |
|---|---|---|
| `--topic` | `"TCP Three-Way Handshake"` | The educational topic to generate a video for |
| `--engine` | `semantic` | `semantic` (recommended) or `legacy` |
| `--category` | `auto` | One of the 8 categories, or `auto` for LLM detection |

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | OpenAI API key for GPT-4.1 and TTS |
| `OPENAI_MODEL` | No | Override LLM model (default: `gpt-4.1`) |
| `TTS_PROVIDER` | No | `openai` (default) or `elevenlabs` |
| `OPENAI_TTS_MODEL` | No | `tts-1` or `tts-1-hd` |
| `OPENAI_TTS_VOICE` | No | Voice name (e.g. `alloy`, `nova`, `echo`) |
| `ELEVENLABS_API_KEY` | If using ElevenLabs | ElevenLabs API key |
| `ELEVENLABS_VOICE_ID` | If using ElevenLabs | Voice ID |
| `ELEVENLABS_MODEL_ID` | If using ElevenLabs | Model ID |

## Output

Each run creates a timestamped folder under `output/`:

```
output/
└── 2026-04-23_tcp-three-way-handshake_semantic/
    ├── script.json          # Full semantic script (for debugging)
    ├── audio/               # Per-scene TTS .mp3 files
    ├── video/               # Intermediate video files
    ├── full_narration.mp3   # Combined audio track
    └── final_video.mp4      # Finished video with narration
```
