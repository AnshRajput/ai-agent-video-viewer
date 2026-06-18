# Ansh Media Watch Skill

A portable AI-agent skill for watching videos, listening to audio, extracting frames, and transcribing/translating speech to English.

Designed to work with:

- Claude Code standalone skills
- Claude Code plugin-style layout
- Hermes Agent skills
- Codex or any shell-capable agent/harness that can read Markdown and run scripts

Author: Ansh
License: MIT

## What it does

- Downloads video/audio URLs with `yt-dlp`
- Processes local video/audio files
- Extracts video frames with `ffmpeg`
- Creates a contact sheet and frame manifest for visual inspection
- Transcribes audio locally with whisper.cpp
- Translates speech to English with whisper.cpp when `--translate` is passed
- Writes agent-friendly outputs:
  - `report.md`
  - `result.json`
  - `transcript.en.txt` or `transcript.txt`
  - `frames/frame_*.jpg`
  - `frames/contact_sheet.jpg`
  - `frames/manifest.md`

## Requirements

| Tool | Needed for |
| --- | --- |
| Python 3.10+ | Running scripts |
| ffmpeg | Frame/audio extraction |
| ffprobe | Media metadata |
| yt-dlp | URL downloads |
| whisper.cpp / whisper-cli | Local transcription and English translation |

macOS:

```bash
brew install ffmpeg yt-dlp whisper-cpp
```

Ubuntu/Debian base tools:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg yt-dlp
# Then install whisper.cpp / whisper-cli from your package manager or source.
```

Windows:

- Install Python, ffmpeg, yt-dlp, and whisper.cpp.
- Ensure `ffmpeg`, `ffprobe`, `yt-dlp`, and `whisper-cli` are on PATH.
- Use `python` instead of `python3` if needed.

First transcription may download a whisper.cpp model from Hugging Face into `~/.cache/whisper/`. After the model is cached, transcription runs locally.

## Install from GitHub

Replace `<owner>` with your GitHub username/org after publishing.

### Claude Code: standalone skill

```bash
git clone https://github.com/<owner>/ansh-media-watch-skill.git ~/.claude/skills/ansh-media-watch
python3 ~/.claude/skills/ansh-media-watch/scripts/setup.py --json
```

Start a new Claude Code session after installing, then ask naturally:

```text
Watch this video and summarize what happens: <url>
Transcribe this audio to English: /path/to/file.m4a
What is visible around 01:20 in this video? <url>
```

If your Claude Code version supports user-invocable skills, you can also try:

```text
/ansh-media-watch <video-or-audio-url-or-path> [question]
```

### Claude Code: plugin-style layout

This repo also includes a Claude plugin-style layout:

```text
.claude-plugin/plugin.json
skills/ansh-media-watch/SKILL.md
skills/ansh-media-watch/scripts/
```

For local plugin development/testing, clone the repo and point Claude Code at the plugin directory if your Claude Code version supports `--plugin-dir`:

```bash
git clone https://github.com/<owner>/ansh-media-watch-skill.git ~/claude-plugins/ansh-media-watch
claude --plugin-dir ~/claude-plugins/ansh-media-watch
```

### Hermes Agent

```bash
git clone https://github.com/<owner>/ansh-media-watch-skill.git ~/.hermes/skills/media/ansh-media-watch
python3 ~/.hermes/skills/media/ansh-media-watch/scripts/setup.py --json
```

Then start a new Hermes session or run `/reload-skills` if available.

### Codex or other generic harnesses

Codex/generic agents do not need a special runtime if they can read files and run shell commands:

```bash
git clone https://github.com/<owner>/ansh-media-watch-skill.git ~/.local/share/ai-skills/ansh-media-watch
cd ~/.local/share/ai-skills/ansh-media-watch
python3 scripts/setup.py --json
```

Then tell the agent:

```text
Read SKILL.md in ~/.local/share/ai-skills/ansh-media-watch and use it to analyze <video-or-audio-source>.
```

### Install from GitHub archive

```bash
mkdir -p ~/.local/share/ai-skills/ansh-media-watch
curl -L https://github.com/<owner>/ansh-media-watch-skill/archive/refs/heads/main.tar.gz \
  | tar -xz --strip-components=1 -C ~/.local/share/ai-skills/ansh-media-watch
```

## Direct script usage

```bash
python3 scripts/setup.py --json
python3 scripts/media_watch.py "https://example.com/video.mp4" --translate
python3 scripts/media_watch.py "voice-note.m4a" --audio-only --translate
python3 scripts/media_watch.py "video.mp4" --start 00:30 --end 01:15 --translate
```

For better on-screen text visibility:

```bash
python3 scripts/media_watch.py "video.mp4" --resolution 1024 --max-frames 40 --translate
```

## Capability checks

```bash
python3 scripts/setup.py --json
python3 scripts/setup.py --check-local
python3 scripts/setup.py --check-transcription
python3 scripts/setup.py --check
```

`--check` requires full URL-download + local-transcription capability. `--check-local` only requires local media frame/metadata capability.

## Privacy and network behavior

- URL sources are fetched locally with `yt-dlp`.
- Local files are copied into the output directory.
- Frames/audio/transcripts are stored under the output directory.
- The script does not upload media or audio to cloud transcription APIs.
- First transcription may download a whisper.cpp model from Hugging Face.
- Outputs may contain sensitive frames/transcripts; delete the output directory after use.

## Validation before publishing

```bash
python3 -m py_compile scripts/setup.py scripts/media_watch.py
python3 scripts/setup.py --json
python3 scripts/media_watch.py --help
python3 -m unittest discover -s tests -v
```

Optional smoke test with generated video:

```bash
tmp=$(mktemp -d)
ffmpeg -hide_banner -loglevel error -y -f lavfi -i testsrc=duration=2:size=320x180:rate=2 "$tmp/sample.mp4"
python3 scripts/media_watch.py "$tmp/sample.mp4" --max-frames 2 --out-dir "$tmp/out"
```

## Troubleshooting

- Missing ffmpeg/ffprobe: install ffmpeg and ensure binaries are on PATH.
- URL download fails: private/login-required or region-locked URLs may not work without a local file.
- No transcript: install whisper.cpp / whisper-cli or use a media file with a clear audio track.
- Long video: use `--start` and `--end` for a focused section.
- No vision tool in your agent: use transcript/metadata only; do not claim visual details.

## Repository layout

```text
SKILL.md                         # standalone/generic skill entrypoint
scripts/                         # source scripts
.claude-plugin/plugin.json       # Claude Code plugin metadata
skills/ansh-media-watch/         # plugin-compatible mirrored skill directory
tests/                           # unit tests
```

The root `SKILL.md` + `scripts/` are the source of truth. The plugin-compatible `skills/ansh-media-watch/` directory is mirrored from the root for Claude plugin-style installs.
