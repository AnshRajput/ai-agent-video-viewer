#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys

REQUIRED = ["ffmpeg", "ffprobe", "yt-dlp"]
WHISPER_CANDIDATES = ["whisper-cli", "whisper-cpp", "main"]


def find_whisper() -> str | None:
    for name in WHISPER_CANDIDATES:
        path = shutil.which(name)
        if path:
            return path
    return None


def status() -> dict:
    missing = [name for name in REQUIRED if shutil.which(name) is None]
    whisper = find_whisper()
    return {
        "ready": not missing and bool(whisper),
        "platform": platform.system(),
        "missing_binaries": missing,
        "whisper_binary": whisper,
        "has_local_transcription": bool(whisper),
        "install_hint_macos": "brew install ffmpeg yt-dlp whisper-cpp",
        "install_hint_debian": "sudo apt-get update && sudo apt-get install -y ffmpeg yt-dlp  # then install whisper.cpp/whisper-cli",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Check dependencies for ansh-media-watch")
    ap.add_argument("--check", action="store_true", help="exit non-zero if required tools are missing")
    ap.add_argument("--json", action="store_true", help="print JSON status")
    args = ap.parse_args()

    data = status()
    if args.json:
        print(json.dumps(data, indent=2))
    elif not data["ready"]:
        print("ansh-media-watch setup needs attention:", file=sys.stderr)
        if data["missing_binaries"]:
            print(f"missing: {', '.join(data['missing_binaries'])}", file=sys.stderr)
        if not data["whisper_binary"]:
            print("missing: whisper-cli (from whisper.cpp)", file=sys.stderr)
        print(f"macOS: {data['install_hint_macos']}", file=sys.stderr)
        print(f"Debian/Ubuntu: {data['install_hint_debian']}", file=sys.stderr)
    else:
        print("ansh-media-watch setup OK")

    if args.check and not data["ready"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
