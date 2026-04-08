"""TheConstruct tray app — clipboard-driven YouTube bundler.

Runs a system-tray icon. Watches the clipboard; when a YouTube URL appears
it asks for confirmation, then runs the full pipeline and pops the bundle
folder open on the Desktop.

Usage:
    python tray.py
"""

from __future__ import annotations

import logging
import re
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog

from theconstruct import (
    CONFIG,
    WALKTHROUGH_TEXT,
    create_session_bundle,
    open_folder,
)

log = logging.getLogger("theconstruct.tray")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

YOUTUBE_RE = re.compile(
    r"https?://(?:www\.)?(?:youtube\.com/(?:watch\?v=|shorts/|embed/|live/)|youtu\.be/)[\w-]{11}\S*"
)

STATE_DIR = Path.home() / ".config" / "theconstruct"
STATE_DIR.mkdir(parents=True, exist_ok=True)
SEEN_WALKTHROUGH = STATE_DIR / "seen_walkthrough"
LAST_BUNDLE_FILE = STATE_DIR / "last_bundle"


# ----------------------------------------------------------------------- icon

def _make_icon_image(size: int = 64):
    from PIL import Image, ImageDraw  # type: ignore

    img = Image.new("RGBA", (size, size), (15, 15, 25, 255))
    d = ImageDraw.Draw(img)
    d.ellipse((6, 6, size - 6, size - 6), fill=(80, 200, 255, 255))
    d.text((size // 2 - 9, size // 2 - 9), "TC", fill=(15, 15, 25, 255))
    return img


# ------------------------------------------------------------------ walkthrough

def show_walkthrough() -> None:
    """Display the walkthrough in a Tk window."""
    root = tk.Tk()
    root.title("TheConstruct — Walkthrough")
    root.geometry("620x540")
    txt = tk.Text(root, wrap="word", padx=14, pady=14, font=("TkDefaultFont", 11))
    txt.insert("1.0", WALKTHROUGH_TEXT)
    txt.config(state="disabled")
    txt.pack(fill="both", expand=True)
    tk.Button(root, text="Close", command=root.destroy, padx=20, pady=4).pack(pady=10)
    root.mainloop()


# ------------------------------------------------------------------- tray app

class TrayApp:
    def __init__(self) -> None:
        import pystray  # type: ignore

        self._pystray = pystray
        self.icon = pystray.Icon(
            "theconstruct",
            _make_icon_image(),
            "TheConstruct",
            menu=pystray.Menu(
                pystray.MenuItem("Process clipboard URL", self.on_process_clipboard),
                pystray.MenuItem("Process URL...", self.on_prompt_url),
                pystray.MenuItem("Open last bundle", self.on_open_last),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Walkthrough", self.on_walkthrough),
                pystray.MenuItem("Quit", self.on_quit),
            ),
        )
        self._last_clipboard = ""
        self._stop = threading.Event()

    # ---------- helpers

    def _notify(self, msg: str) -> None:
        log.info(msg)
        try:
            self.icon.notify(msg, "TheConstruct")
        except Exception:
            pass

    def _process(self, url: str) -> None:
        self._notify(f"Processing {url}")
        try:
            bundle = create_session_bundle(url)
            LAST_BUNDLE_FILE.write_text(str(bundle))
            self._notify(f"Done: {bundle.name}")
        except Exception as e:
            log.exception("Pipeline failed")
            self._notify(f"Failed: {type(e).__name__}: {e}")

    def _read_clipboard(self) -> str:
        try:
            import pyperclip  # type: ignore
            return pyperclip.paste() or ""
        except Exception:
            return ""

    # ---------- menu callbacks

    def on_process_clipboard(self, _icon=None, _item=None) -> None:
        m = YOUTUBE_RE.search(self._read_clipboard())
        if not m:
            self._notify("No YouTube URL on clipboard.")
            return
        threading.Thread(target=self._process, args=(m.group(0),), daemon=True).start()

    def on_prompt_url(self, _icon=None, _item=None) -> None:
        def ask():
            root = tk.Tk()
            root.withdraw()
            url = simpledialog.askstring("TheConstruct", "Paste YouTube URL:", parent=root)
            root.destroy()
            if url:
                m = YOUTUBE_RE.search(url)
                if m:
                    self._process(m.group(0))
                else:
                    self._notify("That doesn't look like a YouTube URL.")

        threading.Thread(target=ask, daemon=True).start()

    def on_open_last(self, _icon=None, _item=None) -> None:
        if LAST_BUNDLE_FILE.exists():
            p = Path(LAST_BUNDLE_FILE.read_text().strip())
            if p.exists():
                open_folder(p)
                return
        self._notify("No bundles yet.")

    def on_walkthrough(self, _icon=None, _item=None) -> None:
        threading.Thread(target=show_walkthrough, daemon=True).start()

    def on_quit(self, _icon=None, _item=None) -> None:
        self._stop.set()
        self.icon.stop()

    # ---------- clipboard watcher

    def _watch_clipboard(self) -> None:
        try:
            import pyperclip  # noqa: F401
        except ImportError:
            log.warning("pyperclip not installed; clipboard watcher disabled.")
            return

        # Seed with current value so we don't fire on whatever was already copied.
        self._last_clipboard = self._read_clipboard()

        while not self._stop.is_set():
            try:
                cur = self._read_clipboard()
                if cur and cur != self._last_clipboard:
                    self._last_clipboard = cur
                    m = YOUTUBE_RE.search(cur)
                    if m and self._confirm_process(m.group(0)):
                        threading.Thread(target=self._process, args=(m.group(0),), daemon=True).start()
            except Exception as e:
                log.debug("clipboard tick error: %s", e)
            time.sleep(1.0)

    def _confirm_process(self, url: str) -> bool:
        result = {"ok": False}

        def ask():
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            result["ok"] = messagebox.askyesno(
                "TheConstruct",
                f"Detected a YouTube URL on your clipboard.\n\n{url}\n\nProcess it?",
                parent=root,
            )
            root.destroy()

        t = threading.Thread(target=ask)
        t.start()
        t.join(timeout=60)
        return result["ok"]

    # ---------- run

    def run(self) -> None:
        threading.Thread(target=self._watch_clipboard, daemon=True).start()
        if not SEEN_WALKTHROUGH.exists():
            threading.Thread(target=show_walkthrough, daemon=True).start()
            SEEN_WALKTHROUGH.write_text("seen")
        log.info("TheConstruct tray running. Right-click the tray icon for the menu.")
        self.icon.run()


def main() -> int:
    try:
        TrayApp().run()
    except ImportError as e:
        print(
            f"Missing dependency: {e}\n"
            "Install with: pip install pystray Pillow pyperclip",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
