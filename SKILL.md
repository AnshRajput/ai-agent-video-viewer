---
name: ai-agent-video-viewer
description: This skill should be used when the user asks to watch a video, summarize what happens in a video, describe what is visible, listen to audio, transcribe audio/video, translate speech to English, or answer questions about a video/audio URL or local media path. It extracts frames, transcribes or translates speech to English, and grounds answers in timestamps.
version: 1.0.0
author: Ansh
license: MIT
homepage: https://github.com/ansh/ai-agent-video-viewer
repository: https://github.com/ansh/ai-agent-video-viewer
allowed-tools: Bash, Read
user-invocable: true
argument-hint: "<video-or-audio-url-or-path> [question]"
metadata:
  hermes:
    tags: [media, video, audio, transcription, translation, whisper, ffmpeg, yt-dlp]
    related_skills: [youtube-content]
  compatibility:
    harnesses: [Claude Code, Hermes Agent, Codex, generic shell-capable agents]
---

# AI Agent Video Viewer

## Overview

This skill lets an agent watch video, listen to audio, transcribe speech, translate speech into English, and answer questions grounded in extracted media evidence.

The core implementation is harness-neutral. It is a Markdown skill plus a Python script:

- `scripts/media_watch.py` downloads/copies media, extracts frames, produces a transcript, and writes `report.md` + `result.json`.
- Agents inspect the generated files with whatever file-reading and image/vision tools their harness provides.
- If the agent has no vision tool, it must not hallucinate visual details; it should use transcript and metadata only.

Default processing is local:

- `yt-dlp` downloads URL sources.
- `ffmpeg` / `ffprobe` probe media, extract frames, and convert audio.
- `whisper.cpp` (`whisper-cli`) transcribes locally and can translate speech to English.
- No cloud transcription API is used by this skill.

First transcription may download the selected whisper.cpp model from Hugging Face into `~/.cache/whisper/`. After that, transcription is local.

## When to Use

Use this skill when the user asks to:

- watch a video and explain what happens
- summarize what is in a video
- identify visual details, screens, actions, people, objects, or scene changes
- listen to an audio file or voice note
- transcribe audio/video speech
- translate non-English speech in media into English
- answer a question about a timestamp or section of media

Do not use this skill for:

- live streams that cannot be downloaded by `yt-dlp`
- private media requiring browser login/cookies unless the user provides an accessible local file
- frame-perfect forensic work without a focused timestamp range and higher resolution

## Important Path Rule

Let `SKILL_DIR` be the directory containing this `SKILL.md`.

Harnesses differ:

- Claude Code usually exposes `CLAUDE_SKILL_DIR`.
- Some harnesses may expose `SKILL_DIR`.
- Generic/Codex-style agents may expose neither; in that case, `cd` into the cloned skill directory or use an absolute path to `scripts/media_watch.py`.

Safe portable pattern when the harness provides a skill directory:

```bash
SKILL_DIR="${CLAUDE_SKILL_DIR:-${SKILL_DIR:-}}"
test -n "$SKILL_DIR" || { echo "Set SKILL_DIR to the directory containing SKILL.md" >&2; exit 2; }
python3 "$SKILL_DIR/scripts/setup.py" --check-local
python3 "$SKILL_DIR/scripts/media_watch.py" "<video-or-audio-url-or-local-path>" --translate
```

If your current working directory is the skill directory, this shorter form also works:

```bash
SKILL_DIR="$PWD"
python3 scripts/setup.py --check-local
python3 scripts/media_watch.py "<source>" --translate
```

When a coordinator spawns a subagent, pass the resolved `SKILL_DIR` and an explicit shared `--out-dir` in the subagent prompt. Do not make spawned agents guess or copy placeholder paths.

## Agent Workflow

### Step 0 — Capability Check

Run a capability check before first use or after media processing fails:

```bash
python3 "$SKILL_DIR/scripts/setup.py" --json
```

Use the mode-specific gate that matches the request:

```bash
# local visual/metadata work
python3 "$SKILL_DIR/scripts/setup.py" --check-local

# transcription or translation
python3 "$SKILL_DIR/scripts/setup.py" --check-transcription

# URL download plus transcription/translation
python3 "$SKILL_DIR/scripts/setup.py" --check
```

Capability meanings:

- `local_media_metadata`: can inspect local media with ffmpeg/ffprobe.
- `local_video_frames`: can extract frames from local videos.
- `url_download`: can download URLs via yt-dlp and process them.
- `local_transcription`: can transcribe/translate with local whisper.cpp.
- `full`: URL download + local transcription are both available.

Missing transcription does not prevent visual-only video analysis. Missing `yt-dlp` does not prevent local file analysis.

Install hints:

```bash
# macOS
brew install ffmpeg yt-dlp whisper-cpp

# Ubuntu/Debian base deps
sudo apt-get update && sudo apt-get install -y ffmpeg yt-dlp
# Then install whisper.cpp / whisper-cli from your package manager or source.
```

On Windows, install ffmpeg, yt-dlp, and whisper.cpp, ensure binaries are on PATH, and use `python` if `python3` is unavailable.

### Step 1 — Parse the Request

Separate:

- source: URL or local path
- question: what the user wants to know
- optional range: timestamp section, if mentioned
- requested output: full summary, transcript, visual description, or targeted answer

For long videos, prefer a focused `--start` / `--end` range when the question is specific.

### Step 2 — Run the Script

General video/audio analysis with English transcript/translation:

```bash
python3 "$SKILL_DIR/scripts/media_watch.py" "<source>" --translate
```

Focused section:

```bash
python3 "$SKILL_DIR/scripts/media_watch.py" "<source>" --start 01:20 --end 02:10 --translate
```

On-screen text / UI detail:

```bash
python3 "$SKILL_DIR/scripts/media_watch.py" "<source>" --resolution 1024 --max-frames 40 --translate
```

Audio-only transcription:

```bash
python3 "$SKILL_DIR/scripts/media_watch.py" "voice-note.m4a" --audio-only --translate
```

Useful flags:

- `--start T` / `--end T`: focus on a range (`SS`, `MM:SS`, or `HH:MM:SS`)
- `--max-frames N`: frame budget, 1..120, default 80
- `--resolution W`: frame width, 64..4096, default 512
- `--fps F`: override frame rate, 0.01..2.0
- `--audio-only`: skip frame extraction
- `--language CODE`: force spoken language (`hi`, `gu`, `en`, etc.) or `auto`
- `--translate`: translate transcript to English using whisper.cpp
- `--model NAME`: whisper.cpp model (`base`, `small`, `medium`, `large-v3`); default `small`
- `--out-dir DIR`: choose output directory; must be empty unless `--force` is passed
- `--force`: allow fixed output filenames in a non-empty output directory; only use with a dedicated ai-agent-video-viewer directory
- `--max-media-mb N`: maximum local/downloaded media size in MB; default 2048, 0 disables for trusted media
- `--max-duration-sec N`: maximum media or requested range duration in seconds; default 21600, 0 disables for trusted media
- `--allow-private-urls`: allow localhost/private-network URLs only for trusted local/internal media
- `--keep`: suppress cleanup reminder

### Step 3 — Inspect Outputs

The script prints a Markdown report and writes these files in the output directory:

- `report.md`: human-readable report
- `result.json`: machine-readable metadata, frame list, transcript path, transcript segments
- `transcript.en.txt`: timestamped English transcript when `--translate` is used
- `transcript.txt`: timestamped original-language transcript when `--translate` is not used
- `frames/frame_*.jpg`: extracted video frames
- `frames/manifest.md`: frame index with approximate timestamps and paths
- `frames/contact_sheet.jpg`: tiled overview of extracted frames when generation succeeds

Harness-neutral inspection steps:

1. Read `report.md` and `result.json`.
2. If transcript exists, read it and use timestamps as source-time evidence.
3. If vision/image tools are available, inspect `frames/contact_sheet.jpg` first, then relevant individual frames.
4. If vision/image tools are not available, explicitly say visual content was not inspected and avoid visual claims.

Harness notes:

- Claude Code: use `Read` on report/transcript/frame paths.
- Hermes Agent: use `read_file` on text outputs and `vision_analyze` on contact sheet or frame paths.
- Codex/generic CLI agents: use shell/file tools available in that harness; if no image capability exists, limit analysis to transcript/metadata.

### Step 3A — Spawner Team / Subagent Handoff

For multi-agent workflows, the coordinator should create a shared output directory and pass it to the media worker. The worker must keep artifacts until the coordinator says cleanup is complete.

```bash
OUT_DIR="<shared-workdir>/ai-agent-video-viewer/<slug-or-timestamp>"
python3 "$SKILL_DIR/scripts/media_watch.py" "<source>" --out-dir "$OUT_DIR" --keep --translate
```

The media worker's response must include absolute paths to `report.md`, `result.json`, the transcript file if present, `frames/contact_sheet.jpg` if present, and `frames/manifest.md` if present. The coordinator/reviewer must read `result.json` and inspect the evidence files directly before trusting a spawned agent summary.

### Step 4 — Answer Grounded in Evidence

For “what’s in the video?” include:

- concise overall summary
- visible scene/action progression with timestamps, only if frames were inspected
- spoken content summary from transcript
- important on-screen text or UI if visible
- uncertainty where frames are sparse, blurry, or not inspected

For transcription requests, return the English transcript or cleaned English transcript. Preserve timestamps unless the user asks for plain text only.

For targeted questions, answer directly first, then cite relevant timestamp evidence.

### Step 5 — Cleanup

The output directory can contain downloaded media, extracted audio, frames, and transcripts. Delete it after follow-ups are done:

```bash
rm -rf -- "<out-dir>"
```

Keep it if the user may ask more questions about the same media.

## Recommended Defaults

- Use `--translate` unless the user explicitly wants original-language transcription.
- Use `--language auto` by default.
- Use `--model small` for speed/accuracy balance.
- Use `--model medium` or `large-v3` for noisy or code-switched audio.
- Use `--resolution 512` unless on-screen text matters.
- Keep frames under 80 for broad summaries; use focused ranges for detail.

## Failure Handling

- Download fails: report the yt-dlp error plainly. Do not repeatedly retry private/login-required URLs.
- No audio track: continue with visual-only analysis.
- No video stream: treat as audio-only and provide transcript if possible.
- Whisper missing: proceed visual-only for video, or ask the user to install whisper.cpp for transcription.
- Long video: run a sparse pass only for high-level summary; otherwise request or infer a timestamp range.
- Blurry/sparse frames: re-run with `--start/--end`, higher `--resolution`, or fewer frames over a narrower section.

## Privacy and Safety

This skill:

- downloads URL sources directly with `yt-dlp`
- refuses localhost/private-network URLs by default to reduce accidental SSRF in unattended agent runs; use `--allow-private-urls` only for trusted local/internal media
- limits media size by default (`--max-media-mb 2048`) and allows trusted override with `--max-media-mb 0`
- limits media/requested-range duration by default (`--max-duration-sec 21600`) and allows trusted override with `--max-duration-sec 0`
- provides safer defaults for user-owned agents, but is not a complete hosted-service sandbox; public untrusted deployments still need OS/container disk quotas and network egress controls because redirects/extractors and unknown-size downloads can consume resources before post-download checks run
- copies local files into an output directory
- extracts frames and audio locally
- transcribes locally with whisper.cpp by default
- may download a whisper.cpp model from Hugging Face on first transcription
- does not upload media or audio to a cloud transcription API
- writes outputs only under the selected output directory

Warn before processing sensitive/private media and delete the output directory when finished.

## Verification Checklist

- [ ] Capability check passed for the requested mode
- [ ] `result.json` exists
- [ ] For video: contact sheet or frames were inspected before making visual claims
- [ ] For speech: transcript exists, or absence is explained
- [ ] Specific claims cite timestamps
- [ ] Visual uncertainty is stated when frames are sparse or no vision tool is available
- [ ] Cleanup decision is explicit
- [ ] For spawned-agent workflows, the worker returned artifact paths and the coordinator independently inspected `result.json`
