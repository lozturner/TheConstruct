# TheConstruct — Walkthrough

A YouTube link in, a Desktop folder out.

## What just happened
A folder named `TheConstruct__<title>__<timestamp>` was created on your
Desktop. Inside you'll find:

- `transcript.txt` — plain text transcript
- `transcript-timestamped.txt` — same, with `[HH:MM:SS]` markers
- `hello.mp3` — your cloned voice greeting ("hi Laurence")
- `metadata.json` — URL, video id, title, voice id, timestamps
- `run.py` — re-runnable single-file script for this exact URL
- `README.md` — short summary of this bundle
- `WALKTHROUGH.md` — this document

## How to use it day-to-day
1. Run `python tray.py` once. A "TC" icon appears in your system tray.
2. Copy any YouTube URL to the clipboard. The tray app detects it and asks
   if you want to process it.
3. Click "Yes" — a new bundle folder pops open on your Desktop and your
   cloned voice plays the greeting.
4. Use the tray menu for: "Process clipboard URL", "Process URL...",
   "Open last bundle", "Walkthrough", "Quit".

## First-time setup
Edit `.env` (copy from `.env.example`). Set ONE of:
- `ELEVENLABS_API_KEY` — preferred, uses the official API
- `VOICE_SERVICE_EMAIL` + `VOICE_SERVICE_PASSWORD` + `SAMPLE_VOICE_PATH`
  — uses the Playwright browser path against PlayHT

That's it. No more talking to Claude every time.
