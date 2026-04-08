"""TheConstruct — single-file pipeline.

YouTube transcript -> voice clone (browser-driven) -> TTS synthesis.

Usage:
    python theconstruct.py transcript <youtube_url>
    python theconstruct.py clone <sample.wav>
    python theconstruct.py say "hi Laurence" [--voice-id ID]
    python theconstruct.py pipeline <youtube_url> [--voice-id ID]
    python theconstruct.py demo
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

# ============================================================================
# Config
# ============================================================================

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass
class Config:
    output_dir: Path = field(default_factory=lambda: Path(os.getenv("OUTPUT_DIR", "./out")))
    headless: bool = os.getenv("HEADLESS", "true").lower() in ("1", "true", "yes")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    sample_voice_path: Optional[str] = os.getenv("SAMPLE_VOICE_PATH")
    default_voice_id: Optional[str] = os.getenv("DEFAULT_VOICE_ID")
    voice_service: str = os.getenv("VOICE_SERVICE", "playht")
    voice_service_email: Optional[str] = os.getenv("VOICE_SERVICE_EMAIL")
    voice_service_password: Optional[str] = os.getenv("VOICE_SERVICE_PASSWORD")
    elevenlabs_api_key: Optional[str] = os.getenv("ELEVENLABS_API_KEY")
    user_data_dir: Path = field(
        default_factory=lambda: Path(os.getenv("USER_DATA_DIR", "~/.cache/theconstruct")).expanduser()
    )

    def ensure_dirs(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.user_data_dir.mkdir(parents=True, exist_ok=True)


CONFIG = Config()


# ============================================================================
# Logging
# ============================================================================

def setup_logging(level: str = "INFO") -> logging.Logger:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    return logging.getLogger("theconstruct")


log = setup_logging(CONFIG.log_level)


# ============================================================================
# Errors
# ============================================================================

class ConfigError(Exception): pass
class TranscriptError(Exception): pass
class VoiceCloneError(Exception): pass
class SynthesisError(Exception): pass
class CaptchaRequiredError(VoiceCloneError): pass


EXIT_CODES = {
    ConfigError: 2,
    TranscriptError: 3,
    VoiceCloneError: 4,
    SynthesisError: 5,
}


# ============================================================================
# Section 1 — YouTube transcript fetcher
# ============================================================================

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def _extract_video_id(url: str) -> str:
    """Extract a YouTube video ID from many URL shapes."""
    if _VIDEO_ID_RE.match(url):
        return url
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().lstrip("www.")
    if host == "youtu.be":
        vid = parsed.path.lstrip("/").split("/")[0]
    elif "youtube" in host:
        if parsed.path == "/watch":
            vid = parse_qs(parsed.query).get("v", [""])[0]
        else:
            parts = [p for p in parsed.path.split("/") if p]
            # /shorts/<id>, /embed/<id>, /live/<id>
            vid = parts[1] if len(parts) >= 2 and parts[0] in {"shorts", "embed", "live", "v"} else ""
    else:
        vid = ""
    if not _VIDEO_ID_RE.match(vid):
        raise ValueError(f"Could not extract a YouTube video ID from: {url!r}")
    return vid


def _format_segments(segments, with_timestamps: bool) -> str:
    if with_timestamps:
        lines = []
        for s in segments:
            t = int(s.get("start", 0))
            lines.append(f"[{t // 3600:02d}:{(t % 3600) // 60:02d}:{t % 60:02d}] {s['text']}")
        return "\n".join(lines)
    return re.sub(r"\s+", " ", " ".join(s["text"] for s in segments)).strip()


def get_transcript(
    url: str,
    languages: Optional[list[str]] = None,
    with_timestamps: bool = False,
    prefer_manual: bool = True,
) -> str:
    """Return a YouTube video transcript as plain text.

    Tries youtube-transcript-api first, then yt-dlp as a fallback.
    Raises TranscriptError on irrecoverable failures.
    """
    languages = languages or ["en"]
    video_id = _extract_video_id(url)
    log.info("Fetching transcript for video_id=%s", video_id)

    try:
        from youtube_transcript_api import (  # type: ignore
            YouTubeTranscriptApi,
            TranscriptsDisabled,
            NoTranscriptFound,
            VideoUnavailable,
        )
    except ImportError as e:
        raise TranscriptError(
            "youtube-transcript-api not installed. Run: pip install youtube-transcript-api"
        ) from e

    def _normalize(fetched) -> list[dict]:
        # youtube-transcript-api >=1.0 returns a FetchedTranscript whose snippets
        # are objects with .text/.start/.duration. Older versions returned list[dict].
        snippets = getattr(fetched, "snippets", fetched)
        out = []
        for s in snippets:
            if isinstance(s, dict):
                out.append({"text": s.get("text", ""), "start": s.get("start", 0)})
            else:
                out.append({"text": getattr(s, "text", ""), "start": getattr(s, "start", 0)})
        return out

    try:
        # v1.x uses instance methods (list/fetch); v0.x used classmethods (list_transcripts).
        if hasattr(YouTubeTranscriptApi, "list_transcripts"):
            listing = YouTubeTranscriptApi.list_transcripts(video_id)  # type: ignore[attr-defined]
        else:
            listing = YouTubeTranscriptApi().list(video_id)

        chosen = None
        if prefer_manual:
            try:
                chosen = listing.find_manually_created_transcript(languages)
            except NoTranscriptFound:
                pass
        if chosen is None:
            try:
                chosen = listing.find_transcript(languages)
            except NoTranscriptFound:
                for t in listing:
                    if getattr(t, "is_translatable", False):
                        chosen = t.translate(languages[0])
                        break
        if chosen is None:
            raise TranscriptError("No usable transcript found in any requested language.")
        segments = _normalize(chosen.fetch())
        return _format_segments(segments, with_timestamps)
    except TranscriptsDisabled as e:
        raise TranscriptError("Captions are disabled for this video.") from e
    except VideoUnavailable as e:
        raise TranscriptError("Video is unavailable or private.") from e
    except TranscriptError:
        raise
    except Exception as e:
        log.warning("Primary transcript fetch failed (%s); trying yt-dlp fallback.", e)
        return _yt_dlp_fallback(video_id, languages, with_timestamps)


def _yt_dlp_fallback(video_id: str, languages: list[str], with_timestamps: bool) -> str:
    """Fallback chain when youtube-transcript-api fails: try pytubefix, then
    yt-dlp with multiple player clients to dodge YouTube's bot challenge."""
    errors: list[str] = []

    # 1. pytubefix — actively maintained fork that updates anti-bot bypasses.
    try:
        from pytubefix import YouTube  # type: ignore

        yt = YouTube(f"https://www.youtube.com/watch?v={video_id}")
        captions = yt.captions
        track = None
        for lang in languages:
            for key in (lang, f"a.{lang}"):
                if key in captions:
                    track = captions[key]
                    break
            if track:
                break
        if not track and captions:
            track = list(captions.values())[0]
        if track:
            xml = track.xml_captions
            import re as _re
            segments = []
            for m in _re.finditer(r'<text[^>]*start="([\d.]+)"[^>]*>([^<]*)</text>', xml):
                start = float(m.group(1))
                text = (m.group(2) or "").replace("&amp;", "&").replace("&#39;", "'").replace("&quot;", '"')
                if text.strip():
                    segments.append({"text": text.strip(), "start": start})
            if segments:
                return _format_segments(segments, with_timestamps)
    except Exception as e:
        errors.append(f"pytubefix: {e}")

    # 2. yt-dlp with multiple player_client values.
    try:
        import yt_dlp  # type: ignore
    except ImportError:
        raise TranscriptError(
            "All transcript fetchers failed. Errors:\n  "
            + "\n  ".join(errors + ["yt-dlp not installed"])
        )

    import json as _json
    import tempfile

    for client in ("ios", "android", "tv_simply", "mweb", "web"):
        with tempfile.TemporaryDirectory() as tmp:
            opts = {
                "skip_download": True,
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": languages,
                "subtitlesformat": "json3",
                "outtmpl": os.path.join(tmp, "%(id)s.%(ext)s"),
                "quiet": True,
                "no_warnings": True,
                "extractor_args": {"youtube": {"player_client": [client]}},
                "user_agent": (
                    "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Mobile Safari/537.36"
                ),
            }
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
            except Exception as e:
                errors.append(f"yt-dlp[{client}]: {e}")
                continue

            for fname in os.listdir(tmp):
                if fname.endswith(".json3"):
                    with open(os.path.join(tmp, fname), encoding="utf-8") as f:
                        data = _json.load(f)
                    segments = []
                    for ev in data.get("events", []):
                        if "segs" not in ev:
                            continue
                        text = "".join(s.get("utf8", "") for s in ev["segs"]).strip()
                        if text:
                            segments.append({"text": text, "start": ev.get("tStartMs", 0) / 1000})
                    if segments:
                        return _format_segments(segments, with_timestamps)
            errors.append(f"yt-dlp[{client}]: no subtitles in output")

    raise TranscriptError("All transcript fetchers failed:\n  " + "\n  ".join(errors))


# ============================================================================
# Section 3 — Browser voice-clone agent (Playwright) + ElevenLabs API fallback
# ============================================================================

def _local_tts(text: str, out_path: str) -> str:
    """Last-resort offline TTS via espeak-ng. Writes a WAV file at out_path
    (renaming .mp3 -> .wav since espeak-ng emits WAV)."""
    if not shutil.which("espeak-ng"):
        raise SynthesisError(
            "No TTS available: ElevenLabs API key not set, no browser session, "
            "and espeak-ng is not installed."
        )
    out = Path(out_path)
    if out.suffix.lower() != ".wav":
        out = out.with_suffix(".wav")
    out.parent.mkdir(parents=True, exist_ok=True)
    log.info("Synthesizing via espeak-ng -> %s", out)
    proc = subprocess.run(
        ["espeak-ng", "-w", str(out), text],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not out.exists():
        raise SynthesisError(f"espeak-ng failed: {proc.stderr.strip()}")
    return str(out)


SELECTORS = {
    "playht": {
        "login_url": "https://play.ht/app/login",
        "studio_url": "https://play.ht/studio/voice-cloning",
        "tts_url": "https://play.ht/studio",
        "email": 'input[type="email"]',
        "password": 'input[type="password"]',
        "submit": 'button[type="submit"]',
        "file_input": 'input[type="file"]',
        "voice_name": 'input[name="voice-name"], input[placeholder*="name" i]',
        "clone_submit": 'button:has-text("Clone")',
        "tts_textarea": 'textarea',
        "generate": 'button:has-text("Generate")',
        "download": 'button:has-text("Download"), a[download]',
    }
}


class VoiceCloner:
    """Context-managed Playwright voice cloner with ElevenLabs API shortcut."""

    def __init__(self, config: Config = CONFIG):
        self.config = config
        self._pw = None
        self._ctx = None
        self._page = None

    def __enter__(self):
        if self.config.elevenlabs_api_key:
            log.info("ElevenLabs API key present — browser will be skipped where possible.")
            return self
        try:
            self._start_browser()
        except VoiceCloneError as e:
            log.warning("Browser unavailable (%s); will fall back to local TTS.", e)
        return self

    def __exit__(self, *exc):
        if self._ctx:
            try:
                self._ctx.close()
            except Exception:
                pass
        if self._pw:
            try:
                self._pw.stop()
            except Exception:
                pass

    def _start_browser(self):
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except ImportError as e:
            raise VoiceCloneError(
                "playwright not installed. Run: pip install playwright && playwright install chromium"
            ) from e
        self.config.ensure_dirs()
        self._pw = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self.config.user_data_dir),
            headless=self.config.headless,
            accept_downloads=True,
        )
        self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()

    # ------------------------------------------------------------------ API path

    def _api_clone(self, sample_path: str) -> Optional[str]:
        if not self.config.elevenlabs_api_key:
            return None
        try:
            import requests
        except ImportError:
            return None
        log.info("Cloning voice via ElevenLabs API.")
        with open(sample_path, "rb") as f:
            r = requests.post(
                "https://api.elevenlabs.io/v1/voices/add",
                headers={"xi-api-key": self.config.elevenlabs_api_key},
                data={"name": f"clone_{uuid.uuid4().hex[:8]}"},
                files={"files": (Path(sample_path).name, f, "audio/mpeg")},
                timeout=120,
            )
        if r.status_code >= 400:
            raise VoiceCloneError(f"ElevenLabs clone failed: {r.status_code} {r.text}")
        return r.json().get("voice_id")

    def _api_synth(self, text: str, voice_id: str, out_path: str) -> Optional[str]:
        if not self.config.elevenlabs_api_key:
            return None
        try:
            import requests
        except ImportError:
            return None
        log.info("Synthesizing via ElevenLabs API: %r", text)
        r = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": self.config.elevenlabs_api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={"text": text, "model_id": "eleven_multilingual_v2"},
            timeout=120,
        )
        if r.status_code >= 400:
            raise SynthesisError(f"ElevenLabs synth failed: {r.status_code} {r.text}")
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(r.content)
        return out_path

    # -------------------------------------------------------------- Browser path

    def _check_captcha(self):
        if self._page.locator('iframe[src*="recaptcha"], iframe[src*="hcaptcha"]').count():
            raise CaptchaRequiredError("Captcha encountered — manual intervention required.")

    def _login_playht(self):
        sel = SELECTORS["playht"]
        if not (self.config.voice_service_email and self.config.voice_service_password):
            raise ConfigError("VOICE_SERVICE_EMAIL / VOICE_SERVICE_PASSWORD must be set.")
        self._page.goto(sel["login_url"], wait_until="domcontentloaded")
        if "/app" in self._page.url and "login" not in self._page.url:
            log.info("Already logged in (persistent session).")
            return
        self._check_captcha()
        self._page.fill(sel["email"], self.config.voice_service_email)
        self._page.fill(sel["password"], self.config.voice_service_password)
        self._page.click(sel["submit"])
        self._page.wait_for_url(re.compile(r".*/app.*"), timeout=30000)

    def _browser_clone(self, sample_path: str) -> str:
        sel = SELECTORS["playht"]
        self._login_playht()
        self._page.goto(sel["studio_url"], wait_until="domcontentloaded")
        self._check_captcha()
        name = f"clone_{uuid.uuid4().hex[:8]}"
        with self._page.expect_response(
            lambda r: "voice" in r.url and r.request.method == "POST", timeout=120000
        ) as resp_info:
            self._page.set_input_files(sel["file_input"], sample_path)
            try:
                self._page.fill(sel["voice_name"], name)
            except Exception:
                pass
            self._page.click(sel["clone_submit"])
        try:
            data = resp_info.value.json()
            voice_id = data.get("id") or data.get("voice_id") or name
        except Exception:
            voice_id = name
        log.info("Cloned voice id=%s", voice_id)
        return voice_id

    def _browser_synth(self, text: str, voice_id: str, out_path: str) -> str:
        sel = SELECTORS["playht"]
        self._page.goto(sel["tts_url"], wait_until="domcontentloaded")
        self._check_captcha()
        self._page.fill(sel["tts_textarea"], text)
        with self._page.expect_download(timeout=120000) as dl_info:
            self._page.click(sel["generate"])
            self._page.click(sel["download"])
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        dl_info.value.save_as(out_path)
        return out_path

    # ----------------------------------------------------------------- Public

    def clone_voice(self, sample_path: str) -> str:
        if not Path(sample_path).exists():
            raise ConfigError(f"Sample audio not found: {sample_path}")
        api = self._api_clone(sample_path)
        if api:
            return api
        if self._page is None:
            try:
                self._start_browser()
            except VoiceCloneError:
                log.warning("No browser available — returning local-tts pseudo voice id.")
                return "local-tts"
        return self._browser_clone(sample_path)

    def synthesize(self, text: str, voice_id: str, out_path: Optional[str] = None) -> str:
        out_path = out_path or str(self.config.output_dir / f"{uuid.uuid4().hex[:8]}.mp3")
        api = self._api_synth(text, voice_id, out_path)
        if api:
            return api
        if self._page is None:
            try:
                self._start_browser()
            except VoiceCloneError:
                return _local_tts(text, out_path)
        if voice_id == "local-tts":
            return _local_tts(text, out_path)
        return self._browser_synth(text, voice_id, out_path)


def clone_voice(sample_path: str) -> str:
    with VoiceCloner() as vc:
        return vc.clone_voice(sample_path)


def synthesize(text: str, voice_id: str, out_path: Optional[str] = None) -> str:
    with VoiceCloner() as vc:
        return vc.synthesize(text, voice_id, out_path)


# ============================================================================
# Demo / pipeline runners
# ============================================================================

def run_demo() -> str:
    """Canonical smoke test: clone (or reuse) voice and say 'hi Laurence'."""
    CONFIG.ensure_dirs()
    out_path = str(CONFIG.output_dir / "hi_laurence.mp3")
    with VoiceCloner() as vc:
        voice_id = CONFIG.default_voice_id
        if not voice_id:
            if not CONFIG.sample_voice_path:
                raise ConfigError("Set DEFAULT_VOICE_ID or SAMPLE_VOICE_PATH in .env")
            voice_id = vc.clone_voice(CONFIG.sample_voice_path)
        result = vc.synthesize("hi Laurence", voice_id, out_path)
    log.info("Demo audio written to %s", result)
    return result


def run_pipeline(url: str, voice_id: Optional[str] = None) -> str:
    """Full pipeline: transcript -> (optional truncate) -> synthesize."""
    CONFIG.ensure_dirs()
    transcript = get_transcript(url)
    log.info("Transcript length: %d chars", len(transcript))
    snippet = transcript[:500]
    with VoiceCloner() as vc:
        vid = voice_id or CONFIG.default_voice_id
        if not vid:
            if not CONFIG.sample_voice_path:
                raise ConfigError("Provide --voice-id, or set DEFAULT_VOICE_ID/SAMPLE_VOICE_PATH.")
            vid = vc.clone_voice(CONFIG.sample_voice_path)
        out_path = str(CONFIG.output_dir / f"pipeline_{_extract_video_id(url)}.mp3")
        return vc.synthesize(snippet, vid, out_path)


# ============================================================================
# Session bundle — desktop folder + auto-open + audio greeting
# ============================================================================

DESKTOP_DIR = Path(os.getenv("THECONSTRUCT_DESKTOP", str(Path.home() / "Desktop")))

WALKTHROUGH_TEXT = """\
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
"""


def _slugify(text: str, max_len: int = 50) -> str:
    text = re.sub(r"[^\w\s-]", "", text or "").strip()
    text = re.sub(r"[\s_-]+", "_", text)
    return (text[:max_len] or "untitled").strip("_")


def _get_video_title(url: str) -> Optional[str]:
    try:
        import yt_dlp  # type: ignore
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get("title")
    except Exception as e:
        log.debug("Could not fetch video title: %s", e)
        return None


def open_folder(path: Path) -> None:
    """Open a folder in the platform's file manager."""
    p = str(path)
    sysname = platform.system()
    try:
        if sysname == "Darwin":
            subprocess.run(["open", p], check=False)
        elif sysname == "Windows":
            os.startfile(p)  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", p], check=False)
    except Exception as e:
        log.warning("Could not open folder %s: %s", p, e)


def play_audio(path: Path) -> None:
    """Play an audio file using whatever player is available on this OS."""
    p = str(path)
    sysname = platform.system()
    try:
        if sysname == "Darwin":
            subprocess.Popen(["afplay", p])
            return
        if sysname == "Windows":
            os.startfile(p)  # type: ignore[attr-defined]
            return
        for player in ("ffplay", "mpg123", "paplay", "aplay", "xdg-open"):
            if shutil.which(player):
                args = [player, "-nodisp", "-autoexit", p] if player == "ffplay" else [player, p]
                subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
    except Exception as e:
        log.warning("Could not play audio %s: %s", p, e)


def _render_bundle_readme(meta: dict) -> str:
    audio = meta.get("audio_file") or "(none — synthesis skipped)"
    err = meta.get("transcript_error")
    err_line = f"- Transcript error: {err}\n" if err else ""
    return (
        f"# {meta.get('title') or meta['video_id']}\n\n"
        f"Created: {meta['created_at']}\n\n"
        f"- URL: {meta['url']}\n"
        f"- Video ID: {meta['video_id']}\n"
        f"- Voice ID: {meta.get('voice_id') or '(none — synthesis skipped)'}\n"
        f"- Audio file: {audio}\n"
        f"- Transcript length: {meta['transcript_chars']} chars\n"
        f"{err_line}\n"
        f"## Files\n"
        f"- `transcript.txt` — plain transcript\n"
        f"- `transcript-timestamped.txt` — with timestamps\n"
        f"- `{audio}` — greeting audio\n"
        f"- `metadata.json` — machine-readable details\n"
        f"- `run.py` — re-runnable script for this URL\n"
        f"- `WALKTHROUGH.md` — how the system works\n"
    )


def _render_run_script(url: str) -> str:
    return (
        '"""Re-run this exact bundle. Generated by TheConstruct."""\n'
        "from theconstruct import create_session_bundle\n\n"
        f'URL = {url!r}\n\n'
        'if __name__ == "__main__":\n'
        '    create_session_bundle(URL)\n'
    )


def create_session_bundle(
    url: str,
    voice_id: Optional[str] = None,
    open_when_done: bool = True,
    play_when_done: bool = True,
) -> Path:
    """Run the full pipeline and bundle results into a Desktop folder."""
    CONFIG.ensure_dirs()
    DESKTOP_DIR.mkdir(parents=True, exist_ok=True)

    video_id = _extract_video_id(url)
    title = _get_video_title(url)
    title_slug = _slugify(title) if title else video_id
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    bundle = DESKTOP_DIR / f"TheConstruct__{title_slug}__{stamp}"
    bundle.mkdir(parents=True, exist_ok=True)
    log.info("Creating bundle: %s", bundle)

    transcript = ""
    transcript_ts = ""
    transcript_error: Optional[str] = None
    try:
        transcript = get_transcript(url)
        transcript_ts = get_transcript(url, with_timestamps=True)
    except Exception as e:
        transcript_error = f"{type(e).__name__}: {e}"
        log.warning("Transcript fetch failed: %s", transcript_error)
        transcript = (
            f"[Transcript unavailable: {transcript_error}]\n"
            f"URL: {url}\n"
            "Run `python theconstruct.py transcript <url>` from a network where\n"
            "YouTube is reachable to populate this file.\n"
        )
        transcript_ts = transcript

    (bundle / "transcript.txt").write_text(transcript, encoding="utf-8")
    (bundle / "transcript-timestamped.txt").write_text(transcript_ts, encoding="utf-8")

    audio_path: Optional[Path] = None
    used_voice_id: Optional[str] = None
    with VoiceCloner() as vc:
        vid = voice_id or CONFIG.default_voice_id
        if not vid:
            if CONFIG.sample_voice_path and Path(CONFIG.sample_voice_path).exists():
                try:
                    vid = vc.clone_voice(CONFIG.sample_voice_path)
                except Exception as e:
                    log.warning("Voice clone failed: %s", e)
            else:
                # No api key, no sample — try local TTS directly.
                vid = "local-tts"
        try:
            produced = vc.synthesize("hi Laurence", vid, str(bundle / "hello.mp3"))
            audio_path = Path(produced)
            used_voice_id = vid
        except Exception as e:
            log.warning("Synthesis failed: %s", e)

    meta = {
        "url": url,
        "video_id": video_id,
        "title": title,
        "voice_id": used_voice_id,
        "audio_file": audio_path.name if audio_path else None,
        "transcript_error": transcript_error,
        "created_at": stamp,
        "transcript_chars": len(transcript),
    }
    (bundle / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (bundle / "README.md").write_text(_render_bundle_readme(meta), encoding="utf-8")
    (bundle / "run.py").write_text(_render_run_script(url), encoding="utf-8")
    (bundle / "WALKTHROUGH.md").write_text(WALKTHROUGH_TEXT, encoding="utf-8")

    if play_when_done and audio_path and audio_path.exists():
        play_audio(audio_path)
    if open_when_done:
        open_folder(bundle)

    log.info("Bundle ready: %s", bundle)
    return bundle


# ============================================================================
# CLI
# ============================================================================

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="theconstruct", description=__doc__)
    sub = p.add_subparsers(dest="cmd")

    t = sub.add_parser("transcript", help="Print a YouTube transcript.")
    t.add_argument("url")
    t.add_argument("--timestamps", action="store_true")

    c = sub.add_parser("clone", help="Clone a voice from an audio sample.")
    c.add_argument("sample")

    s = sub.add_parser("say", help="Synthesize text with a cloned voice.")
    s.add_argument("text")
    s.add_argument("--voice-id")
    s.add_argument("--out")

    pl = sub.add_parser("pipeline", help="Transcript -> synthesize.")
    pl.add_argument("url")
    pl.add_argument("--voice-id")

    b = sub.add_parser("bundle", help="Create a Desktop session bundle for a URL.")
    b.add_argument("url")
    b.add_argument("--voice-id")
    b.add_argument("--no-open", action="store_true")
    b.add_argument("--no-play", action="store_true")

    sub.add_parser("demo", help='Smoke test: synthesize "hi Laurence".')
    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    # Bare URL shortcut: `python theconstruct.py <url>` -> pipeline
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] not in {"transcript", "clone", "say", "pipeline", "bundle", "demo", "-h", "--help"}:
        argv = ["bundle", *argv]
    args = parser.parse_args(argv)

    try:
        if args.cmd == "transcript":
            print(get_transcript(args.url, with_timestamps=args.timestamps))
        elif args.cmd == "clone":
            print(clone_voice(args.sample))
        elif args.cmd == "say":
            vid = args.voice_id or CONFIG.default_voice_id
            if not vid:
                raise ConfigError("--voice-id or DEFAULT_VOICE_ID is required.")
            print(synthesize(args.text, vid, args.out))
        elif args.cmd == "pipeline":
            print(run_pipeline(args.url, args.voice_id))
        elif args.cmd == "bundle":
            print(create_session_bundle(
                args.url,
                voice_id=args.voice_id,
                open_when_done=not args.no_open,
                play_when_done=not args.no_play,
            ))
        elif args.cmd == "demo":
            print(run_demo())
        else:
            parser.print_help()
            return 1
        return 0
    except tuple(EXIT_CODES.keys()) as e:
        log.error("%s: %s", type(e).__name__, e)
        log.debug("trace", exc_info=True)
        return EXIT_CODES[type(e)]
    except Exception as e:
        log.exception("Unexpected error: %s", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
