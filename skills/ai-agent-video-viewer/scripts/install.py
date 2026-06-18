#!/usr/bin/env python3
"""One-command installer for AI Agent Video Viewer.

Installs the local media toolchain (ffmpeg/ffprobe, yt-dlp, whisper.cpp) and
copies the skill into Claude Code's user skill directory and plugin-style test
layout.

The installer is intentionally explicit about bootstrapping Homebrew because
that requires executing Homebrew's remote installer. Package installs and file
copies are shown with --dry-run.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
from pathlib import Path

SKILL_NAME = "ai-agent-video-viewer"
LEGACY_SKILL_NAMES = ["ansh-media-watch"]
REPO_URL = "https://github.com/AnshRajput/ai-agent-video-viewer"


class InstallStep:
    def __init__(self, label: str, command: list[str] | None = None, destination: Path | None = None, note: str | None = None):
        self.label = label
        self.command = command
        self.destination = destination
        self.note = note

    def as_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "command": self.command,
            "destination": str(self.destination) if self.destination else None,
            "note": self.note,
        }


def fail(message: str) -> None:
    raise SystemExit(f"[ai-agent-video-viewer installer] {message}")


def which(name: str) -> str | None:
    return shutil.which(name)


def command_exists(name: str) -> bool:
    return which(name) is not None


def run(command: list[str], *, dry_run: bool = False) -> None:
    printable = " ".join(shlex_quote(part) for part in command)
    if dry_run:
        print(f"DRY-RUN: {printable}")
        return
    print(f"RUN: {printable}")
    subprocess.run(command, check=True)


def shlex_quote(value: str) -> str:
    import shlex

    return shlex.quote(str(value))


def is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def sudo_prefix(has_sudo: bool | None = None) -> list[str]:
    if is_root():
        return []
    if has_sudo is None:
        has_sudo = command_exists("sudo")
    return ["sudo"] if has_sudo else []


def homebrew_install_command() -> list[str]:
    return [
        "/bin/bash",
        "-c",
        '$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)',
    ]


def brew_binary(machine: str | None = None) -> str:
    existing = which("brew")
    if existing:
        return existing
    machine = machine or platform.machine()
    if machine in {"arm64", "aarch64"}:
        return "/opt/homebrew/bin/brew"
    return "/usr/local/bin/brew"


def build_dependency_plan(
    *,
    system: str | None = None,
    machine: str | None = None,
    has_brew: bool | None = None,
    has_apt: bool | None = None,
    has_sudo: bool | None = None,
    install_homebrew: bool = False,
    whisper_missing: bool | None = None,
) -> list[InstallStep]:
    """Return package install/build steps for the current platform.

    This function is pure enough to unit test by injecting platform and command
    availability. It does not execute anything.
    """
    system = system or platform.system()
    machine = machine or platform.machine()
    steps: list[InstallStep] = []

    if whisper_missing is None:
        whisper_missing = not (command_exists("whisper-cli") or command_exists("whisper-cpp"))

    if system == "Darwin":
        if has_brew is None:
            has_brew = command_exists("brew")
        if not has_brew:
            if not install_homebrew:
                fail(
                    "Homebrew is required on macOS to install ffmpeg, yt-dlp, and whisper-cpp automatically. "
                    "Install Homebrew yourself or rerun this installer with --install-homebrew."
                )
            steps.append(
                InstallStep(
                    "Install Homebrew",
                    homebrew_install_command(),
                    note="Explicit opt-in only: this runs Homebrew's official remote installer.",
                )
            )
        steps.append(
            InstallStep(
                "Install ffmpeg, yt-dlp, and whisper-cpp with Homebrew",
                [brew_binary(machine), "install", "ffmpeg", "yt-dlp", "whisper-cpp"],
            )
        )
        return steps

    if system == "Linux":
        if has_apt is None:
            has_apt = command_exists("apt-get")
        if has_apt:
            prefix = sudo_prefix(has_sudo)
            steps.append(InstallStep("Update apt package index", prefix + ["apt-get", "update"]))
            steps.append(
                InstallStep(
                    "Install ffmpeg, yt-dlp, and whisper.cpp build prerequisites with apt",
                    prefix
                    + [
                        "apt-get",
                        "install",
                        "-y",
                        "python3",
                        "git",
                        "curl",
                        "ca-certificates",
                        "ffmpeg",
                        "yt-dlp",
                        "build-essential",
                        "cmake",
                    ],
                )
            )
        else:
            fail(
                "Automatic Linux dependency install currently supports apt-get systems. "
                "Install ffmpeg, ffprobe, yt-dlp, git, cmake, and whisper-cli manually, then rerun with --skip-deps."
            )
        if whisper_missing:
            local_share = "$HOME/.local/share/ai-agent-video-viewer"
            local_bin = "$HOME/.local/bin"
            build_script = (
                "set -euo pipefail; "
                f"mkdir -p {local_share} {local_bin}; "
                f"if [ ! -d {local_share}/whisper.cpp/.git ]; then "
                f"git clone --depth 1 https://github.com/ggerganov/whisper.cpp.git {local_share}/whisper.cpp; "
                "fi; "
                f"cmake -S {local_share}/whisper.cpp -B {local_share}/whisper.cpp/build -DCMAKE_BUILD_TYPE=Release; "
                f"cmake --build {local_share}/whisper.cpp/build --config Release -j 2; "
                f"ln -sf {local_share}/whisper.cpp/build/bin/whisper-cli {local_bin}/whisper-cli; "
                "echo 'Add ~/.local/bin to PATH if whisper-cli is not found by your shell.'"
            )
            steps.append(
                InstallStep(
                    "Build and link whisper.cpp whisper-cli locally",
                    ["/bin/bash", "-lc", build_script],
                )
            )
        return steps

    if system in {"Windows", "MSYS_NT", "CYGWIN_NT"} or system.startswith("MINGW"):
        if command_exists("winget"):
            steps.extend(
                [
                    InstallStep("Install ffmpeg with winget", ["winget", "install", "--id", "Gyan.FFmpeg", "-e", "--accept-package-agreements", "--accept-source-agreements"]),
                    InstallStep("Install yt-dlp with winget", ["winget", "install", "--id", "yt-dlp.yt-dlp", "-e", "--accept-package-agreements", "--accept-source-agreements"]),
                ]
            )
        fail(
            "Windows still needs a manual whisper.cpp/whisper-cli install on PATH after ffmpeg and yt-dlp. "
            "Use the release binaries from https://github.com/ggerganov/whisper.cpp/releases, then rerun setup.py --check."
        )

    fail(f"Unsupported platform for automatic dependency install: {system}")


def copy_tree(src: Path, dst: Path, *, force: bool = False, dry_run: bool = False) -> None:
    if not src.exists():
        fail(f"Source path missing: {src}")
    if dst.exists():
        if not force:
            fail(f"Destination already exists: {dst}. Rerun with --force to replace it.")
        if dry_run:
            print(f"DRY-RUN: remove existing {dst}")
        else:
            if dst.is_symlink() or dst.is_file():
                dst.unlink()
            else:
                shutil.rmtree(dst)
    if dry_run:
        print(f"DRY-RUN: copy {src} -> {dst}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    ignore = shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".DS_Store", ".ai-agent-video-viewer-runs")
    if src.is_file():
        shutil.copy2(src, dst)
    else:
        shutil.copytree(src, dst, ignore=ignore)


def install_standalone_skill(repo_root: Path, home: Path, *, force: bool, dry_run: bool) -> Path:
    dst = home / ".claude" / "skills" / SKILL_NAME
    if dry_run:
        print(f"DRY-RUN: install Claude Code standalone skill to {dst}")
    if dst.exists() and force and not dry_run:
        shutil.rmtree(dst)
    elif dst.exists() and not force:
        fail(f"Claude Code skill already exists: {dst}. Rerun with --force to replace it.")
    if not dry_run:
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo_root / "SKILL.md", dst / "SKILL.md")
        copy_tree(repo_root / "scripts", dst / "scripts", force=True, dry_run=False)
        make_scripts_executable(dst / "scripts")
    return dst


def install_plugin_layout(repo_root: Path, home: Path, *, force: bool, dry_run: bool) -> Path:
    dst = home / "claude-plugins" / SKILL_NAME
    copy_tree(repo_root, dst, force=force, dry_run=dry_run)
    if not dry_run:
        make_scripts_executable(dst / "scripts")
        make_scripts_executable(dst / "skills" / SKILL_NAME / "scripts")
    return dst


def make_scripts_executable(scripts_dir: Path) -> None:
    if not scripts_dir.exists():
        return
    for script in scripts_dir.glob("*.py"):
        mode = script.stat().st_mode
        script.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def build_claude_install_plan(root: Path, home: Path, *, install_skill: bool, install_plugin: bool, force: bool) -> list[InstallStep]:
    required = [root / "SKILL.md", root / "scripts" / "media_watch.py", root / "scripts" / "setup.py", root / ".claude-plugin" / "plugin.json"]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        fail("Repository layout is incomplete; missing: " + ", ".join(missing))
    steps: list[InstallStep] = []
    if install_skill:
        steps.append(InstallStep("Install Claude Code standalone skill", destination=home / ".claude" / "skills" / SKILL_NAME))
    if install_plugin:
        steps.append(InstallStep("Install Claude Code plugin-style layout", destination=home / "claude-plugins" / SKILL_NAME))
    return steps


def install_claude_targets(repo_root: Path, home: Path, *, install_skill: bool, install_plugin: bool, force: bool, dry_run: bool) -> list[Path]:
    installed: list[Path] = []
    build_claude_install_plan(repo_root, home, install_skill=install_skill, install_plugin=install_plugin, force=force)
    if install_skill:
        installed.append(install_standalone_skill(repo_root, home, force=force, dry_run=dry_run))
    if install_plugin:
        installed.append(install_plugin_layout(repo_root, home, force=force, dry_run=dry_run))
    return installed


def remove_legacy_skills(home: Path, *, dry_run: bool = False) -> None:
    for name in LEGACY_SKILL_NAMES:
        path = home / ".claude" / "skills" / name
        if path.exists():
            if dry_run:
                print(f"DRY-RUN: remove legacy Claude Code skill {path}")
            else:
                shutil.rmtree(path)
                print(f"Removed legacy Claude Code skill: {path}")


def run_setup_check(repo_root: Path, *, dry_run: bool = False) -> None:
    cmd = [sys.executable, str(repo_root / "scripts" / "setup.py"), "--check"]
    run(cmd, dry_run=dry_run)


def print_post_install(installed: list[Path], *, home: Path) -> None:
    print("\nAI Agent Video Viewer install complete.")
    if installed:
        print("Installed paths:")
        for path in installed:
            print(f"- {path}")
    print("\nClaude Code usage:")
    print("1. Restart Claude Code terminal sessions and the Claude Code app/IDE integration.")
    print("2. Ask naturally: Watch this video and summarize it: <url>")
    print(f"3. If your Claude Code supports skill slash commands, try: /{SKILL_NAME} <url-or-path> [question]")
    print("\nPlugin-dir usage for local testing:")
    print(f"claude --plugin-dir {home / 'claude-plugins' / SKILL_NAME}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Install AI Agent Video Viewer dependencies and Claude Code skill/plugin targets")
    ap.add_argument("--dry-run", action="store_true", help="print actions without installing packages or copying files")
    ap.add_argument("--json", action="store_true", help="print install plan as JSON and exit")
    ap.add_argument("--force", action="store_true", help="replace existing Claude skill/plugin install directories")
    ap.add_argument("--skip-deps", action="store_true", help="do not install ffmpeg, yt-dlp, or whisper.cpp")
    ap.add_argument("--install-homebrew", action="store_true", help="macOS only: allow this script to run Homebrew's official installer if brew is missing")
    ap.add_argument("--skip-claude-skill", action="store_true", help="do not install ~/.claude/skills/ai-agent-video-viewer")
    ap.add_argument("--skip-claude-plugin", action="store_true", help="do not install ~/claude-plugins/ai-agent-video-viewer")
    ap.add_argument("--remove-legacy", action="store_true", help="remove legacy ~/.claude/skills/ansh-media-watch if present")
    ap.add_argument("--no-check", action="store_true", help="skip final setup.py --check")
    ap.add_argument("--home", type=Path, default=Path.home(), help="home directory for Claude installs; useful for tests")
    ap.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1], help="repository root to install from")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    repo_root = args.repo_root.resolve()
    home = args.home.expanduser().resolve()

    install_skill = not args.skip_claude_skill
    install_plugin = not args.skip_claude_plugin
    plan: list[InstallStep] = []
    if not args.skip_deps:
        plan.extend(build_dependency_plan(install_homebrew=args.install_homebrew))
    plan.extend(build_claude_install_plan(repo_root, home, install_skill=install_skill, install_plugin=install_plugin, force=args.force))

    if args.json:
        print(json.dumps([step.as_dict() for step in plan], indent=2))
        return 0

    print("AI Agent Video Viewer installer")
    print(f"Repository: {repo_root}")
    print(f"Home: {home}")
    print("\nPlanned steps:")
    for step in plan:
        if step.command:
            print(f"- {step.label}: {' '.join(shlex_quote(p) for p in step.command)}")
        elif step.destination:
            print(f"- {step.label}: {step.destination}")
        else:
            print(f"- {step.label}")
        if step.note:
            print(f"  note: {step.note}")

    if args.remove_legacy:
        remove_legacy_skills(home, dry_run=args.dry_run)

    if not args.skip_deps:
        for step in build_dependency_plan(install_homebrew=args.install_homebrew):
            if step.command:
                run(step.command, dry_run=args.dry_run)

    installed = install_claude_targets(repo_root, home, install_skill=install_skill, install_plugin=install_plugin, force=args.force, dry_run=args.dry_run)

    if not args.no_check:
        run_setup_check(repo_root, dry_run=args.dry_run)

    print_post_install(installed, home=home)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
