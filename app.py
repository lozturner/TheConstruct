"""TheConstruct local web app.

Runs a tiny HTTP server on http://localhost:7117/. Paste a YouTube URL
into the box, hit Go, and you get a transcript + cloned-voice greeting +
a bundle folder on your Desktop. No CLI, no tray, no clicking around.

Usage:
    python app.py                    # starts server + opens browser
    python app.py --no-open          # starts without opening browser
    python app.py --port 8000        # custom port
"""

from __future__ import annotations

import argparse
import html
import http.server
import json
import logging
import mimetypes
import socketserver
import sys
import threading
import time
import traceback
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Optional

from theconstruct import (
    CONFIG,
    DESKTOP_DIR,
    create_session_bundle,
    log as tc_log,
)

PORT_DEFAULT = 7117

INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TheConstruct</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh;
    background: radial-gradient(ellipse at top, #1a1f3a 0%, #0a0c18 70%);
    color: #e6e9f2; font-family: -apple-system, Segoe UI, Roboto, sans-serif;
    display: flex; flex-direction: column; align-items: center;
    padding: 48px 20px;
  }
  h1 { font-weight: 600; letter-spacing: -0.02em; margin: 0 0 4px; font-size: 28px; }
  .sub { color: #8a93a8; margin-bottom: 32px; font-size: 14px; }
  .card {
    width: 100%; max-width: 720px; background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08); border-radius: 14px;
    padding: 24px; box-shadow: 0 20px 60px rgba(0,0,0,0.4);
  }
  .row { display: flex; gap: 10px; }
  input[type=text] {
    flex: 1; padding: 13px 14px; border-radius: 10px;
    border: 1px solid rgba(255,255,255,0.12); background: rgba(0,0,0,0.3);
    color: #fff; font-size: 15px; outline: none;
  }
  input[type=text]:focus { border-color: #50c8ff; }
  button {
    padding: 13px 22px; border-radius: 10px; border: 0;
    background: linear-gradient(180deg, #5ad1ff, #3ba5d6); color: #071325;
    font-weight: 600; font-size: 15px; cursor: pointer;
  }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .status {
    margin-top: 18px; padding: 12px 14px; border-radius: 10px;
    background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.06);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 13px; white-space: pre-wrap; color: #9db3cc;
    min-height: 18px;
  }
  .result { margin-top: 24px; display: none; }
  .result.show { display: block; }
  .result h3 { margin: 0 0 10px; font-size: 14px; color: #8a93a8; text-transform: uppercase; letter-spacing: 0.08em; }
  .transcript {
    max-height: 280px; overflow: auto; background: rgba(0,0,0,0.3);
    padding: 14px 16px; border-radius: 10px; font-size: 14px; line-height: 1.55;
    border: 1px solid rgba(255,255,255,0.06);
  }
  audio { width: 100%; margin-top: 14px; }
  .meta { margin-top: 14px; font-size: 13px; color: #8a93a8; }
  .meta a { color: #5ad1ff; text-decoration: none; }
  .meta a:hover { text-decoration: underline; }
  .err { color: #ff7a7a; }
  .spinner {
    display: inline-block; width: 14px; height: 14px; border-radius: 50%;
    border: 2px solid rgba(255,255,255,0.15); border-top-color: #5ad1ff;
    animation: spin 0.9s linear infinite; vertical-align: -2px; margin-right: 8px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
  <h1>TheConstruct</h1>
  <div class="sub">YouTube link in. Desktop folder out.</div>

  <div class="card">
    <form id="f" class="row" onsubmit="return go(event)">
      <input id="url" type="text" placeholder="Paste a YouTube URL…" autofocus>
      <button id="b" type="submit">Go</button>
    </form>
    <div id="status" class="status">Ready.</div>

    <div id="result" class="result">
      <h3>Greeting</h3>
      <audio id="audio" controls></audio>

      <h3 style="margin-top:22px">Transcript</h3>
      <div id="transcript" class="transcript"></div>

      <div class="meta" id="meta"></div>
    </div>
  </div>

<script>
async function go(ev) {
  ev.preventDefault();
  const url = document.getElementById('url').value.trim();
  if (!url) return false;
  const btn = document.getElementById('b');
  const status = document.getElementById('status');
  const result = document.getElementById('result');
  btn.disabled = true;
  result.classList.remove('show');
  status.innerHTML = '<span class="spinner"></span>Working… fetching transcript, cloning voice, building bundle.';
  try {
    const res = await fetch('/bundle', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url})
    });
    const data = await res.json();
    if (!res.ok || data.error) {
      status.innerHTML = '<span class="err">Failed: ' + (data.error || res.status) + '</span>';
    } else {
      status.textContent = 'Bundle ready: ' + data.bundle_name;
      document.getElementById('transcript').textContent = data.transcript || '(no transcript)';
      const audio = document.getElementById('audio');
      if (data.audio_url) {
        audio.src = data.audio_url;
        audio.style.display = '';
        audio.play().catch(()=>{});
      } else {
        audio.style.display = 'none';
      }
      document.getElementById('meta').innerHTML =
        'Folder: <a href="/open?bundle=' + encodeURIComponent(data.bundle_name) + '" target="_blank">' + data.bundle_path + '</a>' +
        ' &middot; <a href="/file?bundle=' + encodeURIComponent(data.bundle_name) + '&name=transcript.txt">transcript.txt</a>' +
        (data.audio_url ? ' &middot; <a href="' + data.audio_url + '" download>download audio</a>' : '');
      result.classList.add('show');
    }
  } catch (e) {
    status.innerHTML = '<span class="err">Network error: ' + e + '</span>';
  } finally {
    btn.disabled = false;
  }
  return false;
}
</script>
</body>
</html>
"""


def _json_response(handler, obj, status=200):
    body = json.dumps(obj).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _find_bundle(name: str) -> Optional[Path]:
    p = DESKTOP_DIR / name
    if p.exists() and p.is_dir() and p.resolve().is_relative_to(DESKTOP_DIR.resolve()):
        return p
    return None


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        tc_log.info("http %s - %s", self.address_string(), format % args)

    # ---- GET ----
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            body = INDEX_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        q = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/file":
            name = (q.get("name") or [""])[0]
            bundle = _find_bundle((q.get("bundle") or [""])[0])
            if not bundle:
                self.send_error(404, "bundle not found"); return
            fp = (bundle / name).resolve()
            if not fp.is_file() or not fp.is_relative_to(bundle.resolve()):
                self.send_error(404, "file not found"); return
            mime = mimetypes.guess_type(fp.name)[0] or "application/octet-stream"
            data = fp.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Disposition", f'inline; filename="{fp.name}"')
            self.end_headers()
            self.wfile.write(data)
            return

        if parsed.path == "/open":
            from theconstruct import open_folder
            bundle = _find_bundle((q.get("bundle") or [""])[0])
            if bundle:
                open_folder(bundle)
            self.send_response(204)
            self.end_headers()
            return

        self.send_error(404, "not found")

    # ---- POST ----
    def do_POST(self):
        if self.path != "/bundle":
            self.send_error(404, "not found"); return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw.decode("utf-8") or "{}")
            url = (payload.get("url") or "").strip()
            if not url:
                _json_response(self, {"error": "missing url"}, 400); return

            tc_log.info("web: bundling %s", url)
            bundle = create_session_bundle(
                url,
                open_when_done=False,  # user clicks "open folder" link in UI
                play_when_done=False,  # audio plays in the <audio> element
            )

            transcript = ""
            tp = bundle / "transcript.txt"
            if tp.exists():
                transcript = tp.read_text(encoding="utf-8", errors="ignore")

            audio_name = None
            for candidate in ("hello.mp3", "hello.wav"):
                if (bundle / candidate).exists():
                    audio_name = candidate
                    break

            _json_response(self, {
                "bundle_name": bundle.name,
                "bundle_path": str(bundle),
                "transcript": transcript,
                "audio_url": (
                    f"/file?bundle={urllib.parse.quote(bundle.name)}&name={audio_name}"
                    if audio_name else None
                ),
            })
        except Exception as e:
            tc_log.exception("web bundle failed")
            _json_response(self, {"error": f"{type(e).__name__}: {e}"}, 500)


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=PORT_DEFAULT)
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()

    CONFIG.ensure_dirs()
    DESKTOP_DIR.mkdir(parents=True, exist_ok=True)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://localhost:{args.port}/"
    print(f"TheConstruct running at {url}  (Ctrl-C to quit)")
    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
        server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
