import argparse
import json
import tempfile
import unittest
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("media_watch", ROOT / "scripts" / "media_watch.py")
media_watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(media_watch)


class TimeParsingTests(unittest.TestCase):
    def test_valid_timestamps(self):
        self.assertEqual(media_watch.parse_time("12"), 12)
        self.assertEqual(media_watch.parse_time("01:02"), 62)
        self.assertEqual(media_watch.parse_time("01:02:03"), 3723)

    def test_invalid_timestamps(self):
        for value in ["abc", "-1", "1:99", "1:2:99", "1:2:3:4", "nan", "inf"]:
            with self.subTest(value=value):
                with self.assertRaises(argparse.ArgumentTypeError):
                    media_watch.parse_time(value)

    def test_precise_format(self):
        self.assertEqual(media_watch.fmt_time(62.5, precise=True), "01:02.50")


class SafetyTests(unittest.TestCase):
    def test_private_urls_are_rejected_by_default(self):
        for url in ["http://localhost/video.mp4", "https://127.0.0.1/video.mp4", "http://[::1]/video.mp4"]:
            with self.subTest(url=url):
                with self.assertRaises(SystemExit):
                    media_watch.validate_public_url(url)

    def test_private_urls_can_be_allowed_explicitly(self):
        media_watch.validate_public_url("http://localhost/video.mp4", allow_private=True)

    def test_file_size_limit_is_enforced(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sample.bin"
            path.write_bytes(b"x" * 2048)
            with self.assertRaises(SystemExit):
                media_watch.enforce_file_size(path, 0.001, "sample")
            media_watch.enforce_file_size(path, 1, "sample")

    def test_output_dir_must_be_empty_unless_forced(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            out.mkdir()
            (out / "existing.txt").write_text("existing")
            with self.assertRaises(SystemExit):
                media_watch.prepare_output_dir(str(out), force=False)
            self.assertEqual(media_watch.prepare_output_dir(str(out), force=True), out.resolve())

    def test_output_dir_rejects_home(self):
        with self.assertRaises(SystemExit):
            media_watch.prepare_output_dir(str(Path.home()), force=True)

    def test_downloaded_media_must_stay_inside_output_dir(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "root"
            root.mkdir()
            outside = Path(td) / "outside.mp4"
            outside.write_bytes(b"data")
            with self.assertRaises(SystemExit):
                media_watch.ensure_inside(outside, root, "media")

    def test_duration_limit_allows_focused_range(self):
        info = {"duration": 10_000.0}
        with self.assertRaises(SystemExit):
            media_watch.enforce_duration(info, 100.0, None, None)
        media_watch.enforce_duration(info, 100.0, 10.0, 20.0)


class WhisperJsonTests(unittest.TestCase):
    def test_start_offset_is_applied(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "whisper.json"
            path.write_text(json.dumps({"transcription": [{"text": "hello", "offsets": {"from": 1000, "to": 2500}}]}))
            segments = media_watch.segments_from_whisper_json(path, base_offset=80)
            self.assertEqual(segments[0]["start"], 81.0)
            self.assertEqual(segments[0]["end"], 82.5)
            self.assertEqual(segments[0]["time"], "01:21")


class PreciseTimeCarryTests(unittest.TestCase):
    def test_centisecond_boundary_carries(self):
        # frac rounding must not produce ".100"; it must carry into seconds.
        self.assertEqual(media_watch.fmt_time(2.999, precise=True), "00:03")
        self.assertEqual(media_watch.fmt_time(3599.999, precise=True), "01:00:00")
        self.assertEqual(media_watch.fmt_time(0.995, precise=True), "00:01")
        self.assertEqual(media_watch.fmt_time(62.5, precise=True), "01:02.50")


class TranscriptionDegradationTests(unittest.TestCase):
    def test_setup_failure_degrades_instead_of_aborting(self):
        # whisper is present, but audio extraction fails: the run must not abort,
        # so any already-extracted frames still get reported.
        orig_find, orig_extract = media_watch.find_whisper, media_watch.extract_audio
        try:
            media_watch.find_whisper = lambda: "/fake/whisper-cli"

            def boom(*args, **kwargs):
                raise SystemExit("ffmpeg produced no audio file")

            media_watch.extract_audio = boom
            with tempfile.TemporaryDirectory() as td:
                segments, source, state = media_watch.transcribe(
                    Path(td) / "m.mp4", Path(td), None, None, "small", "auto", True
                )
            self.assertEqual(segments, [])
            self.assertIsNone(source)
            self.assertEqual(state, "failed")
        finally:
            media_watch.find_whisper, media_watch.extract_audio = orig_find, orig_extract


if __name__ == "__main__":
    unittest.main()
