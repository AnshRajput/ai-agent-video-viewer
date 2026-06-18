# AI Agent Video Viewer

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
| Python 3.9+ | Running scripts and installer |
| ffmpeg | Frame/audio extraction |
| ffprobe | Media metadata |
| yt-dlp | URL downloads |
| whisper.cpp / whisper-cli | Local transcription and English translation |
| Claude Code CLI | Terminal/app skill usage |

First transcription may download a whisper.cpp model from Hugging Face into `~/.cache/whisper/`. After the model is cached, transcription runs locally.

## One-command install

Canonical repository URL: `https://github.com/AnshRajput/ai-agent-video-viewer`.

The full installer installs the local media toolchain and makes the skill available to Claude Code both as a user skill and as a plugin-style directory:

- `~/.claude/skills/ai-agent-video-viewer` for normal Claude Code terminal/app sessions after restart
- `~/claude-plugins/ai-agent-video-viewer` for plugin-dir testing with `claude --plugin-dir ...`

Recommended install after cloning:

```bash
git clone https://github.com/AnshRajput/ai-agent-video-viewer.git ~/.local/share/ai-agent-video-viewer/source
cd ~/.local/share/ai-agent-video-viewer/source
python3 scripts/install.py --force
```

macOS with Homebrew already installed uses:

```bash
brew install ffmpeg yt-dlp whisper-cpp
```

If Homebrew is not installed, the installer stops instead of silently running a remote bootstrap script. To explicitly allow Homebrew bootstrap, run:

```bash
python3 scripts/install.py --install-homebrew --force
```

Remote bootstrap is also supported for users who prefer a single copy/paste command. For supply-chain safety, inspect `install.sh` first if possible.

```bash
curl -fsSL https://raw.githubusercontent.com/AnshRajput/ai-agent-video-viewer/main/install.sh | bash -s -- --force
```

Useful installer options:

```bash
python3 scripts/install.py --dry-run          # show package/file actions only
python3 scripts/install.py --json             # machine-readable install plan
python3 scripts/install.py --skip-deps        # install Claude skill/plugin only
python3 scripts/install.py --remove-legacy    # remove old ~/.claude/skills/ansh-media-watch
python3 scripts/install.py --no-check         # skip final setup.py --check
```

Ubuntu/Debian: `scripts/install.py` installs apt base tools and builds `whisper.cpp` locally under `~/.local/share/ai-agent-video-viewer/whisper.cpp` when `whisper-cli` is missing. Ensure `~/.local/bin` is on PATH.

Windows: automatic setup is still limited. Install Python, ffmpeg, yt-dlp, and whisper.cpp, ensure `ffmpeg`, `ffprobe`, `yt-dlp`, and `whisper-cli` are on PATH, then run `python scripts/setup.py --check`.

Start a new Claude Code terminal session and restart the Claude Code app/IDE integration after installing, then ask naturally:

```text
Watch this video and summarize what happens: <url>
Transcribe this audio to English: /path/to/file.m4a
What is visible around 01:20 in this video? <url>
```

If your Claude Code version supports user-invocable skills, you can also try:

```text
/ai-agent-video-viewer <video-or-audio-url-or-path> [question]
```

### Claude Code: plugin-style layout

This repo also includes a Claude plugin-style layout:

```text
.claude-plugin/plugin.json
skills/ai-agent-video-viewer/SKILL.md
skills/ai-agent-video-viewer/scripts/
```

For local plugin development/testing, clone the repo and point Claude Code at the plugin directory if your Claude Code version supports `--plugin-dir`:

```bash
git clone https://github.com/AnshRajput/ai-agent-video-viewer.git ~/claude-plugins/ai-agent-video-viewer
claude --plugin-dir ~/claude-plugins/ai-agent-video-viewer
```

### Hermes Agent

```bash
git clone https://github.com/AnshRajput/ai-agent-video-viewer.git ~/.hermes/skills/media/ai-agent-video-viewer
python3 ~/.hermes/skills/media/ai-agent-video-viewer/scripts/setup.py --json
```

Then start a new Hermes session or run `/reload-skills` if available.

### Codex or other generic harnesses

Codex/generic agents do not need a special runtime if they can read files and run shell commands:

```bash
git clone https://github.com/AnshRajput/ai-agent-video-viewer.git ~/.local/share/ai-skills/ai-agent-video-viewer
cd ~/.local/share/ai-skills/ai-agent-video-viewer
python3 scripts/setup.py --json
```

Then tell the agent:

```text
Read SKILL.md in ~/.local/share/ai-skills/ai-agent-video-viewer and use it to analyze <video-or-audio-source>.
```

### Install from GitHub archive

```bash
mkdir -p ~/.local/share/ai-skills/ai-agent-video-viewer
curl -L https://github.com/AnshRajput/ai-agent-video-viewer/archive/refs/heads/main.tar.gz \
  | tar -xz --strip-components=1 -C ~/.local/share/ai-skills/ai-agent-video-viewer
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

Use mode-specific checks before agent work:

- Visual/local file analysis: `python3 scripts/setup.py --check-local`
- Transcription or translation: `python3 scripts/setup.py --check-transcription`
- URL download plus transcription: `python3 scripts/setup.py --check`

## Spawner Team / multi-agent handoff

When a coordinator spawns a worker agent to process media, avoid temp-dir ambiguity. The coordinator should create or choose a shared output directory and pass it to the worker:

```bash
OUT_DIR="$PWD/.ai-agent-video-viewer-runs/$(date +%Y%m%d-%H%M%S)"
python3 scripts/media_watch.py "<source>" --out-dir "$OUT_DIR" --keep --translate
```

The media worker should return absolute paths to:

- `report.md`
- `result.json`
- `transcript.en.txt` or `transcript.txt`, if present
- `frames/contact_sheet.jpg`, if present
- `frames/manifest.md`, if present

The coordinator or reviewer must read `result.json` and inspect the evidence files directly before trusting a spawned agent's summary. Do not delete the output directory until all follow-up questions and reviews are complete.

## Privacy and network behavior

- URL sources are fetched locally with `yt-dlp`.
- Private-network/localhost URLs are refused by default to reduce accidental SSRF in unattended agent runs. Use `--allow-private-urls` only for trusted local/internal media.
- Input/download size is limited by default with `--max-media-mb 2048`; pass `--max-media-mb 0` only for trusted large media.
- Media or requested range duration is limited by default with `--max-duration-sec 21600`; pass `--max-duration-sec 0` only for trusted long media.
- These guards are safer defaults for user-owned agents, not a complete hosted-service sandbox. If you expose this to untrusted users, also use OS/container disk quotas and network egress controls because redirects/extractors and unknown-size downloads can still consume resources before post-download checks run.
- Local files are copied into the output directory.
- Frames/audio/transcripts are stored under the output directory.
- The script does not upload media or audio to cloud transcription APIs.
- First transcription may download a whisper.cpp model from Hugging Face.
- Outputs may contain sensitive frames/transcripts; delete the output directory after use.

## Validation before publishing

```bash
python3 -m py_compile scripts/setup.py scripts/install.py scripts/media_watch.py
python3 scripts/install.py --dry-run --skip-deps --force --no-check
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
install.sh                        # one-command bootstrap wrapper
SKILL.md                          # standalone/generic skill entrypoint
scripts/                          # source scripts: installer, setup checker, media processor
.claude-plugin/plugin.json        # Claude Code plugin metadata
skills/ai-agent-video-viewer/     # plugin-compatible mirrored skill directory
tests/                            # unit tests
```

The root `SKILL.md` + `scripts/` are the source of truth. The plugin-compatible `skills/ai-agent-video-viewer/` directory is mirrored from the root for Claude plugin-style installs.
