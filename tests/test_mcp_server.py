import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mcp_server", ROOT / "scripts" / "mcp_server.py")
mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp)

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _make_silent_clip(path: Path) -> None:
    # Video-only clip (no audio) keeps the test offline: no whisper, no model download.
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", "testsrc=duration=1:size=120x90:rate=3", str(path)],
        check=True,
    )


class HandshakeTests(unittest.TestCase):
    def test_initialize_echoes_protocol_and_reports_server(self):
        resp = mcp.dispatch({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                             "params": {"protocolVersion": "2025-06-18"}})
        self.assertEqual(resp["id"], 1)
        self.assertEqual(resp["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(resp["result"]["serverInfo"]["name"], "ai-agent-video-viewer")
        self.assertIn("tools", resp["result"]["capabilities"])

    def test_initialize_falls_back_to_default_protocol(self):
        resp = mcp.dispatch({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(resp["result"]["protocolVersion"], mcp.DEFAULT_PROTOCOL)

    def test_initialized_notification_has_no_response(self):
        self.assertIsNone(mcp.dispatch({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_unknown_method_is_method_not_found(self):
        resp = mcp.dispatch({"jsonrpc": "2.0", "id": 9, "method": "does/not/exist"})
        self.assertEqual(resp["error"]["code"], -32601)

    def test_unknown_notification_is_silently_ignored(self):
        self.assertIsNone(mcp.dispatch({"jsonrpc": "2.0", "method": "notifications/whatever"}))


class ToolListTests(unittest.TestCase):
    def test_tools_list_exposes_both_tools_with_schemas(self):
        resp = mcp.dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {t["name"] for t in resp["result"]["tools"]}
        self.assertEqual(names, {"watch_media", "check_capabilities"})
        watch = next(t for t in resp["result"]["tools"] if t["name"] == "watch_media")
        self.assertEqual(watch["inputSchema"]["required"], ["source"])

    def test_watch_media_requires_source(self):
        resp = mcp.dispatch({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                             "params": {"name": "watch_media", "arguments": {}}})
        self.assertTrue(resp["result"]["isError"])

    def test_unknown_tool_returns_error_content_not_crash(self):
        resp = mcp.dispatch({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                             "params": {"name": "nope", "arguments": {}}})
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("Unknown tool", resp["result"]["content"][0]["text"])


class FlagBuildingTests(unittest.TestCase):
    def test_translate_defaults_on_and_passthrough_flags(self):
        args = mcp._flag_args({"start": "1:00", "end": "2:00", "model": "small", "max_frames": 10})
        self.assertIn("--translate", args)
        self.assertIn("--start", args)
        self.assertIn("1:00", args)
        self.assertIn("--max-frames", args)
        self.assertIn("10", args)

    def test_translate_can_be_disabled(self):
        self.assertNotIn("--translate", mcp._flag_args({"translate": False}))


class CapabilityToolTests(unittest.TestCase):
    def test_check_capabilities_runs_setup_and_returns_json_text(self):
        content, is_error = mcp.check_capabilities({})
        self.assertFalse(is_error)
        self.assertIn("local_media_metadata", content[0]["text"])


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg/ffprobe required for the end-to-end watch_media path")
class WatchMediaIntegrationTests(unittest.TestCase):
    def _existing_runs(self) -> set:
        return set(Path(tempfile.gettempdir()).glob("ai-agent-video-viewer-mcp-*"))

    def test_default_run_inlines_image_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as td:
            sample = Path(td) / "sample.mp4"
            _make_silent_clip(sample)
            before = self._existing_runs()
            content, is_error = mcp.run_watch({"source": str(sample), "max_frames": 2, "translate": False})
            self.assertFalse(is_error, msg=content)
            self.assertIn("image", [c["type"] for c in content])  # contact sheet inlined
            self.assertEqual(self._existing_runs() - before, set(), "default run must remove its temp dir")

    def test_keep_output_retains_dir_and_reports_paths(self):
        with tempfile.TemporaryDirectory() as td:
            sample = Path(td) / "sample.mp4"
            _make_silent_clip(sample)
            content, is_error = mcp.run_watch({"source": str(sample), "max_frames": 2, "translate": False, "keep_output": True})
            self.assertFalse(is_error, msg=content)
            artifacts = next((c["text"] for c in content if c["type"] == "text" and c["text"].startswith("Artifacts")), None)
            self.assertIsNotNone(artifacts)
            out_dir = Path(json.loads(artifacts.split("\n", 1)[1])["output_dir"])
            try:
                self.assertTrue(out_dir.exists(), "keep_output=true must retain the output dir")
            finally:
                shutil.rmtree(out_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
