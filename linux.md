# Running CoreDuation on WSL (Ubuntu) — Beginner Guide

This is a step-by-step guide for running the long-form video pipeline on **Windows Subsystem for Linux (WSL) with Ubuntu**. It assumes you have a fresh Windows machine and zero Linux experience.

---

## What is WSL?

WSL = Windows Subsystem for Linux. It runs a real Linux system **inside** Windows. You'll have two filesystems visible:
- **Windows files**: from inside Linux they appear under `/mnt/c/...` (e.g. `/mnt/c/workspace/coreduation2`)
- **Linux files**: live in `/home/<your-linux-username>/...`, also written as `~/`

Your project code lives on the Windows side (`C:\workspace\coreduation2`), but your **Python environment must live on the Linux side** because Windows filesystem can't hold Linux file permissions.

---

## Part 1 — One-time setup (do this once)

### 1.1 Install WSL + Ubuntu

Open **PowerShell** (Windows key → type `powershell` → Enter) and run:

```powershell
wsl --install -d Ubuntu
```

When prompted, create a Linux **username** (lowercase, no spaces) and **password**. Write the password down — you'll need it for `sudo` commands. You won't see the characters as you type the password; that's normal.

When the Ubuntu window opens with a prompt like `anant@JayaAnant:~$`, you're in.

### 1.2 Install system tools inside Ubuntu

In the Ubuntu terminal, paste this and press Enter:

```bash
sudo apt update && sudo apt install -y software-properties-common curl ffmpeg \
  libcairo2-dev libpango1.0-dev libgif-dev build-essential pkg-config
```

Type your password when asked.

### 1.3 Install Python 3.12

The default Python on a fresh Ubuntu may be too new (3.14) for our packages. Install Python 3.12 explicitly:

```bash
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3.12-dev
```

Verify:

```bash
python3.12 --version
```

Should print `Python 3.12.x`.

### 1.4 Create the Python virtual environment

**Important:** the venv must live on the Linux filesystem (`~/`), not on `/mnt/c/...`, because Windows filesystem doesn't support Linux file permissions and venv creation will fail.

```bash
python3.12 -m venv ~/coreduation-venv
```

### 1.5 Install Python project dependencies

```bash
source ~/coreduation-venv/bin/activate
cd /mnt/c/workspace/coreduation2
pip install --upgrade pip
pip install -r requirements.txt
```

This takes **5–10 minutes**. Lots of scrolling output is normal.

### 1.6 Make sure your `.env` file exists

The pipeline reads API keys from `.env` in the project root. From Ubuntu:

```bash
ls -la /mnt/c/workspace/coreduation2/.env
```

If it shows the file exists, you're good — same `.env` you use on Windows works on Linux. If it says "No such file", copy `.env.example` to `.env` and fill in your `OPENAI_API_KEY`:

```bash
cp /mnt/c/workspace/coreduation2/.env.example /mnt/c/workspace/coreduation2/.env
nano /mnt/c/workspace/coreduation2/.env
```

(`nano` is a text editor — type your key, then `Ctrl+O` to save, `Enter`, `Ctrl+X` to exit.)

---

## Part 2 — Every-time workflow (do this each time you start a session)

### 2.1 Open Ubuntu

Press the **Windows key**, type `Ubuntu`, press Enter. A terminal opens at your Linux home folder.

### 2.2 Activate venv and go to the project

```bash
source ~/coreduation-venv/bin/activate
cd /mnt/c/workspace/coreduation2
```

Your prompt should now show `(coreduation-venv)` at the front and you should be in `/mnt/c/workspace/coreduation2`.

### 2.3 Run a long-form video

```bash
python main.py --topic "TCP three-way handshake" --engine semantic --category networking
```

Replace `"TCP three-way handshake"` with whatever topic you want. Replace `networking` with the matching category (`security`, `databases`, `programming`, etc.).

The pipeline will:
1. Generate a script via OpenAI (~30s)
2. Generate TTS narration per scene (~1–2 min)
3. Run Whisper alignment (~30s)
4. Render the video with Manim (the long step — **5 to 30 minutes** depending on topic complexity)
5. Mux audio + SFX + music
6. Run frame validation + auto-fix
7. (Optional) Generate thumbnail and dubs

### 2.4 Find your output

The finished video is at:

```
output/<YYYYMMDD_HHMMSS>_semantic_<topic-slug>/final_semantic.mp4
```

From Windows, that's `C:\workspace\coreduation2\output\<timestamp>_semantic_<slug>\final_semantic.mp4`. You can double-click it in File Explorer to play.

### 2.5 Other useful commands

**Run with shorts (vertical 9:16 alongside long-form):**
```bash
python main.py --topic "TLS Handshake" --category security --shorts
```

**Run shorts only (skip long-form):**
```bash
python main.py --topic "TLS Handshake" --category security --shorts-only
```

**Run the test suite:**
```bash
pytest tests/ -q
```

**Preview UI:**
```bash
streamlit run dashboard/app.py
```

---

## Part 3 — Troubleshooting

### "command not found: python" or "command not found: pip"
You haven't activated the venv. Run:
```bash
source ~/coreduation-venv/bin/activate
```

### "No module named 'X'"
Dependency missing. Make sure you're in the venv (see above), then:
```bash
pip install -r /mnt/c/workspace/coreduation2/requirements.txt
```

### `python -m venv` fails with permission errors
The venv must be on the Linux filesystem (`~/coreduation-venv`), not under `/mnt/c/...`. If you accidentally created one in the project folder, delete it:
```bash
rm -rf /mnt/c/workspace/coreduation2/.venv-linux
```

### Manim render fails with "ffmpeg not found"
Reinstall ffmpeg:
```bash
sudo apt install -y ffmpeg
which ffmpeg   # should print /usr/bin/ffmpeg
```

### Manim render fails with "cairo" or "pango" errors
Reinstall the graphics libraries:
```bash
sudo apt install -y libcairo2-dev libpango1.0-dev libgif-dev pkg-config build-essential
```

### Pipeline runs but is very slow
Reading/writing on `/mnt/c/...` is slower than on Linux native filesystem. This is a WSL limitation. For huge speedups you could move the project entirely into `~/coreduation2`, but then you lose easy access from Windows. Most users live with the speed cost.

### How to update WSL itself
From PowerShell (not from inside Ubuntu):
```powershell
wsl --update
```

### How to shut down WSL cleanly
From PowerShell:
```powershell
wsl --shutdown
```

---

## Quick reference card

| What | Command |
|---|---|
| Open Ubuntu | Windows key → "Ubuntu" → Enter |
| Activate venv | `source ~/coreduation-venv/bin/activate` |
| Go to project | `cd /mnt/c/workspace/coreduation2` |
| Run long-form | `python main.py --topic "X" --engine semantic --category Y` |
| Run shorts only | `python main.py --topic "X" --category Y --shorts-only` |
| Run tests | `pytest tests/ -q` |
| Find output | `C:\workspace\coreduation2\output\<timestamp>_semantic_<slug>\` |
| Deactivate venv | `deactivate` |
| Exit Ubuntu | `exit` |
