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

## Cloud bridge (no local install needed)

Push a URL into `pending_urls.txt` and the GitHub Actions workflow
`Bundle URL` runs the pipeline on a hosted runner and commits the
result back to `example_bundles/`. You can also trigger it manually from
the Actions tab with a URL parameter.

### One-time setup: cookies (required for the cloud bridge)

YouTube blocks all unauthenticated requests from datacenter IPs as of
late 2024 — including GitHub Actions runners. We've verified this with
a real Chromium screenshot in `example_bundles/`: even a stealth
Playwright session loads the page shell but the player config comes
back null with "Sign in to confirm you're not a bot".

The fix is **one** manual step, done **once**:

1. In a logged-in browser, install the **"Get cookies.txt LOCALLY"**
   extension (Chrome/Firefox), open `https://www.youtube.com/`, click
   the extension, hit "Export".
2. Open the downloaded `cookies.txt` and copy its full contents.
3. In your GitHub repo: **Settings → Secrets and variables → Actions →
   New repository secret**. Name it `YT_COOKIES`. Paste the contents.
   Save.
4. Push a URL into `pending_urls.txt`. The workflow now uses your
   cookies, slips past the bot wall, and commits the real bundle back.

After that, you never touch it again. Drop URLs, get bundles.

### Local mode (no cookies needed)

The pipeline running on your own desktop uses your residential IP,
which YouTube treats normally. `python tray.py` works without any
cookie setup.

## Files

- `theconstruct.py` — single-file pipeline (transcript + voice clone + bundle)
- `tray.py` — system tray + clipboard watcher + walkthrough
- `test_voice_pipeline.py` — smoke test that synthesizes "hi Laurence"
- `.github/workflows/bundle.yml` — cloud bridge workflow
- `pending_urls.txt` — drop URLs here to trigger the bridge
- `requirements.txt`, `.env.example`
