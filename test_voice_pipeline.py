"""Smoke test for the voice pipeline.

Clones a voice from a sample and synthesizes "hi Laurence", asserting the
resulting audio file exists and is non-trivial in size.

Run:
    python test_voice_pipeline.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from theconstruct import (
    CONFIG,
    ConfigError,
    VoiceCloner,
    clone_voice,
    synthesize,
)


def main() -> int:
    CONFIG.ensure_dirs()
    out_path = Path(CONFIG.output_dir) / "hi_laurence.mp3"

    voice_id = CONFIG.default_voice_id
    sample = CONFIG.sample_voice_path

    print(f"[test] output_dir = {CONFIG.output_dir}")
    print(f"[test] default_voice_id = {voice_id!r}")
    print(f"[test] sample_voice_path = {sample!r}")

    with VoiceCloner() as vc:
        if not voice_id:
            if not sample or not Path(sample).exists():
                raise ConfigError(
                    "Set DEFAULT_VOICE_ID, or SAMPLE_VOICE_PATH pointing to an existing audio file."
                )
            print("[test] cloning voice from sample...")
            voice_id = vc.clone_voice(sample)
            print(f"[test] cloned voice_id = {voice_id}")

        print('[test] synthesizing "hi Laurence"...')
        result = vc.synthesize("hi Laurence", voice_id, str(out_path))

    assert isinstance(result, str), "synthesize() must return a path string"
    assert os.path.exists(result), f"audio file not produced at {result}"
    size = os.path.getsize(result)
    assert size > 1024, f"audio file suspiciously small ({size} bytes)"

    print(f"[test] OK — wrote {size} bytes to {result}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:
        print(f"[test] FAIL: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[test] ERROR: {type(e).__name__}: {e}")
        sys.exit(2)
