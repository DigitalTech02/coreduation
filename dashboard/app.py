"""Streamlit preview dashboard for CoreDuation.

Run with::

    streamlit run dashboard/app.py

Workflow it enables:
  1. Type a topic & pick a category, click *Generate script* — uses
     ``llm_orchestrator_semantic.generate_semantic_script`` (which is cached
     by topic + category + prompt + model, so re-runs are instant).
  2. Inspect / edit per-scene narration, voice mood, music mood, image prompts.
  3. Save the edited script back to its run directory.
  4. Click *Re-render TTS only* (re-runs ``generate_speech`` per scene → uses
     the disk cache for unchanged scenes), or *Re-render full video* (Manim).
  5. Preview the silent video, the muxed final video, the auto-generated
     thumbnail, and the vision QA report inline.

Heavy imports (manim, openai, …) are deferred until the matching button is
pressed so the dashboard starts in <2s.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

# Make the workspace root importable when launched from anywhere.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    import streamlit as st
except ImportError:
    raise SystemExit(
        "Streamlit is not installed. Run:  pip install streamlit"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CATEGORIES = [
    "auto",
    "networking",
    "data-structures",
    "programming",
    "cloud-architecture",
    "system-design",
    "business-analysis",
    "databases",
    "security",
]


def list_runs() -> list[Path]:
    out_dir = _ROOT / "output"
    if not out_dir.exists():
        return []
    runs = [p for p in out_dir.iterdir() if p.is_dir()]
    runs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return runs


def load_script(run_dir: Path):
    sj = run_dir / "script.json"
    if not sj.exists():
        return None
    try:
        return json.loads(sj.read_text(encoding="utf-8"))
    except Exception as e:
        st.error(f"Failed to load script.json: {e}")
        return None


def save_script(run_dir: Path, data: dict) -> None:
    sj = run_dir / "script.json"
    sj.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def find_video(run_dir: Path) -> Path | None:
    for name in ("final_with_chrome.mp4", "final_semantic.mp4"):
        p = run_dir / name
        if p.exists():
            return p
    vid_dir = run_dir / "video"
    if vid_dir.exists():
        mp4s = sorted(vid_dir.glob("*.mp4"))
        if mp4s:
            return mp4s[-1]
    return None


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.set_page_config(page_title="CoreDuation Dashboard", page_icon=":clapper:", layout="wide")
st.title("CoreDuation — Preview Dashboard")
st.caption(
    "Edit narration, swap voice/music moods, preview cached re-renders. "
    f"Workspace: `{_ROOT}`"
)

with st.sidebar:
    st.subheader("Generate new video")
    topic = st.text_input("Topic", value="B-Tree Indexes")
    category = st.selectbox("Category", CATEGORIES, index=0)
    if st.button("Generate script", type="primary", use_container_width=True):
        with st.spinner("Calling LLM (cached if you've run this before)…"):
            try:
                from llm_orchestrator_semantic import generate_semantic_script
                from main import _make_run_dir
                from semantic_repair import repair_duplicate_ids
                from semantic_validation import validate_semantic_script

                script = generate_semantic_script(topic, category=category)
                script = repair_duplicate_ids(script)
                validate_semantic_script(script)

                run_dir = _make_run_dir(topic, "semantic")
                save_script(run_dir, script.model_dump(by_alias=True))
                st.success(f"Saved script -> {run_dir}")
                st.session_state["selected_run"] = str(run_dir)
                st.rerun()
            except Exception as e:
                st.error(f"Script generation failed: {e}")

    st.divider()
    st.subheader("Existing runs")
    runs = list_runs()
    if not runs:
        st.info("No runs yet.")
    else:
        labels = [f"{p.name} ({datetime.fromtimestamp(p.stat().st_mtime).strftime('%Y-%m-%d %H:%M')})"
                  for p in runs]
        default_idx = 0
        if "selected_run" in st.session_state:
            for i, p in enumerate(runs):
                if str(p) == st.session_state["selected_run"]:
                    default_idx = i
                    break
        choice = st.selectbox("Pick a run", labels, index=default_idx)
        st.session_state["selected_run"] = str(runs[labels.index(choice)])


run_dir_str = st.session_state.get("selected_run")
if not run_dir_str:
    st.info("Generate a script or pick an existing run from the sidebar to begin.")
    st.stop()

run_dir = Path(run_dir_str)
st.subheader(f"Run: `{run_dir.name}`")

data = load_script(run_dir)
if data is None:
    st.error("This run has no script.json yet.")
    st.stop()

meta_cols = st.columns(4)
meta_cols[0].metric("Scenes", len(data.get("scenes", [])))
meta_cols[1].metric("Category", data.get("category") or "—")
meta_cols[2].write(f"**Title:** {data.get('video_title') or '—'}")
meta_cols[3].write(f"**Hook:** {data.get('video_hook') or '—'}")

tab_edit, tab_preview, tab_qa = st.tabs(["Edit scenes", "Preview", "Vision QA"])

with tab_edit:
    st.write("Edit narration / mood per scene, then save & re-render.")
    edited = False
    moods_voice = ["", "narrator", "excited", "dramatic", "calm", "analytical", "urgent", "hook"]
    moods_music = ["", "uplifting", "tense", "curious", "calm", "dramatic", "neutral"]

    for i, scene in enumerate(data.get("scenes", [])):
        with st.expander(f"Scene {i+1}: {scene.get('title', scene.get('scene_id'))}", expanded=(i == 0)):
            new_narr = st.text_area(
                "Narration", value=scene.get("narration", ""), key=f"narr-{i}", height=120,
            )
            c1, c2, c3 = st.columns(3)
            with c1:
                vm = scene.get("voice_mood", "") or ""
                idx = moods_voice.index(vm) if vm in moods_voice else 0
                new_vm = st.selectbox("Voice mood", moods_voice, index=idx, key=f"vm-{i}")
            with c2:
                mm = scene.get("music_mood", "") or ""
                idx = moods_music.index(mm) if mm in moods_music else 0
                new_mm = st.selectbox("Music mood", moods_music, index=idx, key=f"mm-{i}")
            with c3:
                new_ip = st.text_input("B-roll image prompt",
                                       value=scene.get("image_prompt", ""), key=f"ip-{i}")

            if (new_narr != scene.get("narration", "")
                    or new_vm != (scene.get("voice_mood") or "")
                    or new_mm != (scene.get("music_mood") or "")
                    or new_ip != (scene.get("image_prompt") or "")):
                scene["narration"] = new_narr
                scene["voice_mood"] = new_vm
                scene["music_mood"] = new_mm
                scene["image_prompt"] = new_ip
                edited = True

    save_col, tts_col, render_col = st.columns(3)
    if save_col.button("Save edits", use_container_width=True, disabled=not edited):
        save_script(run_dir, data)
        st.success("script.json saved.")

    if tts_col.button("Re-render TTS only", use_container_width=True):
        save_script(run_dir, data)
        with st.spinner("Re-running TTS for all scenes (cached for unchanged ones)…"):
            try:
                from tts_generator import generate_speech
                audio_dir = run_dir / "audio"
                audio_dir.mkdir(exist_ok=True)
                for scene in data.get("scenes", []):
                    out = audio_dir / f"{scene['scene_id']}.mp3"
                    generate_speech(scene["narration"], str(out),
                                    mood=scene.get("voice_mood") or None)
                st.success(f"TTS re-rendered into {audio_dir}")
            except Exception as e:
                st.error(f"TTS re-render failed: {e}")

    if render_col.button("Re-render full video (Manim)", use_container_width=True):
        save_script(run_dir, data)
        with st.spinner("Rendering full Manim video — this can take a few minutes…"):
            try:
                from models_semantic import EnrichedVideoScript
                from rendering_engine.engine import render_full_semantic_video
                from semantic_audio import build_semantic_narration_track, mux_video_with_audio

                script = EnrichedVideoScript(**data)
                video_dir = run_dir / "video"
                silent = render_full_semantic_video(script, output_dir=video_dir)
                if silent:
                    audio_dir = run_dir / "audio"
                    audio_paths = [str(audio_dir / f"{s.scene_id}.mp3") for s in script.scenes
                                   if (audio_dir / f"{s.scene_id}.mp3").exists()]
                    if audio_paths:
                        narration = str(run_dir / "full_narration.mp3")
                        actions = [[a.model_dump(by_alias=True) for a in s.actions]
                                   for s in script.scenes]
                        moods = [getattr(s, "music_mood", "") or "" for s in script.scenes]
                        build_semantic_narration_track(
                            audio_paths, output_path=narration,
                            scene_actions=actions, category=script.category,
                            scene_moods=moods,
                        )
                        final = str(run_dir / "final_semantic.mp4")
                        mux_video_with_audio(silent, narration, final)
                    st.success("Re-render complete.")
                else:
                    st.error("Manim render returned no path.")
            except Exception as e:
                st.error(f"Render failed: {e}")


with tab_preview:
    video = find_video(run_dir)
    if video is None:
        st.info("No rendered video yet — re-render from the *Edit scenes* tab.")
    else:
        st.write(f"**Latest video:** `{video.name}`")
        with open(video, "rb") as fh:
            st.video(fh.read())

    st.divider()
    thumb = run_dir / "thumbnail.jpg"
    cols = st.columns([1, 1])
    with cols[0]:
        st.write("**Thumbnail**")
        if thumb.exists():
            st.image(str(thumb), use_container_width=True)
        else:
            st.info("No thumbnail yet.")
        if st.button("Regenerate thumbnail"):
            try:
                from thumbnail_generator import generate_thumbnail
                title = data.get("suggested_thumbnail_text") or data.get("video_title") or data.get("topic", "")
                generate_thumbnail(title, data.get("category", ""), str(thumb))
                st.success("Thumbnail regenerated.")
                st.rerun()
            except Exception as e:
                st.error(f"Thumbnail failed: {e}")

    with cols[1]:
        st.write("**Dub videos**")
        dubs = sorted(run_dir.glob("final_*.mp4"))
        if dubs:
            for d in dubs:
                st.write(f"- `{d.name}`")
        else:
            st.info("No language dubs in this run.")


with tab_qa:
    qa_path = run_dir / "vision_qa.json"
    if not qa_path.exists():
        st.info("No vision QA report. Run the pipeline with `ENABLE_VISION_QA=true` "
                "or trigger it manually below.")
        if st.button("Run Vision QA now"):
            video = find_video(run_dir)
            if video is None:
                st.error("No rendered video to analyze.")
            else:
                with st.spinner("Sampling frames and asking GPT-4o…"):
                    try:
                        from vision_qa import run_vision_qa
                        run_vision_qa(str(video), report_path=str(qa_path))
                        st.success("QA report generated.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Vision QA failed: {e}")
    else:
        try:
            issues = json.loads(qa_path.read_text(encoding="utf-8"))
            fail_ct = sum(1 for i in issues if i.get("severity") == "fail")
            warn_ct = sum(1 for i in issues if i.get("severity") == "warn")
            ok_ct = sum(1 for i in issues if i.get("severity") == "ok")
            cs = st.columns(3)
            cs[0].metric("Failures", fail_ct)
            cs[1].metric("Warnings", warn_ct)
            cs[2].metric("Healthy frames", ok_ct)
            st.dataframe(issues, use_container_width=True, height=400)
        except Exception as e:
            st.error(f"Could not parse QA report: {e}")
