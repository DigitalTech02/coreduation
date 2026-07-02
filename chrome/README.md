# CoreDuation Chrome (Remotion)

This is the optional Remotion-based **chrome** layer for CoreDuation videos.
It produces broadcast-quality intro, outro, and lower-third clips that the
Python pipeline composites with the Manim content via FFmpeg.

It's a **complementary** layer — Manim still renders the educational content
(topology, packets, code, charts).  Remotion handles the polish.

## Setup

```bash
cd chrome
npm install
```

## Usage

The Python pipeline calls `chrome_compositor.py` which runs:

```bash
npx remotion render src/index.ts Intro out/intro.mp4 --props='{"channelName":"...","tagline":"...","accent":"#3FB6FF"}'
```

You can preview compositions interactively:

```bash
npm run studio
```

## Compositions

- `Intro` — animated logo + channel name (~2.6s)
- `Outro` — "Subscribe" CTA card (~3.5s)
- `LowerThird` — section banner (~4s)

## Configuration

Triggered by `ENABLE_REMOTION_CHROME=true` in the Python `.env`.  Falls back
to Manim-rendered branding when disabled or when `npm`/`node` aren't available.

> **Default is OFF as of Track 5 (May 2026):** Manim already renders an intro
> card + title card + outro card inside `final_semantic.mp4` via
> `play_intro_card` / `play_outro_card` in the scene runner. Layering Remotion
> chrome on top duplicated both ends of every video. Re-enable only when you
> have suppressed the Manim intro/outro (e.g. via a custom build).
