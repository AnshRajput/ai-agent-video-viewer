"""Guard against drift between the root source of truth and the plugin mirror.

The root SKILL.md + scripts/ are authoritative; skills/ai-agent-video-viewer/ is
a byte-for-byte mirror used for Claude plugin-style installs. If they diverge,
plugin users silently run stale code. Re-sync the mirror from root when this fails.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIRROR = ROOT / "skills" / "ai-agent-video-viewer"
MIRRORED_FILES = [
    "SKILL.md",
    "scripts/media_watch.py",
    "scripts/setup.py",
    "scripts/install.py",
    "scripts/mcp_server.py",
]


class MirrorSyncTests(unittest.TestCase):
    def test_plugin_mirror_matches_source_of_truth(self):
        for rel in MIRRORED_FILES:
            with self.subTest(file=rel):
                src = ROOT / rel
                dst = MIRROR / rel
                self.assertTrue(dst.exists(), f"missing mirror file: {dst}")
                self.assertEqual(
                    src.read_bytes(),
                    dst.read_bytes(),
                    f"mirror drift in {rel}; re-sync skills/ai-agent-video-viewer/ from root",
                )


if __name__ == "__main__":
    unittest.main()
