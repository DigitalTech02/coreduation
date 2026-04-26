# Video Generation Commands

## Usage

```bash
python main.py --topic "<TOPIC>" [--category <CATEGORY>] [--engine semantic|legacy]
```

- `--topic` — The video topic (required)
- `--category` — Specialty prompt category (default: `auto`)
- `--engine` — Rendering engine (default: `semantic`)

## Available Categories

| Category | Best for |
|---|---|
| `networking` | TCP, DNS, BGP, routing, protocols |
| `data-structures` | Arrays, trees, linked lists, hash maps, binary search |
| `programming` | Recursion, Big-O, design patterns, language concepts |
| `cloud-architecture` | AWS VPC, serverless, multi-region, CDN |
| `system-design` | URL shortener, chat system, load balancer design |
| `business-analysis` | SWOT, requirements gathering, use case modeling |
| `databases` | Normalization, B-tree indexes, ACID, SQL queries |
| `security` | TLS handshake, OAuth2, firewall rules, encryption |
| `auto` | LLM auto-detects the best category (default) |

## Examples — Explicit Category

```bash
python main.py --topic "TCP Three-Way Handshake" --category networking
python main.py --topic "Binary Search" --category data-structures
python main.py --topic "AWS VPC Design" --category cloud-architecture
python main.py --topic "SWOT Analysis" --category business-analysis
python main.py --topic "Recursion in Python" --category programming
python main.py --topic "B-Tree Indexes" --category databases
python main.py --topic "TLS Handshake" --category security
python main.py --topic "URL Shortener Design" --category system-design
```

## Examples — Auto-Detect Category

```bash
python main.py --topic "How DNS Resolution Works"
python main.py --topic "Merge Sort Algorithm"
python main.py --topic "Kubernetes Pod Networking"
python main.py --topic "Database Normalization"
```

## Output

Each run creates a timestamped folder under `output/` containing:

- `script.json` — The generated semantic script (edit and re-render via the dashboard)
- `audio/` — Per-scene TTS narration files
- `audio_<lang>/` — Per-language dub TTS (when `ENABLE_DUBS=true`)
- `video/` — Silent Manim render(s)
- `full_narration.mp3` — Combined audio track (narration + SFX + mood-matched music)
- `full_narration_<lang>.mp3` — Per-language narration when dubbing
- `final_semantic.mp4` — Manim video with narration audio
- `final_with_chrome.mp4` — Above, with Remotion intro/outro concatenated (when enabled)
- `final_<lang>.mp4` — Per-language dub videos
- `thumbnail.jpg` — 1280×720 YouTube thumbnail (when `ENABLE_THUMBNAIL_GEN=true`)
- `vision_qa.json` — GPT-4o frame-by-frame QA report (when `ENABLE_VISION_QA=true`)

---

## Streamlit Preview Dashboard

A web UI for tuning a video without re-running the whole CLI pipeline. Cached
re-renders make iteration nearly instant.

### Install (one-time)

```bash
pip install streamlit
```

### Launch

```bash
python -m streamlit run dashboard/app.py --server.headless true
```

Then open the URL Streamlit prints (default <http://localhost:8501>).

> **Note:** Use `python -m streamlit` instead of bare `streamlit` if the
> command is not on your system PATH (common with user-level pip installs on
> Windows). The `--server.headless true` flag skips the first-run email prompt.

Custom port:

```bash
python -m streamlit run dashboard/app.py --server.headless true --server.port 8600
```

To stop the server, press `Ctrl+C` in the terminal that launched it.

### What you can do in the dashboard

1. **Sidebar — Generate new video** — type a topic, pick a category, click
   *Generate script*. Cached by `(topic, category, prompt, model)` so re-runs
   are instant.
2. **Sidebar — Existing runs** — pick any timestamped folder under `output/`.
3. **Edit scenes tab** — edit narration text, swap `voice_mood`, swap
   `music_mood`, set `image_prompt` for AI B-roll.
4. **Re-render TTS only** — fast (cache hits for unchanged scenes).
5. **Re-render full video (Manim)** — full Manim re-render plus narration mux.
6. **Preview tab** — inline player for the latest MP4, thumbnail preview +
   regenerate button, list of language dubs.
7. **Vision QA tab** — view the existing GPT-4o frame report or trigger a new
   QA pass on demand.

The dashboard respects every `.env` flag (Remotion, mood music, kinetic
subtitles, vision QA, etc.), so anything you enable on the CLI is also
available in the UI.

---

## Engagement Upgrade — Feature Flags

All set in `.env` or inline; defaults match a sensible "polished but cheap" baseline.

### Per-feature commands

```bash
# Vision QA after render (~$0.10-0.30 per video)
ENABLE_VISION_QA=true python main.py --topic "Hash Maps" --category data-structures

# Branding (intro card + outro CTA + corner watermark)
ENABLE_BRANDING=true CHANNEL_NAME="CoreDuation" python main.py --topic "B-Tree Indexes" --category databases

# AI-generated B-roll (DALL-E 3) — requires OPENAI_API_KEY
ENABLE_AI_BROLL=true python main.py --topic "How CDNs Work" --category cloud-architecture

# Real D3 charts (one-time setup: `playwright install chromium`)
python main.py --topic "TCP Throughput vs Latency" --category networking

# Pseudo-3D topology (depth shading + camera orbit drift)
ENABLE_3D_TOPOLOGY=true python main.py --topic "Spanning Tree Protocol" --category networking

# Kinetic word-level subtitles (requires `pip install openai-whisper`)
ENABLE_KINETIC_SUBTITLES=true python main.py --topic "Recursion" --category programming

# Multi-language dubs (translate + re-TTS into Spanish, Hindi, French)
ENABLE_DUBS=true DUB_LANGUAGES="es,hi,fr" python main.py --topic "OAuth2" --category security

# YouTube auto-upload (requires client_secret.json from Google Cloud Console)
ENABLE_YOUTUBE_UPLOAD=true YOUTUBE_PRIVACY_STATUS=unlisted python main.py --topic "REST API Design" --category system-design
```

### Remotion chrome (Node-side setup)

```bash
cd chrome
npm install
cd ..

# Now Python can render intro/outro via Remotion
ENABLE_REMOTION_CHROME=true python main.py --topic "Kubernetes Pods" --category cloud-architecture
```

If you see `Remotion not installed` or `could not execute npx`: install [Node.js LTS](https://nodejs.org/) (includes `node` and `npx`), open a **new** terminal so `PATH` updates, run `cd chrome && npm install`, then try again. On Windows, the pipeline resolves `npx.cmd` automatically; if `node` works but the warning persists, verify `where npx` in PowerShell.

### Full-stack engagement run

Everything on (slow + expensive but maximally polished):

```bash
ENABLE_VISION_QA=true \
  ENABLE_KINETIC_SUBTITLES=true \
  ENABLE_AI_BROLL=true \
  ENABLE_3D_TOPOLOGY=true \
  ENABLE_REMOTION_CHROME=true \
  ENABLE_THUMBNAIL_GEN=true \
  THUMBNAIL_USE_AI_BG=true \
  ENABLE_DUBS=true DUB_LANGUAGES="es,hi" \
  ENABLE_YOUTUBE_UPLOAD=true YOUTUBE_PRIVACY_STATUS=unlisted \
  python main.py --topic "Database Sharding" --category databases
```

### Cache management

```bash
# Caches live under .cache/ (TTS, LLM scripts, translations, B-roll, thumbnails)
rm -rf .cache/                    # nuke all caches
rm -rf .cache/llm_scripts/        # only LLM scripts
rm -rf .cache/tts/                # only TTS audio
```

---

## Run Tests

```bash
python -m pytest tests/ -v
```

All 30 tests should pass.
