#!/usr/bin/env python3
"""Dependency/capability checker for ai-agent-video-viewer."""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
from pathlib import Path

WHISPER_CANDIDATES = ["whisper-cli", "whisper-cpp"]


def binary_ok(name: str) -> bool:
    path = shutil.which(name)
    if not path:
        return False
    try:
        result = subprocess.run([path, "-version" if name.startswith("ff") else "--version"], capture_output=True, text=True, timeout=10)
        return result.returncode in (0, 1)
    except Exception:
        return False


def find_whisper() -> str | None:
    for name in WHISPER_CANDIDATES:
        path = shutil.which(name)
        if not path:
            continue
        try:
            result = subprocess.run([path, "--help"], capture_output=True, text=True, timeout=10)
        except Exception:
            continue
        text = f"{result.stdout}\n{result.stderr}".lower()
        if result.returncode in (0, 1) and ("whisper" in text or "-oj" in text or "--output-json" in text):
            return path
    return None


def status() -> dict:
    repo_root = Path(__file__).resolve().parents[1]
    home = Path.home()
    ffmpeg = binary_ok("ffmpeg")
    ffprobe = binary_ok("ffprobe")
    ytdlp = binary_ok("yt-dlp")
    whisper = find_whisper()
    return {
        "platform": platform.system(),
        "python_hint_windows": "Use python instead of python3 if python3 is the Microsoft Store stub.",
        "binaries": {
            "ffmpeg": shutil.which("ffmpeg"),
            "ffprobe": shutil.which("ffprobe"),
            "yt-dlp": shutil.which("yt-dlp"),
            "whisper": whisper,
        },
        "capabilities": {
            "local_media_metadata": ffmpeg and ffprobe,
            "local_video_frames": ffmpeg and ffprobe,
            "url_download": ffmpeg and ffprobe and ytdlp,
            "local_transcription": ffmpeg and ffprobe and bool(whisper),
            "full": ffmpeg and ffprobe and ytdlp and bool(whisper),
        },
        "claude_code": {
            "binary": shutil.which("claude"),
            "standalone_skill": str(home / ".claude" / "skills" / "ai-agent-video-viewer"),
            "standalone_skill_installed": (home / ".claude" / "skills" / "ai-agent-video-viewer" / "SKILL.md").exists(),
            "plugin_dir": str(home / "claude-plugins" / "ai-agent-video-viewer"),
            "plugin_dir_installed": (home / "claude-plugins" / "ai-agent-video-viewer" / ".claude-plugin" / "plugin.json").exists(),
        },
        "install": {
            "one_command": "python3 scripts/install.py --force",
            "macos_full_bootstrap": "python3 scripts/install.py --install-homebrew --force",
            "remote_bootstrap": "curl -fsSL https://raw.githubusercontent.com/AnshRajput/ai-agent-video-viewer/main/install.sh | bash -s -- --force",
            "macos_manual": "brew install ffmpeg yt-dlp whisper-cpp",
            "debian_ubuntu_manual": "sudo apt-get update && sudo apt-get install -y ffmpeg yt-dlp git cmake build-essential  # install.py can build whisper.cpp",
            "windows_manual": "Install ffmpeg, yt-dlp, and whisper.cpp; ensure ffmpeg, ffprobe, yt-dlp, and whisper-cli are on PATH.",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Check dependencies for ai-agent-video-viewer")
    ap.add_argument("--check", action="store_true", help="exit non-zero unless full URL+transcription capability is available")
    ap.add_argument("--check-local", action="store_true", help="exit non-zero unless local media frame/metadata capability is available")
    ap.add_argument("--check-transcription", action="store_true", help="exit non-zero unless local transcription capability is available")
    ap.add_argument("--json", action="store_true", help="print JSON status")
    args = ap.parse_args()

    data = status()
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print("ai-agent-video-viewer capability status")
        for key, value in data["capabilities"].items():
            print(f"- {key}: {'yes' if value else 'no'}")
        print("\nClaude Code:")
        for key, value in data["claude_code"].items():
            print(f"- {key}: {value}")
        if not data["capabilities"]["full"]:
            print("\nInstall hints:")
            for os_name, hint in data["install"].items():
                print(f"- {os_name}: {hint}")

    if args.check and not data["capabilities"]["full"]:
        return 2
    if args.check_local and not data["capabilities"]["local_video_frames"]:
        return 2
    if args.check_transcription and not data["capabilities"]["local_transcription"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
