# TheConstruct

YouTube link in. Desktop folder out.

## Install (one line)

**Windows (PowerShell):**

```powershell
iwr -useb https://raw.githubusercontent.com/lozturner/theconstruct/claude/multi-agent-orchestration-ipOZM/install.ps1 | iex
```

**macOS / Linux (Terminal):**

```bash
curl -sSL https://raw.githubusercontent.com/lozturner/theconstruct/claude/multi-agent-orchestration-ipOZM/install.sh | bash
```

That's it. The installer clones the repo, makes a venv, installs deps,
puts a **TheConstruct** shortcut on your Desktop, launches the local
web app, and opens your browser at `http://localhost:7117/`.

Paste a YouTube URL into the box. Hit Go. A folder appears on your
Desktop with the transcript, your cloned-voice greeting, and a
re-runnable script. The greeting plays in the page.

Next time: double-click the **TheConstruct** shortcut on your Desktop.

## Prerequisites

- **Python 3.10+** on PATH
  ([python.org/downloads](https://www.python.org/downloads/) — tick "Add
  to PATH" on Windows)
- **git** on PATH

## Voice config (optional but recommended)

Without any config, the greeting uses the offline `espeak-ng` voice (a
synthetic robot voice). For a proper cloned voice, set ONE of these in
`~/TheConstruct/.env` (copy from `.env.example`):

- `ELEVENLABS_API_KEY=sk_...` — cleanest; uses the official API
- `VOICE_SERVICE_EMAIL` + `VOICE_SERVICE_PASSWORD` + `SAMPLE_VOICE_PATH`
  — uses a Playwright-driven PlayHT session

## What's in a bundle

Each run writes a folder to your Desktop named
`TheConstruct__<title>__<YYYY-MM-DD_HHMMSS>/` containing:

- `transcript.txt`, `transcript-timestamped.txt`
- `hello.mp3` (or `hello.wav`) — greeting audio
- `metadata.json` — url, video id, title, voice id, timestamps
- `run.py` — re-runnable single-file script for this exact URL
- `README.md`, `WALKTHROUGH.md`

## Alternative interfaces

- `python tray.py` — system-tray icon + clipboard watcher
- `python theconstruct.py bundle <url>` — CLI one-shot
- `python theconstruct.py demo` — offline smoke test

## Cloud bridge (optional, only if you want to run without installing)

Push a YouTube URL into `pending_urls.txt` and the
`.github/workflows/bundle.yml` workflow runs the pipeline on a GitHub
runner and commits the produced bundle to `example_bundles/`. Because
GitHub runners are datacenter IPs, YouTube challenges them with
"Sign in to confirm you're not a bot" — so the bridge needs **one**
manual step:

1. Install the **"Get cookies.txt LOCALLY"** browser extension, open
   `https://www.youtube.com/` while logged in, click the extension,
   hit "Export".
2. In your GitHub repo: **Settings → Secrets and variables → Actions →
   New repository secret**. Name it `YT_COOKIES`, paste the file
   contents.

After that the bridge works. The local mode above does not need this —
your residential IP bypasses the block.

## Files

- `app.py` — local web app at `http://localhost:7117/`
- `theconstruct.py` — single-file pipeline (transcript + voice clone + bundle)
- `tray.py` — system-tray + clipboard watcher
- `install.ps1` / `install.sh` — one-line installers
- `.github/workflows/bundle.yml` — cloud bridge workflow
- `requirements.txt`, `.env.example`
