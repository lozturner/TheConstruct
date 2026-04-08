# TheConstruct

YouTube link in. Desktop folder out. No more talking to Claude every time.

## What it does

1. You copy a YouTube URL to the clipboard.
2. The tray app spots it, asks once, then runs the pipeline.
3. A folder appears on your Desktop named
   `TheConstruct__<title>__<YYYY-MM-DD_HHMMSS>` containing:
   - `transcript.txt` and `transcript-timestamped.txt`
   - `hello.mp3` — your cloned voice saying "hi Laurence"
   - `metadata.json`
   - `run.py` (re-runnable single-file script for that exact URL)
   - `README.md` and `WALKTHROUGH.md`
4. The folder pops open and the audio plays.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium      # only needed for the browser-driven path
cp .env.example .env             # then edit
```

In `.env` set ONE of:

- `ELEVENLABS_API_KEY` — preferred, uses the official API and skips the browser
- `VOICE_SERVICE_EMAIL` + `VOICE_SERVICE_PASSWORD` + `SAMPLE_VOICE_PATH` —
  uses Playwright against PlayHT

## Run

```bash
python tray.py                   # background tray app — usual mode
```

Or use the CLI directly:

```bash
python theconstruct.py bundle <youtube_url>     # full pipeline + bundle
python theconstruct.py transcript <youtube_url>
python theconstruct.py demo                     # smoke test
```

A bare URL also works: `python theconstruct.py https://youtu.be/...` runs `bundle`.

## Files

- `theconstruct.py` — single-file pipeline (transcript + voice clone + bundle)
- `tray.py` — system tray + clipboard watcher + walkthrough
- `test_voice_pipeline.py` — smoke test that synthesizes "hi Laurence"
- `requirements.txt`, `.env.example`
