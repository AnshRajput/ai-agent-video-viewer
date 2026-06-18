#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".opus", ".flac", ".wma", ".aiff", ".aif"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".flv", ".wmv"}
WHISPER_CANDIDATES = ["whisper-cli", "whisper-cpp", "main"]
MODEL_DIR = Path.home() / ".cache" / "whisper"
MODEL_BASE_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"
VALID_MODELS = {"tiny", "base", "small", "medium", "large-v3", "large-v3-turbo", "tiny.en", "base.en", "small.en", "medium.en"}


def log(msg: str) -> None:
    print(f"[ansh-media-watch] {msg}", file=sys.stderr)


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise SystemExit(f"Command failed ({result.returncode}): {' '.join(cmd)}\n{result.stderr.strip()}")
    return result


def is_url(source: str) -> bool:
    return bool(re.match(r"https?://", source))


def parse_time(value: str | None) -> float | None:
    if not value:
        return None
    parts = [float(p) for p in value.split(":")]
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    raise SystemExit(f"Invalid timestamp: {value}")


def fmt_time(seconds: float | None) -> str:
    if seconds is None or math.isnan(seconds):
        return "unknown"
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def require_binary(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"Missing required binary: {name}")


def find_whisper() -> str | None:
    for name in WHISPER_CANDIDATES:
        path = shutil.which(name)
        if path:
            return path
    return None


def ensure_model(model: str) -> Path:
    if model not in VALID_MODELS:
        raise SystemExit(f"Unknown whisper model '{model}'. Choose: {', '.join(sorted(VALID_MODELS))}")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    path = MODEL_DIR / f"ggml-{model}.bin"
    if path.exists() and path.stat().st_size > 0:
        return path
    url = f"{MODEL_BASE_URL}/ggml-{model}.bin"
    tmp = path.with_suffix(path.suffix + ".part")
    log(f"downloading whisper.cpp model {model} to {path}")
    try:
        with urllib.request.urlopen(url, timeout=900) as resp, tmp.open("wb") as fh:
            shutil.copyfileobj(resp, fh)
        tmp.replace(path)
    except Exception as exc:
        if tmp.exists():
            tmp.unlink()
        raise SystemExit(f"Could not download whisper model {model}: {exc}")
    return path


def download_or_copy(source: str, work: Path) -> tuple[Path, dict]:
    require_binary("yt-dlp") if is_url(source) else None
    if is_url(source):
        out_tpl = str(work / "source.%(ext)s")
        cmd = ["yt-dlp", "--no-playlist", "-f", "bv*+ba/b", "--merge-output-format", "mp4", "-o", out_tpl, "--print", "after_move:filepath", source]
        log("downloading media with yt-dlp")
        result = run(cmd)
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        media = Path(lines[-1]) if lines else next(work.glob("source.*"), None)
        if not media or not media.exists():
            raise SystemExit("yt-dlp completed but no media file was found")
        return media.resolve(), {"source_kind": "url", "download_stdout": result.stdout.strip()}

    src = Path(source).expanduser().resolve()
    if not src.exists():
        raise SystemExit(f"Local media file not found: {src}")
    dest = work / f"source{src.suffix.lower() or '.media'}"
    if src != dest:
        shutil.copy2(src, dest)
    return dest.resolve(), {"source_kind": "local"}


def probe(media: Path) -> dict:
    require_binary("ffprobe")
    result = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(media)])
    data = json.loads(result.stdout or "{}")
    streams = data.get("streams") or []
    duration = None
    if data.get("format", {}).get("duration"):
        duration = float(data["format"]["duration"])
    has_video = any(s.get("codec_type") == "video" for s in streams)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    return {"duration": duration, "has_video": has_video, "has_audio": has_audio, "streams": streams}


def extract_frames(media: Path, frames_dir: Path, duration: float | None, start: float | None, end: float | None, max_frames: int, resolution: int, fps_override: float | None) -> list[dict]:
    require_binary("ffmpeg")
    frames_dir.mkdir(parents=True, exist_ok=True)
    if duration and start is not None or end is not None:
        range_duration = (end if end is not None else duration or 0) - (start or 0)
    else:
        range_duration = duration or 60
    range_duration = max(1.0, float(range_duration or 60))
    fps = fps_override if fps_override else min(2.0, max(0.05, max_frames / range_duration))
    fps = min(2.0, max(0.01, fps))
    vf = f"fps={fps},scale={resolution}:-1"
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    if start is not None:
        cmd += ["-ss", str(start)]
    if end is not None:
        cmd += ["-to", str(end)]
    cmd += ["-i", str(media), "-vf", vf, "-frames:v", str(max_frames), str(frames_dir / "frame_%05d.jpg")]
    log(f"extracting frames at {fps:.3f} fps, width {resolution}px")
    run(cmd)
    frames = sorted(frames_dir.glob("frame_*.jpg"))
    base = start or 0.0
    return [{"index": i + 1, "timestamp": round(base + i / fps, 2), "time": fmt_time(base + i / fps), "path": str(path)} for i, path in enumerate(frames)]


def extract_audio(media: Path, out_wav: Path, start: float | None, end: float | None) -> Path:
    require_binary("ffmpeg")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    if start is not None:
        cmd += ["-ss", str(start)]
    if end is not None:
        cmd += ["-to", str(end)]
    cmd += ["-i", str(media), "-vn", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(out_wav)]
    run(cmd)
    if not out_wav.exists() or out_wav.stat().st_size == 0:
        raise SystemExit("ffmpeg produced no audio file")
    return out_wav


def segments_from_whisper_json(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    segments = []
    for item in data.get("transcription") or []:
        text = (item.get("text") or "").strip()
        if not text:
            continue
        offsets = item.get("offsets") or {}
        start = float(offsets.get("from") or 0) / 1000.0
        end = float(offsets.get("to") or 0) / 1000.0
        segments.append({"start": round(start, 2), "end": round(end, 2), "time": fmt_time(start), "text": text})
    if not segments and (data.get("text") or "").strip():
        segments.append({"start": 0.0, "end": 0.0, "time": "00:00", "text": data["text"].strip()})
    return segments


def transcribe(media: Path, work: Path, start: float | None, end: float | None, model: str, language: str, translate: bool) -> tuple[list[dict], str | None]:
    cli = find_whisper()
    if not cli:
        log("whisper.cpp not found; skipping transcript")
        return [], None
    wav = extract_audio(media, work / "audio.wav", start, end)
    model_path = ensure_model(model)
    out_base = work / "transcript_whisper"
    cmd = [cli, "-m", str(model_path), "-f", str(wav), "-l", language or "auto", "-oj", "-of", str(out_base), "-np"]
    if translate:
        cmd.append("-tr")
    log(f"transcribing with whisper.cpp model={model}, language={language}, translate={translate}")
    result = run(cmd, check=False)
    if result.returncode != 0:
        log(f"whisper.cpp failed: {result.stderr.strip()[:500]}")
        return [], None
    json_path = Path(str(out_base) + ".json")
    if not json_path.exists():
        log("whisper.cpp produced no JSON transcript")
        return [], None
    segments = segments_from_whisper_json(json_path)
    return segments, f"whisper.cpp/{model}{'/translate-to-english' if translate else ''}"


def write_outputs(work: Path, args: argparse.Namespace, media: Path, info: dict, frames: list[dict], segments: list[dict], transcript_source: str | None) -> None:
    transcript_path = work / "transcript.en.txt"
    if segments:
        transcript_path.write_text("\n".join(f"[{seg['time']}] {seg['text']}" for seg in segments) + "\n", encoding="utf-8")
    report = []
    report.append("# Ansh Media Watch Report")
    report.append("")
    report.append(f"- Source: {args.source}")
    report.append(f"- Local media: {media}")
    report.append(f"- Output directory: {work}")
    report.append(f"- Duration: {fmt_time(info.get('duration'))} ({info.get('duration') or 'unknown'} seconds)")
    report.append(f"- Has video: {info.get('has_video')}")
    report.append(f"- Has audio: {info.get('has_audio')}")
    if args.start or args.end:
        report.append(f"- Focus range: {args.start or 'start'} → {args.end or 'end'}")
    report.append(f"- Frames extracted: {len(frames)}")
    report.append(f"- Transcript segments: {len(segments)}" + (f" via {transcript_source}" if transcript_source else ""))
    report.append("")
    if frames:
        report.append("## Frames")
        for frame in frames:
            report.append(f"- [{frame['time']}] {frame['path']}")
        report.append("")
    report.append("## English Transcript")
    if segments:
        report.append(f"Transcript file: {transcript_path}")
        report.append("")
        report.append("```text")
        report.extend(f"[{seg['time']}] {seg['text']}" for seg in segments)
        report.append("```")
    else:
        report.append("No transcript available. Media may have no audio or whisper.cpp may be unavailable.")
    report.append("")
    if not args.keep:
        report.append(f"Cleanup when done: rm -rf {work}")
    report_text = "\n".join(report) + "\n"
    (work / "report.md").write_text(report_text, encoding="utf-8")
    result = {
        "source": args.source,
        "media_path": str(media),
        "output_dir": str(work),
        "report_path": str(work / "report.md"),
        "transcript_path": str(transcript_path) if segments else None,
        "duration": info.get("duration"),
        "has_video": info.get("has_video"),
        "has_audio": info.get("has_audio"),
        "frames": frames,
        "transcript_source": transcript_source,
        "transcript_segments": segments,
    }
    (work / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(report_text)


def main() -> int:
    ap = argparse.ArgumentParser(description="Watch video, listen audio, and transcribe/translate to English for agents.")
    ap.add_argument("source", help="video/audio URL or local file path")
    ap.add_argument("--start", help="range start: SS, MM:SS, or HH:MM:SS")
    ap.add_argument("--end", help="range end: SS, MM:SS, or HH:MM:SS")
    ap.add_argument("--max-frames", type=int, default=80, help="frame cap (default 80, max 120)")
    ap.add_argument("--resolution", type=int, default=512, help="frame width in px (default 512)")
    ap.add_argument("--fps", type=float, default=None, help="override frame rate, capped at 2 fps")
    ap.add_argument("--audio-only", action="store_true", help="skip frame extraction")
    ap.add_argument("--language", "-l", default="auto", help="spoken language ISO code or auto")
    ap.add_argument("--translate", action="store_true", help="translate transcript to English")
    ap.add_argument("--model", default="small", help="whisper.cpp model name")
    ap.add_argument("--out-dir", help="output directory")
    ap.add_argument("--keep", action="store_true", help="suppress cleanup reminder")
    args = ap.parse_args()

    for binary in ("ffmpeg", "ffprobe"):
        require_binary(binary)
    work = Path(args.out_dir).expanduser().resolve() if args.out_dir else Path(tempfile.mkdtemp(prefix="ansh-media-watch-"))
    work.mkdir(parents=True, exist_ok=True)
    media, extra = download_or_copy(args.source, work)
    info = probe(media)
    start = parse_time(args.start)
    end = parse_time(args.end)
    if end is not None and start is not None and end <= start:
        raise SystemExit("--end must be greater than --start")

    frames = []
    if info.get("has_video") and not args.audio_only:
        frames = extract_frames(media, work / "frames", info.get("duration"), start, end, min(args.max_frames, 120), args.resolution, args.fps)
    segments, transcript_source = ([], None)
    if info.get("has_audio"):
        segments, transcript_source = transcribe(media, work, start, end, args.model, args.language, args.translate)
    write_outputs(work, args, media, info, frames, segments, transcript_source)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
