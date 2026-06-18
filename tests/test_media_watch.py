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


class WhisperJsonTests(unittest.TestCase):
    def test_start_offset_is_applied(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "whisper.json"
            path.write_text(json.dumps({"transcription": [{"text": "hello", "offsets": {"from": 1000, "to": 2500}}]}))
            segments = media_watch.segments_from_whisper_json(path, base_offset=80)
            self.assertEqual(segments[0]["start"], 81.0)
            self.assertEqual(segments[0]["end"], 82.5)
            self.assertEqual(segments[0]["time"], "01:21")


if __name__ == "__main__":
    unittest.main()
