# Dashboard

Streamlit UI for tuning a video without re-running the full pipeline from the command line.

## Run

```powershell
pip install streamlit
streamlit run dashboard/app.py
```

Then open the URL Streamlit prints (defaults to <http://localhost:8501>).

## What you can do

- **Generate a script** from a topic + category (cached by topic+category+prompt+model).
- **Pick an existing run** from `output/` and edit per-scene narration, voice mood,
  music mood, and B-roll prompts.
- **Re-render TTS only** — fast, uses the disk cache for unchanged scenes.
- **Re-render the full Manim video.**
- **Preview** the latest video, the auto-generated thumbnail, and any language dubs.
- **Run vision QA** (GPT-4o) on the latest render and view the result inline.

The dashboard relies on the same modules as `main.py`, so any feature flag in
`.env` (Remotion chrome, mood music, kinetic subtitles, vision QA, etc.) is
respected automatically.
