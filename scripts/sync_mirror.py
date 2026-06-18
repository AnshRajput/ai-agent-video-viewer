#!/usr/bin/env python3
"""Sync the plugin mirror from the root source of truth.

Root ``SKILL.md`` + ``scripts/`` are authoritative. The Claude plugin-style
directory ``skills/ai-agent-video-viewer/`` must stay byte-identical to them
(enforced by ``tests/test_mirror.py``). Run this after editing any mirrored file:

    python3 scripts/sync_mirror.py          # copy root -> mirror
    python3 scripts/sync_mirror.py --check  # exit non-zero if they differ (CI / pre-commit)
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIRROR = ROOT / "skills" / "ai-agent-video-viewer"
MIRRORED = [
    "SKILL.md",
    "scripts/media_watch.py",
    "scripts/setup.py",
    "scripts/install.py",
    "scripts/mcp_server.py",
]


def sync(*, check_only: bool = False) -> int:
    drift: list[str] = []
    for rel in MIRRORED:
        src = ROOT / rel
        dst = MIRROR / rel
        if not src.exists():
            print(f"missing source file: {src}", file=sys.stderr)
            return 2
        if not dst.exists() or src.read_bytes() != dst.read_bytes():
            drift.append(rel)
            if not check_only:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

    if check_only:
        if drift:
            print("mirror drift in: " + ", ".join(drift), file=sys.stderr)
            print("fix with: python3 scripts/sync_mirror.py", file=sys.stderr)
            return 1
        print("mirror in sync")
        return 0

    print("synced: " + ", ".join(drift) if drift else "already in sync")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    return sync(check_only="--check" in argv)


if __name__ == "__main__":
    raise SystemExit(main())
