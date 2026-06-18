#!/usr/bin/env python3
"""Portable media watcher for agents.

Downloads or copies a media source, extracts frames for visual inspection, and
transcribes/translates audio to English with local whisper.cpp when available.
The script is harness-neutral: it writes Markdown + JSON outputs that Claude
Code, Hermes, Codex, or any shell-capable agent can inspect.
"""
from __future__ import annotations

import argparse
import json
import ipaddress
import math
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

WHISPER_CANDIDATES = ["whisper-cli", "whisper-cpp"]
MODEL_DIR = Path.home() / ".cache" / "whisper"
MODEL_BASE_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"
VALID_MODELS = {"tiny", "base", "small", "medium", "large-v3", "large-v3-turbo", "tiny.en", "base.en", "small.en", "medium.en"}
MAX_FRAMES = 120
MAX_RESOLUTION = 4096
DEFAULT_MAX_MEDIA_MB = 2048
DEFAULT_MAX_DURATION_SEC = 6 * 60 * 60


def log(msg: str) -> None:
    print(f"[ai-agent-video-viewer] {msg}", file=sys.stderr)


def run(cmd: list[str], *, check: bool = True, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode != 0:
        raise SystemExit(f"Command failed ({result.returncode}): {shlex.join(cmd)}\n{result.stderr.strip()}")
    return result


def is_url(source: str) -> bool:
    return bool(re.match(r"https?://", source, re.IGNORECASE))


def validate_public_url(source: str, *, allow_private: bool = False) -> None:
    """Reject URL forms that are risky for unattended agent execution."""
    parsed = urllib.parse.urlparse(source)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise SystemExit("Only http(s) URLs are supported")
    if not parsed.hostname:
        raise SystemExit("URL must include a hostname")
    host = parsed.hostname.strip().lower().rstrip(".")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        if not allow_private:
            raise SystemExit("Refusing localhost URL. Pass --allow-private-urls only for trusted local media.")
        return
    if allow_private:
        return
    try:
        ip_obj = ipaddress.ip_address(host)
        addrs = [ip_obj]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise SystemExit(f"Could not resolve URL hostname {host!r}: {exc}") from exc
        addrs = []
        for info in infos:
            addr = info[4][0]
            try:
                addrs.append(ipaddress.ip_address(addr))
            except ValueError:
                continue
    unsafe = [str(ip) for ip in addrs if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified]
    if unsafe:
        raise SystemExit(
            "Refusing URL that resolves to private/local/reserved address(es): "
            + ", ".join(sorted(set(unsafe)))
            + ". Pass --allow-private-urls only for trusted local/internal media."
        )


def file_size_mb(path: Path) -> float:
    return path.stat().st_size / (1024 * 1024)


def enforce_file_size(path: Path, max_mb: float | None, label: str) -> None:
    if max_mb is None or max_mb <= 0:
        return
    size = file_size_mb(path)
    if size > max_mb:
        raise SystemExit(f"{label} is {size:.1f} MB, above limit {max_mb:.1f} MB. Use a focused smaller file or pass 0 to disable the limit.")


def ensure_inside(path: Path, parent: Path, label: str) -> Path:
    resolved = path.resolve()
    root = parent.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise SystemExit(f"{label} resolved outside output directory: {resolved}") from exc
    return resolved


def prepare_output_dir(out_dir: str | None, *, force: bool) -> Path:
    work = Path(out_dir).expanduser().resolve() if out_dir else Path(tempfile.mkdtemp(prefix="ai-agent-video-viewer-"))
    dangerous = {Path("/").resolve(), Path.home().resolve(), Path.cwd().resolve()}
    if work in dangerous:
        raise SystemExit(f"Refusing unsafe output directory: {work}. Choose a dedicated empty subdirectory.")
    if work.exists() and any(work.iterdir()) and not force:
        raise SystemExit(f"Output directory is not empty: {work}\nPass --force to write fixed output names there, or choose a new --out-dir.")
    work.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(work, 0o700)
    except OSError:
        pass
    return work


def parse_time(value: str | None) -> float | None:
    """Parse SS, MM:SS, or HH:MM:SS into non-negative seconds."""
    if value is None or value == "":
        return None
    raw = value.strip()
    if not raw:
        return None
    pieces = raw.split(":")
    if len(pieces) > 3:
        raise argparse.ArgumentTypeError(f"invalid timestamp '{value}'; expected SS, MM:SS, or HH:MM:SS")
    try:
        parts = [float(p) for p in pieces]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid timestamp '{value}'") from exc
    if any(not math.isfinite(p) or p < 0 for p in parts):
        raise argparse.ArgumentTypeError(f"invalid timestamp '{value}'; values must be finite and non-negative")
    if len(parts) >= 2 and parts[-1] >= 60:
        raise argparse.ArgumentTypeError(f"invalid timestamp '{value}'; seconds must be < 60")
    if len(parts) == 3 and parts[-2] >= 60:
        raise argparse.ArgumentTypeError(f"invalid timestamp '{value}'; minutes must be < 60")
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def fmt_time(seconds: float | None, *, precise: bool = False) -> str:
    if seconds is None or not math.isfinite(seconds):
        return "unknown"
    seconds = max(0.0, float(seconds))
    if precise:
        centis = int(round(seconds * 100))
        h, rem = divmod(centis, 360000)
        m, rem = divmod(rem, 6000)
        s, frac = divmod(rem, 100)
        suffix = f".{frac:02d}" if frac else ""
        return f"{h:02d}:{m:02d}:{s:02d}{suffix}" if h else f"{m:02d}:{s:02d}{suffix}"
    whole = int(round(seconds))
    h, rem = divmod(whole, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def positive_int_range(name: str, lo: int, hi: int):
    def parse(value: str) -> int:
        try:
            parsed = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"{name} must be an integer") from exc
        if parsed < lo or parsed > hi:
            raise argparse.ArgumentTypeError(f"{name} must be between {lo} and {hi}")
        return parsed
    return parse


def positive_float_range(name: str, lo: float, hi: float):
    def parse(value: str) -> float:
        try:
            parsed = float(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"{name} must be a number") from exc
        if not math.isfinite(parsed) or parsed < lo or parsed > hi:
            raise argparse.ArgumentTypeError(f"{name} must be finite and between {lo} and {hi}")
        return parsed
    return parse


def require_binary(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"Missing required binary: {name}")


def find_whisper() -> str | None:
    for name in WHISPER_CANDIDATES:
        path = shutil.which(name)
        if not path:
            continue
        result = subprocess.run([path, "--help"], capture_output=True, text=True, timeout=10)
        help_text = f"{result.stdout}\n{result.stderr}".lower()
        if result.returncode in (0, 1) and ("whisper" in help_text or "-oj" in help_text or "--output-json" in help_text):
            return path
    return None


def ensure_model(model: str) -> Path:
    if model not in VALID_MODELS:
        raise SystemExit(f"Unknown whisper model '{model}'. Choose: {', '.join(sorted(VALID_MODELS))}")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    path = MODEL_DIR / f"ggml-{model}.bin"
    # Tiny valid whisper.cpp models are several dozen MB. Anything below 1 MB is
    # almost certainly an interrupted/corrupt download.
    if path.exists() and path.stat().st_size > 1_000_000:
        return path
    if path.exists():
        log(f"cached model {path} looks too small; re-downloading")
        path.unlink()
    url = f"{MODEL_BASE_URL}/ggml-{model}.bin"
    tmp = path.with_suffix(path.suffix + ".part")
    log(f"downloading whisper.cpp model {model} to {path} (first transcription only)")
    try:
        with urllib.request.urlopen(url, timeout=900) as resp, tmp.open("wb") as fh:
            shutil.copyfileobj(resp, fh)
        if tmp.stat().st_size <= 1_000_000:
            raise RuntimeError("downloaded model is unexpectedly small")
        tmp.replace(path)
    except Exception as exc:
        if tmp.exists():
            tmp.unlink()
        raise SystemExit(f"Could not download whisper model {model}: {exc}")
    return path


def download_or_copy(source: str, work: Path, *, max_media_mb: float, allow_private_urls: bool) -> tuple[Path, dict[str, Any]]:
    if is_url(source):
        validate_public_url(source, allow_private=allow_private_urls)
        require_binary("yt-dlp")
        out_tpl = str(work / "source.%(ext)s")
        cmd = [
            "yt-dlp", "--no-playlist", "-f", "bv*+ba/best", "--merge-output-format", "mp4",
        ]
        if max_media_mb and max_media_mb > 0:
            cmd += ["--max-filesize", f"{max_media_mb:.0f}M"]
        cmd += ["-o", out_tpl, "--print", "after_move:filepath", source]
        log("downloading media with yt-dlp")
        result = run(cmd, timeout=3600)
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        media = Path(lines[-1]) if lines else next(work.glob("source.*"), None)
        if not media or not media.exists():
            raise SystemExit("yt-dlp completed but no media file was found")
        media = ensure_inside(media, work, "Downloaded media")
        enforce_file_size(media, max_media_mb, "Downloaded media")
        return media, {"source_kind": "url", "download_stdout": result.stdout.strip()}

    src = Path(source).expanduser().resolve()
    if not src.exists():
        raise SystemExit(f"Local media file not found: {src}")
    if not src.is_file():
        raise SystemExit(f"Local media path is not a file: {src}")
    safe_suffix = src.suffix.lower() or ".media"
    dest = work / f"source{safe_suffix}"
    enforce_file_size(src, max_media_mb, "Local media")
    if src != dest:
        shutil.copy2(src, dest)
    dest = ensure_inside(dest, work, "Copied media")
    enforce_file_size(dest, max_media_mb, "Copied media")
    return dest, {"source_kind": "local"}


def probe(media: Path) -> dict[str, Any]:
    require_binary("ffprobe")
    result = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(media)], timeout=120)
    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"ffprobe returned invalid JSON: {exc}") from exc
    streams = data.get("streams") or []
    duration = None
    if data.get("format", {}).get("duration"):
        duration = float(data["format"]["duration"])
    has_video = any(s.get("codec_type") == "video" for s in streams)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    return {"duration": duration, "has_video": has_video, "has_audio": has_audio, "streams": streams}


def enforce_duration(info: dict[str, Any], max_duration_sec: float | None, start: float | None, end: float | None) -> None:
    if max_duration_sec is None or max_duration_sec <= 0:
        return
    duration = info.get("duration")
    if duration is None:
        return
    if duration <= max_duration_sec:
        return
    if start is not None or end is not None:
        requested = compute_range_duration(duration, start, end)
        if requested <= max_duration_sec:
            return
    raise SystemExit(
        f"Media duration {fmt_time(duration)} exceeds limit {fmt_time(max_duration_sec)}. "
        "Use --start/--end for a focused range or pass --max-duration-sec 0 to disable the limit for trusted media."
    )


def compute_range_duration(duration: float | None, start: float | None, end: float | None) -> float:
    if start is not None or end is not None:
        hi = end if end is not None else duration
        if hi is None:
            hi = (start or 0) + 60
        return max(1.0, hi - (start or 0.0))
    return max(1.0, duration or 60.0)


def extract_frames(media: Path, frames_dir: Path, duration: float | None, start: float | None, end: float | None, max_frames: int, resolution: int, fps_override: float | None) -> list[dict[str, Any]]:
    require_binary("ffmpeg")
    frames_dir.mkdir(parents=True, exist_ok=True)
    range_duration = compute_range_duration(duration, start, end)
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
    run(cmd, timeout=1800)
    frames = sorted(frames_dir.glob("frame_*.jpg"))
    base = start or 0.0
    return [
        {"index": i + 1, "timestamp": round(base + i / fps, 3), "time": fmt_time(base + i / fps, precise=True), "path": str(path)}
        for i, path in enumerate(frames)
    ]


def write_frame_manifest(work: Path, frames: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    if not frames:
        return None, None
    manifest = work / "frames" / "manifest.md"
    lines = ["# Frame Manifest", "", "Timestamps are approximate source times.", "", "| # | Time | Seconds | Path |", "|---:|---|---:|---|"]
    for frame in frames:
        lines.append(f"| {frame['index']} | {frame['time']} | {frame['timestamp']:.3f} | `{frame['path']}` |")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    contact = work / "frames" / "contact_sheet.jpg"
    cols = min(5, max(1, math.ceil(math.sqrt(len(frames)))))
    rows = math.ceil(len(frames) / cols)
    try:
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", "1",
            "-i", str(work / "frames" / "frame_%05d.jpg"),
            "-vf", f"tile={cols}x{rows}:margin=4:padding=2", "-frames:v", "1", str(contact),
        ], check=True, timeout=120)
    except Exception as exc:  # contact sheet is convenience-only
        log(f"contact sheet generation skipped: {exc}")
        contact = None
    return str(manifest), str(contact) if contact and contact.exists() else None


def extract_audio(media: Path, out_wav: Path, start: float | None, end: float | None) -> Path:
    require_binary("ffmpeg")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    if start is not None:
        cmd += ["-ss", str(start)]
    if end is not None:
        cmd += ["-to", str(end)]
    cmd += ["-i", str(media), "-vn", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(out_wav)]
    run(cmd, timeout=1800)
    if not out_wav.exists() or out_wav.stat().st_size == 0:
        raise SystemExit("ffmpeg produced no audio file")
    return out_wav


def segments_from_whisper_json(path: Path, *, base_offset: float = 0.0) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    segments: list[dict[str, Any]] = []
    for item in data.get("transcription") or []:
        text = (item.get("text") or "").strip()
        if not text:
            continue
        offsets = item.get("offsets") or {}
        start = float(offsets.get("from") or 0) / 1000.0 + base_offset
        end = float(offsets.get("to") or 0) / 1000.0 + base_offset
        segments.append({"start": round(start, 3), "end": round(end, 3), "time": fmt_time(start, precise=True), "text": text})
    if not segments and (data.get("text") or "").strip():
        segments.append({"start": round(base_offset, 3), "end": round(base_offset, 3), "time": fmt_time(base_offset, precise=True), "text": data["text"].strip()})
    return segments


def transcribe(media: Path, work: Path, start: float | None, end: float | None, model: str, language: str, translate: bool) -> tuple[list[dict[str, Any]], str | None, str]:
    cli = find_whisper()
    if not cli:
        log("whisper.cpp not found; skipping transcript")
        return [], None, "unavailable"
    try:
        wav = extract_audio(media, work / "audio.wav", start, end)
        model_path = ensure_model(model)
    except (SystemExit, Exception) as exc:  # degrade to visual-only instead of aborting the whole run
        log(f"transcription setup failed; continuing without transcript: {exc}")
        return [], None, "failed"
    out_base = work / "transcript_whisper"
    cmd = [cli, "-m", str(model_path), "-f", str(wav), "-l", language or "auto", "-oj", "-of", str(out_base), "-np"]
    if translate:
        cmd.append("-tr")
    log(f"transcribing with whisper.cpp model={model}, language={language}, translate={translate}")
    result = run(cmd, check=False, timeout=7200)
    if result.returncode != 0:
        log(f"whisper.cpp failed: {result.stderr.strip()[:500]}")
        return [], None, "failed"
    json_path = Path(str(out_base) + ".json")
    if not json_path.exists():
        log("whisper.cpp produced no JSON transcript")
        return [], None, "failed"
    segments = segments_from_whisper_json(json_path, base_offset=start or 0.0)
    state = "ok" if segments else "no_speech_detected"
    return segments, f"whisper.cpp/{model}{'/translate-to-english' if translate else ''}", state


def md_inline(value: Any) -> str:
    return "`" + str(value).replace("`", "\\`").replace("\n", "\\n") + "`"


def write_outputs(work: Path, args: argparse.Namespace, media: Path, info: dict[str, Any], frames: list[dict[str, Any]], segments: list[dict[str, Any]], transcript_source: str | None, transcript_state: str, frame_manifest: str | None, contact_sheet: str | None, source_kind: str | None = None) -> None:
    transcript_path = work / ("transcript.en.txt" if args.translate else "transcript.txt")
    if segments:
        transcript_path.write_text("\n".join(f"[{seg['time']}] {seg['text']}" for seg in segments) + "\n", encoding="utf-8")

    report: list[str] = []
    report.append("# AI Agent Video Viewer Report")
    report.append("")
    report.append(f"- Source: {md_inline(args.source)}")
    report.append(f"- Local media: {md_inline(media)}")
    report.append(f"- Output directory: {md_inline(work)}")
    report.append(f"- Duration: {fmt_time(info.get('duration'))} ({info.get('duration') or 'unknown'} seconds)")
    report.append(f"- Has video: {info.get('has_video')}")
    report.append(f"- Has audio: {info.get('has_audio')}")
    if args.start is not None or args.end is not None:
        report.append(f"- Focus range: {fmt_time(args.start) if args.start is not None else 'start'} → {fmt_time(args.end) if args.end is not None else 'end'}")
    report.append(f"- Frames extracted: {len(frames)}")
    report.append(f"- Transcript segments: {len(segments)}" + (f" via {transcript_source}" if transcript_source else f" ({transcript_state})"))
    report.append("")

    if frames:
        report.append("## Visual Evidence")
        if contact_sheet:
            report.append(f"- Contact sheet: {md_inline(contact_sheet)}")
        if frame_manifest:
            report.append(f"- Frame manifest: {md_inline(frame_manifest)}")
        report.append("- Frame timestamps are approximate source times. If vision is available, inspect the contact sheet first, then individual frames as needed.")
        report.append("- If no vision tool is available, do not claim visual details; use only transcript and metadata.")
        report.append("")
        report.append("## Frames")
        for frame in frames:
            report.append(f"- [{frame['time']} / {frame['timestamp']:.3f}s] {md_inline(frame['path'])}")
        report.append("")

    report.append("## Transcript")
    if segments:
        label = "English transcript" if args.translate else "Transcript"
        report.append(f"{label} file: {md_inline(transcript_path)}")
        report.append("")
        report.append("```text")
        report.extend(f"[{seg['time']}] {seg['text']}" for seg in segments)
        report.append("```")
    elif transcript_state == "no_speech_detected":
        report.append("Transcription ran successfully, but no speech was detected.")
    else:
        report.append("No transcript available. Media may have no audio, whisper.cpp may be unavailable, or transcription may have failed.")
    report.append("")
    if not args.keep:
        report.append(f"Cleanup when done: `rm -rf -- {shlex.quote(str(work))}`")
    report_text = "\n".join(report) + "\n"
    (work / "report.md").write_text(report_text, encoding="utf-8")

    result = {
        "source": args.source,
        "source_kind": source_kind,
        "media_path": str(media),
        "output_dir": str(work),
        "report_path": str(work / "report.md"),
        "transcript_path": str(transcript_path) if segments else None,
        "duration": info.get("duration"),
        "has_video": info.get("has_video"),
        "has_audio": info.get("has_audio"),
        "frames": frames,
        "frame_manifest_path": frame_manifest,
        "contact_sheet_path": contact_sheet,
        "transcript_source": transcript_source,
        "transcript_state": transcript_state,
        "transcript_segments": segments,
        "timestamps": {"frames": "approximate source time", "transcript": "source time"},
        "limits": {"max_media_mb": args.max_media_mb, "max_duration_sec": args.max_duration_sec, "allow_private_urls": args.allow_private_urls},
    }
    (work / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(report_text)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Watch video, listen audio, and transcribe/translate to English for agents.")
    ap.add_argument("source", help="video/audio URL or local file path")
    ap.add_argument("--start", type=parse_time, help="range start: SS, MM:SS, or HH:MM:SS")
    ap.add_argument("--end", type=parse_time, help="range end: SS, MM:SS, or HH:MM:SS")
    ap.add_argument("--max-frames", type=positive_int_range("--max-frames", 1, MAX_FRAMES), default=80, help=f"frame cap (default 80, max {MAX_FRAMES})")
    ap.add_argument("--resolution", type=positive_int_range("--resolution", 64, MAX_RESOLUTION), default=512, help=f"frame width in px (default 512, max {MAX_RESOLUTION})")
    ap.add_argument("--fps", type=positive_float_range("--fps", 0.01, 2.0), default=None, help="override frame rate, 0.01..2.0")
    ap.add_argument("--audio-only", action="store_true", help="skip frame extraction")
    ap.add_argument("--language", "-l", default="auto", help="spoken language ISO code or auto")
    ap.add_argument("--translate", action="store_true", help="translate transcript to English")
    ap.add_argument("--model", default="small", help="whisper.cpp model name")
    ap.add_argument("--out-dir", help="output directory; must be empty unless --force is passed")
    ap.add_argument("--force", action="store_true", help="allow writing fixed output names into a non-empty --out-dir")
    ap.add_argument("--max-media-mb", type=positive_float_range("--max-media-mb", 0, 1_000_000), default=DEFAULT_MAX_MEDIA_MB, help=f"maximum input/download size in MB; 0 disables (default {DEFAULT_MAX_MEDIA_MB})")
    ap.add_argument("--max-duration-sec", type=positive_float_range("--max-duration-sec", 0, 30 * 24 * 60 * 60), default=DEFAULT_MAX_DURATION_SEC, help="maximum media or requested range duration in seconds; 0 disables (default 21600)")
    ap.add_argument("--allow-private-urls", action="store_true", help="allow localhost/private-network URLs for trusted local/internal media")
    ap.add_argument("--keep", action="store_true", help="suppress cleanup reminder")
    return ap


def main() -> int:
    args = build_parser().parse_args()
    for binary in ("ffmpeg", "ffprobe"):
        require_binary(binary)
    if args.end is not None and args.start is not None and args.end <= args.start:
        raise SystemExit("--end must be greater than --start")

    work = prepare_output_dir(args.out_dir, force=args.force)

    media, source_meta = download_or_copy(args.source, work, max_media_mb=args.max_media_mb, allow_private_urls=args.allow_private_urls)
    info = probe(media)
    enforce_duration(info, args.max_duration_sec, args.start, args.end)
    frames: list[dict[str, Any]] = []
    frame_manifest = None
    contact_sheet = None
    if info.get("has_video") and not args.audio_only:
        try:
            frames = extract_frames(media, work / "frames", info.get("duration"), args.start, args.end, args.max_frames, args.resolution, args.fps)
            frame_manifest, contact_sheet = write_frame_manifest(work, frames)
        except (SystemExit, Exception) as exc:  # degrade to transcript-only instead of aborting the whole run
            log(f"frame extraction failed; continuing without frames: {exc}")
            frames = []
            frame_manifest = contact_sheet = None

    segments: list[dict[str, Any]] = []
    transcript_source = None
    transcript_state = "not_attempted"
    if info.get("has_audio"):
        segments, transcript_source, transcript_state = transcribe(media, work, args.start, args.end, args.model, args.language, args.translate)

    write_outputs(work, args, media, info, frames, segments, transcript_source, transcript_state, frame_manifest, contact_sheet, source_kind=source_meta.get("source_kind"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
