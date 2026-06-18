#!/usr/bin/env python3
"""Zero-dependency MCP server for AI Agent Video Viewer.

Wraps ``media_watch.py`` as a Model Context Protocol (MCP) server so the skill
can be auto-discovered as a tool by *any* MCP-capable harness — Claude Code,
Cursor, Windsurf, Cline, Continue, OpenCode, Codex, and others — without copying
a harness-specific skill file into each one.

Design goals:
- Standard library only. No pip install, no virtualenv, fully offline-capable.
- stdio transport: newline-delimited JSON-RPC 2.0 on stdin/stdout. stdout carries
  ONLY protocol messages; all logging goes to stderr.
- Vision for everyone: ``watch_media`` returns the contact sheet inline as an MCP
  image content block, so hosts without filesystem access can still "see" frames.

Tools:
- ``watch_media``        watch a video / listen to audio, transcribe/translate,
                         and return a timestamped report (+ contact sheet image).
- ``check_capabilities`` report which local tools (ffmpeg/yt-dlp/whisper) exist.

Run as a server:        python3 scripts/mcp_server.py
Print client config:    python3 scripts/mcp_server.py --print-config
"""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SERVER_NAME = "ai-agent-video-viewer"
SERVER_VERSION = "1.0.0"
DEFAULT_PROTOCOL = "2024-11-05"

HERE = Path(__file__).resolve().parent
MEDIA_WATCH = HERE / "media_watch.py"
SETUP = HERE / "setup.py"

# Contact sheets above this size are referenced by path instead of inlined, to
# avoid flooding a host's context with a huge base64 blob.
MAX_INLINE_IMAGE_BYTES = 5 * 1024 * 1024


def log(msg: str) -> None:
    print(f"[ai-agent-video-viewer mcp] {msg}", file=sys.stderr, flush=True)


def text(value: str) -> dict[str, Any]:
    return {"type": "text", "text": value}


# --------------------------------------------------------------------------- #
# Tool definitions
# --------------------------------------------------------------------------- #
def make_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "watch_media",
            "description": (
                "Watch a video or listen to an audio file (URL or local path), extract "
                "frames, transcribe speech, and (by default) translate it to English. "
                "Returns a timestamped Markdown report, artifact paths, and the contact "
                "sheet inline as an image. Use this to summarize a video, describe what "
                "is visible, transcribe/translate audio, or answer questions about media."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Video/audio URL or local file path."},
                    "question": {"type": "string", "description": "Optional question to focus the analysis (recorded in the response for the calling agent)."},
                    "start": {"type": "string", "description": "Range start as SS, MM:SS, or HH:MM:SS."},
                    "end": {"type": "string", "description": "Range end as SS, MM:SS, or HH:MM:SS."},
                    "translate": {"type": "boolean", "description": "Translate transcript to English (default true)."},
                    "audio_only": {"type": "boolean", "description": "Skip frame extraction; transcript only."},
                    "language": {"type": "string", "description": "Spoken-language ISO code (hi, gu, en, ...) or 'auto'."},
                    "model": {"type": "string", "description": "whisper.cpp model: tiny, base, small, medium, large-v3. Default small."},
                    "max_frames": {"type": "integer", "description": "Frame budget 1..120 (default 80)."},
                    "resolution": {"type": "integer", "description": "Frame width in px 64..4096 (default 512). Raise for on-screen text."},
                    "fps": {"type": "number", "description": "Override frame rate 0.01..2.0."},
                    "include_contact_sheet": {"type": "boolean", "description": "Inline the contact sheet image in the result (default true)."},
                    "keep_output": {"type": "boolean", "description": "Persist the output directory (frames, transcript, result.json) on disk and return their paths. Default false: the report and contact sheet are returned inline and the temporary directory is removed."},
                    "allow_private_urls": {"type": "boolean", "description": "Allow localhost/private-network URLs (trusted local media only)."},
                    "max_media_mb": {"type": "number", "description": "Max input/download size in MB; 0 disables (default 2048)."},
                    "max_duration_sec": {"type": "number", "description": "Max media/range duration in seconds; 0 disables (default 21600)."},
                },
                "required": ["source"],
                "additionalProperties": False,
            },
        },
        {
            "name": "check_capabilities",
            "description": (
                "Report which local media tools are available (ffmpeg, ffprobe, yt-dlp, "
                "whisper.cpp) and which capabilities are usable. Call this first if a "
                "watch_media call fails, to see what needs installing."
            ),
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    ]


# --------------------------------------------------------------------------- #
# Tool implementations
# --------------------------------------------------------------------------- #
def _flag_args(arguments: dict[str, Any]) -> list[str]:
    cmd: list[str] = []
    if arguments.get("translate", True):
        cmd.append("--translate")
    if arguments.get("audio_only"):
        cmd.append("--audio-only")
    if arguments.get("allow_private_urls"):
        cmd.append("--allow-private-urls")
    for flag, key in (
        ("--start", "start"), ("--end", "end"), ("--language", "language"),
        ("--model", "model"), ("--max-frames", "max_frames"), ("--resolution", "resolution"),
        ("--fps", "fps"), ("--max-media-mb", "max_media_mb"), ("--max-duration-sec", "max_duration_sec"),
    ):
        value = arguments.get(key)
        if value not in (None, ""):
            cmd += [flag, str(value)]
    return cmd


def _artifact_summary(out_dir: Path) -> str:
    result_path = out_dir / "result.json"
    if not result_path.exists():
        return f"Artifacts: output dir {out_dir} (result.json not written)"
    try:
        data = json.loads(result_path.read_text(encoding="utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return f"Artifacts: output dir {out_dir}"
    keys = ["output_dir", "report_path", "transcript_path", "contact_sheet_path", "frame_manifest_path"]
    summary = {k: data.get(k) for k in keys}
    summary["result_json"] = str(result_path)
    summary["frames"] = len(data.get("frames") or [])
    return "Artifacts (paths for filesystem-capable hosts):\n" + json.dumps(summary, indent=2)


def run_watch(arguments: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    source = arguments.get("source")
    if not source or not isinstance(source, str):
        return [text("Error: 'source' (a video/audio URL or local path) is required.")], True
    if not MEDIA_WATCH.exists():
        return [text(f"Error: media_watch.py not found next to the MCP server at {MEDIA_WATCH}.")], True

    keep = bool(arguments.get("keep_output", False))
    out_dir = Path(tempfile.mkdtemp(prefix="ai-agent-video-viewer-mcp-"))
    cmd = [sys.executable, str(MEDIA_WATCH), source, "--out-dir", str(out_dir), "--keep"] + _flag_args(arguments)
    log(f"watch_media: {source}")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
    except subprocess.TimeoutExpired:
        shutil.rmtree(out_dir, ignore_errors=True)
        return [text("media_watch timed out after 2h.")], True
    except Exception as exc:  # pragma: no cover - defensive
        shutil.rmtree(out_dir, ignore_errors=True)
        return [text(f"Failed to launch media_watch: {exc}")], True

    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or "unknown error"
        shutil.rmtree(out_dir, ignore_errors=True)
        return [text(f"media_watch failed (exit {proc.returncode}):\n{detail}")], True

    # Read everything we need into the response BEFORE any cleanup.
    content: list[dict[str, Any]] = []
    question = arguments.get("question")
    if question:
        content.append(text(f"Question to answer from this media: {question}"))

    report_path = out_dir / "report.md"
    report = report_path.read_text(encoding="utf-8", errors="ignore") if report_path.exists() else (proc.stdout or "(no report produced)")
    content.append(text(report))
    if keep:
        content.append(text(_artifact_summary(out_dir)))

    if arguments.get("include_contact_sheet", True):
        contact = out_dir / "frames" / "contact_sheet.jpg"
        if contact.exists():
            size = contact.stat().st_size
            if size <= MAX_INLINE_IMAGE_BYTES:
                encoded = base64.b64encode(contact.read_bytes()).decode("ascii")
                content.append({"type": "image", "data": encoded, "mimeType": "image/jpeg"})
            elif keep:
                content.append(text(f"Contact sheet is {size / 1e6:.1f} MB; not inlined. Read it from {contact}."))

    if not keep:
        # Stateless by default: the report + inline contact sheet already carry the
        # evidence, so the working directory is removed to avoid unbounded temp growth.
        shutil.rmtree(out_dir, ignore_errors=True)
        content.append(text("Temporary outputs were cleaned up. Re-run with keep_output=true to retain frames, transcript, and result.json on disk."))
    return content, False


def check_capabilities(_arguments: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    if not SETUP.exists():
        return [text(f"Error: setup.py not found at {SETUP}.")], True
    try:
        proc = subprocess.run([sys.executable, str(SETUP), "--json"], capture_output=True, text=True, timeout=60)
    except Exception as exc:  # pragma: no cover - defensive
        return [text(f"Failed to run capability check: {exc}")], True
    out = proc.stdout.strip() or proc.stderr.strip() or "(no output)"
    return [text(out)], proc.returncode != 0


TOOL_IMPLS = {"watch_media": run_watch, "check_capabilities": check_capabilities}


def call_tool(name: str, arguments: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    impl = TOOL_IMPLS.get(name)
    if impl is None:
        return [text(f"Unknown tool: {name!r}. Available: {', '.join(TOOL_IMPLS)}.")], True
    return impl(arguments)


# --------------------------------------------------------------------------- #
# JSON-RPC plumbing
# --------------------------------------------------------------------------- #
def _ok(msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def dispatch(message: Any) -> dict[str, Any] | None:
    """Handle one JSON-RPC message. Returns a response dict, or None for notifications."""
    if not isinstance(message, dict):
        return _error(None, -32600, "Invalid Request")
    method = message.get("method")
    msg_id = message.get("id")
    is_notification = "id" not in message

    if method == "initialize":
        params = message.get("params") or {}
        return _ok(msg_id, {
            "protocolVersion": params.get("protocolVersion") or DEFAULT_PROTOCOL,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "ping":
        return _ok(msg_id, {})
    if method == "tools/list":
        return _ok(msg_id, {"tools": make_tools()})
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name") or ""
        arguments = params.get("arguments") or {}
        try:
            content, is_error = call_tool(name, arguments)
        except Exception as exc:  # never let one bad call kill the server
            content, is_error = [text(f"Tool '{name}' raised: {exc}")], True
        return _ok(msg_id, {"content": content, "isError": is_error})
    if method == "resources/list":
        return _ok(msg_id, {"resources": []})
    if method == "prompts/list":
        return _ok(msg_id, {"prompts": []})

    if is_notification:
        return None
    return _error(msg_id, -32601, f"Method not found: {method}")


def serve(stdin: Any = None, stdout: Any = None) -> int:
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    log(f"serving on stdio (server={SERVER_NAME} v{SERVER_VERSION})")
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            _write(stdout, _error(None, -32700, "Parse error"))
            continue
        response = dispatch(message)
        if response is not None:
            _write(stdout, response)
    return 0


def _write(stdout: Any, payload: dict[str, Any]) -> None:
    stdout.write(json.dumps(payload) + "\n")
    stdout.flush()


def print_config() -> None:
    server = str(Path(__file__).resolve())
    py = sys.executable
    block = {"mcpServers": {SERVER_NAME: {"command": py, "args": [server]}}}
    print("# JSON config — Cursor (~/.cursor/mcp.json), Windsurf, Cline, Continue,")
    print("# Claude Code (.mcp.json), and most MCP clients:")
    print(json.dumps(block, indent=2))
    print()
    print("# Claude Code CLI one-liner:")
    print(f"claude mcp add {SERVER_NAME} -- {py} {server}")
    print()
    print("# Codex (~/.codex/config.toml):")
    print(f"[mcp_servers.{SERVER_NAME.replace('-', '_')}]")
    print(f'command = "{py}"')
    print(f'args = ["{server}"]')


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if "--print-config" in argv:
        print_config()
        return 0
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
