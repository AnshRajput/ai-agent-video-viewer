---
name: ansh-media-watch
description: Use when asked to watch a video, listen to audio, describe what is visible, or transcribe/translate media into English. Works in both Hermes Agent and Claude Code by running a local script that downloads/copies media, extracts video frames, and produces an English transcript.
version: 1.0.0
author: Ansh
license: MIT
allowed-tools: Bash, Read
metadata:
  hermes:
    tags: [media, video, audio, transcription, whisper, ffmpeg, yt-dlp]
    related_skills: [youtube-content]
  claude:
    user-invocable: true
    argument-hint: "<video-or-audio-url-or-path> [question]"
---

# Ansh Media Watch

## Overview

This skill lets an agent watch video, listen to audio, transcribe speech into English, and answer questions grounded in the extracted evidence.

It is intentionally dual-compatible:

- Hermes Agent can load this `SKILL.md`, run `scripts/media_watch.py` with the `terminal` tool, read the generated Markdown/JSON outputs, and use `vision_analyze` on extracted frames.
- Claude Code can load the same `SKILL.md`, run the same script with Bash, and use `Read` on extracted frame images and transcript files.

The script uses local tools only by default:

- `yt-dlp` for URLs
- `ffmpeg` / `ffprobe` for media probing, frame extraction, and audio conversion
- `whisper.cpp` (`whisper-cli`) for offline transcription and English translation

No cloud API is required. The video itself is not uploaded anywhere. If the source speech is not English, pass `--translate` so whisper.cpp produces English text.

## When to Use

Use this skill when the user asks to:

- watch a video and explain what happens
- summarize what is in a video
- identify visual details, screens, actions, people, objects, or scene changes
- listen to an audio file or voice note
- transcribe audio/video speech in English
- translate non-English speech from media into English
- answer a specific question about a timestamp or section of media

Do not use this skill for:

- live video streams that cannot be downloaded by `yt-dlp`
- private media that requires browser login/cookies unless the user provides an accessible local file
- frame-perfect forensic work without asking for a focused timestamp range and higher resolution

## Quick Start

From the skill directory:

```bash
python3 scripts/setup.py --check
python3 scripts/media_watch.py "<video-or-audio-url-or-local-path>" --translate
```

For a specific section:

```bash
python3 scripts/media_watch.py "<source>" --start 01:20 --end 02:10 --translate
```

For better OCR / on-screen text visibility:

```bash
python3 scripts/media_watch.py "<source>" --resolution 1024 --max-frames 40 --translate
```

For audio-only transcription:

```bash
python3 scripts/media_watch.py "voice-note.m4a" --audio-only --translate
```

## Agent Workflow

### Step 0 — Preflight

Run this before first use, or when media processing fails:

```bash
python3 "${SKILL_DIR:-.}/scripts/setup.py" --check
```

If it reports missing tools:

- macOS: `brew install ffmpeg yt-dlp whisper-cpp`
- Ubuntu/Debian: `sudo apt-get update && sudo apt-get install -y ffmpeg yt-dlp` then install whisper.cpp from your package manager or source
- Windows: install ffmpeg, yt-dlp, and whisper.cpp, then ensure their binaries are on PATH

### Step 1 — Parse the request

Separate:

- source: URL or local path
- question: what the user wants to know
- optional range: timestamp section, if mentioned
- output need: full summary, transcript, visual description, or targeted answer

Prefer focused ranges for long media. For videos over 10 minutes, ask for or infer a section when the question is timestamp-specific.

### Step 2 — Run the script

Default, English transcript/translation:

```bash
python3 "${SKILL_DIR:-.}/scripts/media_watch.py" "<source>" --translate
```

Useful flags:

- `--start T` / `--end T`: focus on a range (`SS`, `MM:SS`, or `HH:MM:SS`)
- `--max-frames N`: frame budget; default 80, hard cap 120
- `--resolution W`: frame width; default 512
- `--fps F`: override frame rate, capped at 2 fps
- `--audio-only`: skip frames and only transcribe/listen
- `--language CODE`: force spoken language (`hi`, `gu`, `en`, etc.) or `auto`
- `--translate`: translate transcript to English using whisper.cpp
- `--model NAME`: whisper.cpp model (`base`, `small`, `medium`, `large-v3`); default `small`
- `--out-dir DIR`: choose output directory instead of a temporary one
- `--keep`: do not print cleanup reminder

### Step 3 — Inspect outputs

The script prints a Markdown report and writes these files in the output directory:

- `report.md`: human-readable report
- `result.json`: machine-readable metadata, frame list, transcript path
- `transcript.en.txt`: timestamped English transcript, if audio exists
- `frames/frame_*.jpg`: extracted video frames, if video exists

Hermes Agent:

1. Use `read_file` on `report.md` and `transcript.en.txt`.
2. Use `vision_analyze` on representative or all frame paths depending on the question.
3. Use timestamps from the frame manifest and transcript when answering.

Claude Code:

1. Use `Read` on `report.md` and `transcript.en.txt`.
2. Use `Read` on each relevant frame path listed in the report.
3. Answer using both visual frames and transcript.

### Step 4 — Answer grounded in evidence

For general “what’s in the video?” requests, include:

- concise overall summary
- visible scene/action progression with timestamps
- spoken content summary from transcript
- important on-screen text or UI, if visible
- uncertainty where frames are sparse or blurry

For transcription requests, return the English transcript or a cleaned version of it. Preserve timestamps unless the user asks for plain text only.

For targeted questions, answer directly first, then cite the relevant timestamp evidence.

### Step 5 — Cleanup

The output directory may contain downloaded media, extracted audio, and frames. Delete it after the user is done with follow-ups:

```bash
rm -rf "<out-dir>"
```

Keep the directory if the user may ask follow-up questions about the same media.

## Recommended Defaults

- Always use `--translate` unless the user explicitly wants the original language.
- Use `--language auto` by default.
- Use `--model small` for a good speed/accuracy balance.
- Use `--model medium` or `large-v3` for noisy audio or code-switched Hindi/Gujarati/English.
- Keep `--resolution 512` unless on-screen text matters.
- Keep frames under 80 for broad summaries; use focused ranges for detail.

## Failure Handling

- Download fails: report the yt-dlp error plainly. Do not keep retrying private/login-required URLs.
- No audio track: continue with visual-only analysis.
- No video stream: treat as audio-only and provide transcript.
- Whisper missing: install `whisper-cpp` or proceed visual-only for videos.
- Long video: run a sparse pass only for high-level summary; otherwise request or infer a timestamp range.
- Blurry/sparse frames: re-run with `--start/--end`, higher `--resolution`, or lower `--max-frames` over a narrower section.

## Privacy and Safety

This skill:

- downloads public URLs directly with `yt-dlp`
- copies local files into a temporary output directory
- extracts frames and audio locally
- transcribes locally with whisper.cpp by default
- does not upload media or audio to cloud APIs
- writes outputs only under the selected output directory

Warn the user before processing sensitive/private media and delete the output directory when finished.

## Verification Checklist

- [ ] Preflight passed or missing dependencies were clearly reported
- [ ] `result.json` exists
- [ ] For video: frame files exist and were visually inspected
- [ ] For audio/speech: `transcript.en.txt` exists or absence is explained
- [ ] Answer cites timestamps when making specific claims
- [ ] Output directory cleanup decision is explicit
