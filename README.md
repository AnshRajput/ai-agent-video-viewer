<div align="center">

# 🎬 AI Agent Video Viewer

**Give any AI agent eyes and ears for video and audio.**

A portable, harness-neutral skill that lets an agent *watch* video, *listen* to audio,
extract frames, and transcribe or translate speech to English — then answer questions
grounded in timestamped evidence.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Runtime deps](https://img.shields.io/badge/runtime%20deps-stdlib%20only-success.svg)](#design-principles)
[![Transcription](https://img.shields.io/badge/transcription-local%20whisper.cpp-success.svg)](#how-it-works)
[![Platforms](https://img.shields.io/badge/platforms-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg)](#requirements)

</div>

---

## Table of contents

- [Overview](#overview)
- [Why it exists](#why-it-exists)
- [Features](#features)
- [How it works](#how-it-works)
- [Harness compatibility](#harness-compatibility)
- [Requirements](#requirements)
- [Installation](#installation)
  - [One-command install](#one-command-install)
  - [Install into any agent harness](#install-into-any-agent-harness)
  - [MCP server (Cursor, Windsurf, Cline, Continue, Codex…)](#mcp-server)
- [Usage](#usage)
- [Output artifacts](#output-artifacts)
- [Command-line reference](#command-line-reference)
- [Multi-agent handoff](#multi-agent-handoff)
- [Security and privacy](#security-and-privacy)
- [Design principles](#design-principles)
- [Development and testing](#development-and-testing)
- [Repository layout](#repository-layout)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Overview

Large language models cannot natively open a video URL, scrub through frames, or
decode an audio track. **AI Agent Video Viewer** closes that gap with a single,
self-contained pipeline that any shell-capable agent can drive:

1. **Acquire** — download a URL with `yt-dlp`, or copy a local file into a sandboxed
   working directory.
2. **See** — extract auto-scaled frames with `ffmpeg`, plus a contact sheet and a
   timestamped frame manifest for fast visual inspection.
3. **Hear** — transcribe speech locally with `whisper.cpp`, and optionally translate
   it to English — no cloud API, no audio ever leaves the machine.
4. **Report** — write `report.md` + `result.json` that any agent can read, with every
   claim anchored to a source timestamp.

The implementation is deliberately harness-neutral: a Markdown skill plus a Python
CLI plus an optional MCP server. It runs the same in Claude Code, Cursor, Hermes,
Codex, OpenCode, or a bare shell.

## Why it exists

| Problem | This skill's answer |
| --- | --- |
| Agents can't watch video or hear audio | A single CLI turns any media into frames + a timestamped transcript |
| Cloud transcription leaks sensitive audio | Transcription is **local** via `whisper.cpp` — audio never leaves the machine |
| Every harness has a different "skill" format | One portable core + an MCP server that *every* MCP client auto-discovers |
| Agents hallucinate visual detail | Outputs separate verified evidence from speculation and demand timestamp citations |
| Unattended agents are an SSRF / disk-fill risk | Private-network URLs, oversized media, and long media are refused by default |

## Features

- 🎥 **Video understanding** — frame extraction, contact sheet, and a frame manifest with approximate source timestamps.
- 🎙️ **Local transcription & translation** — offline `whisper.cpp`; translate any language to English with one flag.
- 🔗 **URL or local** — `yt-dlp` for the web, direct file processing for local media; audio-only inputs skip frames automatically.
- 🎯 **Focused ranges** — analyze just `01:20 → 02:10` of a long video for speed and precision.
- 🧩 **Universal integration** — Markdown skill, portable CLI, and a zero-dependency MCP server.
- 🛡️ **Safe by default** — SSRF guard, size/duration caps, sandboxed output directory, graceful partial-failure handling.
- 📦 **Self-contained** — standard-library Python at runtime; the only externals are the media binaries themselves.

## How it works

```
            ┌──────────────────────────── media_watch.py ────────────────────────────┐
 source ──▶ │  acquire ──▶ probe ──▶ extract frames ─┐                                 │
 (URL or    │  (yt-dlp/   (ffprobe)  (ffmpeg)         ├─▶ report.md + result.json ──▶  │ ──▶ agent
  local)    │   copy)                 extract audio ──┘    transcript + frames +       │     answers
            │                         (ffmpeg) ──▶ transcribe/translate (whisper.cpp)  │
            └─────────────────────────────────────────────────────────────────────────┘
```

The agent never has to parse stdout heuristics: `result.json` is the machine-readable
contract, `report.md` is the human-readable view, and frames are referenced by path
(and, over MCP, returned inline as an image).

> The first transcription downloads the selected `whisper.cpp` model from Hugging Face
> into `~/.cache/whisper/`. Every transcription after that is fully offline.

## Harness compatibility

| Harness | Integration | Install |
| --- | --- | --- |
| **Claude Code** (CLI / app / IDE) | Native skill **and** MCP server | `install.py` registers `~/.claude/skills/…`; or add the MCP server |
| **Cursor / Windsurf / Cline / Continue** | MCP server | `mcp_server.py --print-config` → paste into the client's MCP config |
| **Codex** | MCP server, or read `SKILL.md` + run the CLI | MCP config (TOML), or point the agent at `SKILL.md` |
| **OpenCode** | MCP server, or `--target` skill dir | MCP config, or `install.py --target …` |
| **Hermes Agent** | File-based skill | `install.py --target ~/.hermes/skills/…` |
| **Any shell-capable agent** | Portable CLI + Markdown | Read `SKILL.md`, run `scripts/media_watch.py` |

There is no universal skill-file format across harnesses, so coverage rests on two
universal interfaces: the **portable CLI** (works anywhere a shell does) and **MCP**
(the one registration standard every modern client supports).

## Requirements

| Tool | Needed for |
| --- | --- |
| Python 3.9+ | Running the scripts, installer, and MCP server |
| ffmpeg | Frame and audio extraction |
| ffprobe | Media metadata |
| yt-dlp | URL downloads |
| whisper.cpp (`whisper-cli`) | Local transcription and English translation |
| Claude Code CLI *(optional)* | Native Claude Code skill usage |

Only the media binaries are external. The Python code itself uses the standard
library exclusively — no `pip install` step, no virtualenv.

## Installation

Canonical repository: `https://github.com/AnshRajput/ai-agent-video-viewer`

### One-command install

Installs the media toolchain and registers the skill with Claude Code (as both a
user skill and a plugin-style directory):

```bash
git clone https://github.com/AnshRajput/ai-agent-video-viewer.git \
  ~/.local/share/ai-agent-video-viewer/source
cd ~/.local/share/ai-agent-video-viewer/source
python3 scripts/install.py --force
```

Platform behavior:

- **macOS** — uses Homebrew: `brew install ffmpeg yt-dlp whisper-cpp`. If Homebrew is
  missing, the installer stops rather than silently running a remote bootstrap. Opt in
  explicitly with `python3 scripts/install.py --install-homebrew --force`.
- **Debian/Ubuntu** — installs base tools with `apt`, then builds `whisper.cpp` under
  `~/.local/share/ai-agent-video-viewer/whisper.cpp` if `whisper-cli` is missing.
  Ensure `~/.local/bin` is on `PATH`.
- **Windows** — installs `ffmpeg`/`yt-dlp` via `winget`; install `whisper.cpp` manually
  and ensure `ffmpeg`, `ffprobe`, `yt-dlp`, and `whisper-cli` are on `PATH`.

Prefer to read before you run? Inspect `install.sh`, then:

```bash
curl -fsSL https://raw.githubusercontent.com/AnshRajput/ai-agent-video-viewer/main/install.sh | bash -s -- --force
```

Useful installer flags:

```bash
python3 scripts/install.py --dry-run          # show every action without doing it
python3 scripts/install.py --json             # machine-readable install plan
python3 scripts/install.py --skip-deps        # register the skill only
python3 scripts/install.py --target DIR        # install the portable skill into any harness dir (repeatable)
python3 scripts/install.py --remove-legacy    # remove the old ~/.claude/skills/ansh-media-watch
python3 scripts/install.py --no-check         # skip the final capability check
```

### Install into any agent harness

The core is a portable CLI (`scripts/media_watch.py`) plus a Markdown skill
(`SKILL.md`) and a dependency checker (`scripts/setup.py`). Two universal paths:

**1. File-based harnesses** with a skill/extensions directory (Claude Code, Hermes,
OpenCode, a generic skills folder). `--target` is repeatable, so several harnesses
can be registered at once:

```bash
python3 scripts/install.py \
  --skip-claude-skill --skip-claude-plugin \
  --target ~/.hermes/skills/media/ai-agent-video-viewer \
  --target ~/.config/opencode/skills/ai-agent-video-viewer
```

**2. Any shell-capable agent** (Codex, Cursor's agent, generic). No registration step:
install the toolchain, then point the agent at `SKILL.md` and let it run the CLI.

```bash
git clone https://github.com/AnshRajput/ai-agent-video-viewer.git ~/.local/share/ai-skills/ai-agent-video-viewer
cd ~/.local/share/ai-skills/ai-agent-video-viewer
python3 scripts/setup.py --json   # confirm capabilities
# then: "Read SKILL.md and use it to analyze <source>."
```

### MCP server

For MCP-capable harnesses, the bundled **zero-dependency** MCP server exposes the skill
as auto-discoverable tools — no per-harness skill file required. It is stdlib-only and
runs the same `media_watch.py` pipeline as a subprocess, inheriting every safety limit.

Generate ready-to-paste config with absolute paths filled in:

```bash
python3 scripts/mcp_server.py --print-config
```

Most clients (Cursor `~/.cursor/mcp.json`, Windsurf, Cline, Continue, Claude Code
`.mcp.json`) accept the standard shape:

```json
{
  "mcpServers": {
    "ai-agent-video-viewer": {
      "command": "python3",
      "args": ["/absolute/path/to/scripts/mcp_server.py"]
    }
  }
}
```

Claude Code one-liner:

```bash
claude mcp add ai-agent-video-viewer -- python3 /absolute/path/to/scripts/mcp_server.py
```

Codex (`~/.codex/config.toml`):

```toml
[mcp_servers.ai_agent_video_viewer]
command = "python3"
args = ["/absolute/path/to/scripts/mcp_server.py"]
```

The server exposes two tools:

| Tool | Purpose |
| --- | --- |
| `watch_media` | Run the full pipeline; returns the report, artifact paths, and the contact sheet **inline as an image** so even filesystem-less hosts get visual evidence. |
| `check_capabilities` | Report which local tools (ffmpeg / yt-dlp / whisper.cpp) are installed. |

## Usage

After installing, start a fresh session and ask naturally:

```text
Watch this video and summarize what happens: <url>
Transcribe this audio to English: /path/to/file.m4a
What is visible around 01:20 in this video? <url>
```

Direct CLI:

```bash
python3 scripts/media_watch.py "https://example.com/video.mp4" --translate
python3 scripts/media_watch.py "voice-note.m4a" --audio-only --translate
python3 scripts/media_watch.py "video.mp4" --start 00:30 --end 01:15 --translate
python3 scripts/media_watch.py "video.mp4" --resolution 1024 --max-frames 40 --translate  # sharper on-screen text
```

### Recommended defaults

- Use `--translate` unless the user explicitly wants original-language output.
- Keep `--language auto` and `--model small` for a good speed/accuracy balance.
- Use `--model medium` or `large-v3` for noisy or code-switched audio.
- Use a focused `--start/--end` range for long videos and specific questions.

## Output artifacts

Every run writes to a single output directory:

| File | Contents |
| --- | --- |
| `report.md` | Human-readable report: metadata, frames, transcript, cleanup hint |
| `result.json` | Machine-readable contract: paths, frame list, transcript segments, limits |
| `transcript.en.txt` / `transcript.txt` | Timestamped transcript (English when `--translate`) |
| `frames/frame_*.jpg` | Extracted frames |
| `frames/manifest.md` | Frame index with approximate timestamps |
| `frames/contact_sheet.jpg` | Tiled overview of all frames |

## Command-line reference

| Flag | Description |
| --- | --- |
| `--start T` / `--end T` | Focus on a range (`SS`, `MM:SS`, or `HH:MM:SS`) |
| `--max-frames N` | Frame budget, 1–120 (default 80) |
| `--resolution W` | Frame width in px, 64–4096 (default 512) |
| `--fps F` | Override frame rate, 0.01–2.0 |
| `--audio-only` | Skip frame extraction |
| `--language CODE` | Force spoken language (`hi`, `gu`, `en`, …) or `auto` |
| `--translate` | Translate transcript to English |
| `--model NAME` | whisper.cpp model (`base`, `small`, `medium`, `large-v3`); default `small` |
| `--out-dir DIR` | Output directory (must be empty unless `--force`) |
| `--force` | Allow fixed output names in a non-empty `--out-dir` |
| `--max-media-mb N` | Max input/download size in MB; `0` disables (default 2048) |
| `--max-duration-sec N` | Max media/range duration in seconds; `0` disables (default 21600) |
| `--allow-private-urls` | Permit localhost/private-network URLs (trusted media only) |
| `--keep` | Suppress the cleanup reminder |

## Multi-agent handoff

When a coordinator spawns a worker to process media, avoid temp-dir ambiguity by
choosing a shared output directory and passing it explicitly:

```bash
OUT_DIR="$PWD/.ai-agent-video-viewer-runs/$(date +%Y%m%d-%H%M%S)"
python3 scripts/media_watch.py "<source>" --out-dir "$OUT_DIR" --keep --translate
```

The worker returns absolute paths to `report.md`, `result.json`, the transcript, the
contact sheet, and the frame manifest. The coordinator must read `result.json` and
inspect the evidence directly before trusting a spawned-agent summary, and keep the
directory until all follow-ups are complete.

## Security and privacy

- **No cloud transcription.** Audio is transcribed locally; nothing is uploaded to a
  transcription API.
- **SSRF guard.** Localhost and private/reserved-network URLs are refused by default;
  override only with `--allow-private-urls` for trusted internal media.
- **Resource caps.** Media size (`--max-media-mb`, default 2048) and duration
  (`--max-duration-sec`, default 21600) are limited by default.
- **Output sandboxing.** All artifacts are written under one `0700` output directory,
  which is refused if it resolves to `/`, `$HOME`, or the current directory.
- **First-run model download.** The selected `whisper.cpp` model is fetched from
  Hugging Face on first use, then cached locally.

> These are safer defaults for user-owned agents, **not** a hosted-service sandbox.
> For untrusted, public-facing deployments, add OS/container disk quotas and network
> egress controls — redirects and unknown-size downloads can consume resources before
> post-download checks run. Delete the output directory when finished.

## Design principles

- **Harness-neutral core.** No assumptions about which agent runtime is calling it.
- **Stdlib-only Python.** Zero runtime pip dependencies keeps installs reproducible and offline-friendly.
- **Evidence over assertion.** Outputs are timestamped and separate verified facts from speculation.
- **Fail soft.** If frame extraction or transcription fails mid-run, the script logs the error and still reports whatever succeeded instead of aborting.
- **Single source of truth.** Root `SKILL.md` + `scripts/` are authoritative; the plugin mirror is verified byte-identical by a test.

## Development and testing

Common tasks are wrapped in a `Makefile`:

```bash
make test      # byte-compile + mirror check + unit tests
make sync      # copy root SKILL.md + scripts/ into the plugin mirror
make check     # fail if the plugin mirror has drifted from root
```

The root tree is the single source of truth; the plugin mirror is kept identical
automatically. Enable the bundled pre-commit hook once per clone so a commit can
never introduce drift:

```bash
git config core.hooksPath .githooks
```

Equivalent raw commands:

```bash
# Static + unit checks
python3 -m py_compile scripts/*.py
python3 -m unittest discover -s tests -v

# Installer plan and capability snapshot
python3 scripts/install.py --dry-run --skip-deps --force --no-check
python3 scripts/setup.py --json
python3 scripts/media_watch.py --help

# MCP server smoke checks
python3 scripts/mcp_server.py --print-config
```

Optional end-to-end smoke test with a generated clip:

```bash
tmp=$(mktemp -d)
ffmpeg -hide_banner -loglevel error -y -f lavfi -i testsrc=duration=2:size=320x180:rate=2 "$tmp/sample.mp4"
python3 scripts/media_watch.py "$tmp/sample.mp4" --max-frames 2 --out-dir "$tmp/out"
```

The test suite covers timestamp parsing, the centisecond-carry formatter, SSRF and
size/duration guards, output-directory safety, whisper JSON parsing, graceful
transcription degradation, the installer planner, `--target` installs, the MCP
JSON-RPC dispatch, and root↔mirror sync.

## Repository layout

```text
install.sh                        # one-command bootstrap wrapper
SKILL.md                          # standalone/generic skill entrypoint (source of truth)
scripts/
  media_watch.py                  # core media pipeline (CLI)
  setup.py                        # dependency/capability checker
  install.py                      # cross-platform installer + harness registration
  mcp_server.py                   # zero-dependency MCP server
.claude-plugin/plugin.json        # Claude Code plugin metadata
skills/ai-agent-video-viewer/     # plugin-compatible mirror (kept byte-identical to root)
tests/                            # unit + integration tests
```

The root `SKILL.md` + `scripts/` are the source of truth. The plugin-compatible
`skills/ai-agent-video-viewer/` directory is mirrored from the root for Claude
plugin-style installs and is enforced identical by `tests/test_mirror.py`.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Missing required binary: ffmpeg` | Install ffmpeg and ensure it is on `PATH` |
| URL download fails | Private/login-required or region-locked sources may need a local file |
| No transcript | Install `whisper.cpp`/`whisper-cli`, or use media with a clear audio track |
| Long video is slow | Use `--start`/`--end` to focus on a section |
| No vision tool in your agent | Use transcript/metadata only; do not claim visual details |
| Capabilities incomplete after install | Run `python3 scripts/setup.py --json` to see exactly what is missing |

## License

[MIT](LICENSE) © Ansh
