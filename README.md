# Ansh Media Watch Skill

Dual-compatible skill for Hermes Agent and Claude Code.

It watches videos, listens to audio, extracts frames, and transcribes/translates speech into English using local tools.

## Install locally

Hermes:

```bash
mkdir -p ~/.hermes/skills/media/ansh-media-watch
cp -R SKILL.md scripts ~/.hermes/skills/media/ansh-media-watch/
```

Claude Code:

```bash
mkdir -p ~/.claude/skills/ansh-media-watch
cp -R SKILL.md scripts ~/.claude/skills/ansh-media-watch/
```

## Dependencies

macOS:

```bash
brew install ffmpeg yt-dlp whisper-cpp
```

Check:

```bash
python3 scripts/setup.py --check
```

## Usage

```bash
python3 scripts/media_watch.py "https://example.com/video.mp4" --translate
python3 scripts/media_watch.py "voice-note.m4a" --audio-only --translate
python3 scripts/media_watch.py "video.mp4" --start 00:30 --end 01:15 --translate
```

Outputs are written to a temporary directory unless `--out-dir` is passed:

- `report.md`
- `result.json`
- `transcript.en.txt`
- `frames/*.jpg`

## Author

Ansh
