import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("install", ROOT / "scripts" / "install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallPlannerTests(unittest.TestCase):
    def test_macos_plan_installs_homebrew_prereq_and_media_tools(self):
        plan = installer.build_dependency_plan(
            system="Darwin",
            machine="arm64",
            has_brew=False,
            has_sudo=False,
            install_homebrew=True,
        )
        labels = [step.label for step in plan]
        self.assertIn("Install Homebrew", labels)
        self.assertIn("Install ffmpeg, yt-dlp, and whisper-cpp with Homebrew", labels)
        brew_step = next(step for step in plan if "ffmpeg" in step.label)
        self.assertIn("brew", brew_step.command[0])
        self.assertIn("ffmpeg", brew_step.command)
        self.assertIn("yt-dlp", brew_step.command)
        self.assertIn("whisper-cpp", brew_step.command)

    def test_macos_plan_refuses_implicit_homebrew_bootstrap(self):
        with self.assertRaises(SystemExit):
            installer.build_dependency_plan(
                system="Darwin",
                machine="arm64",
                has_brew=False,
                has_sudo=False,
                install_homebrew=False,
            )

    def test_linux_plan_uses_apt_for_base_tools_and_builds_whisper_cpp(self):
        plan = installer.build_dependency_plan(
            system="Linux",
            machine="x86_64",
            has_apt=True,
            has_sudo=True,
            whisper_missing=True,
        )
        joined = [" ".join(step.command) for step in plan]
        self.assertTrue(any("apt-get" in cmd and "ffmpeg" in cmd and "yt-dlp" in cmd for cmd in joined))
        self.assertTrue(any("ggerganov/whisper.cpp" in cmd for cmd in joined))

    def test_claude_targets_include_standalone_skill_and_plugin_layout(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            (root / "scripts").mkdir(parents=True)
            (root / "skills" / "ai-agent-video-viewer" / "scripts").mkdir(parents=True)
            (root / "SKILL.md").write_text("name: ai-agent-video-viewer\n")
            (root / "scripts" / "media_watch.py").write_text("print('ok')\n")
            (root / "scripts" / "setup.py").write_text("print('ok')\n")
            (root / ".claude-plugin").mkdir()
            (root / ".claude-plugin" / "plugin.json").write_text('{"name":"ai-agent-video-viewer"}\n')
            (root / "skills" / "ai-agent-video-viewer" / "SKILL.md").write_text("name: ai-agent-video-viewer\n")
            (root / "skills" / "ai-agent-video-viewer" / "scripts" / "media_watch.py").write_text("print('ok')\n")
            (root / "skills" / "ai-agent-video-viewer" / "scripts" / "setup.py").write_text("print('ok')\n")
            home = Path(td) / "home"

            plan = installer.build_claude_install_plan(root, home, install_skill=True, install_plugin=True, force=True)
            destinations = [step.destination for step in plan if step.destination]
            self.assertIn(home / ".claude" / "skills" / "ai-agent-video-viewer", destinations)
            self.assertIn(home / "claude-plugins" / "ai-agent-video-viewer", destinations)

    def test_target_install_copies_portable_skill_to_arbitrary_dir(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            (root / "scripts").mkdir(parents=True)
            (root / "SKILL.md").write_text("name: ai-agent-video-viewer\n")
            (root / "scripts" / "media_watch.py").write_text("print('ok')\n")
            (root / "scripts" / "setup.py").write_text("print('ok')\n")

            target = Path(td) / "any-harness" / "skills" / "ai-agent-video-viewer"
            returned = installer.install_skill_files(root, target, force=False, dry_run=False, label="test")
            self.assertEqual(returned, target)
            self.assertTrue((target / "SKILL.md").exists())
            self.assertTrue((target / "scripts" / "media_watch.py").exists())
            # dry-run must not write
            target2 = Path(td) / "dry" / "ai-agent-video-viewer"
            installer.install_skill_files(root, target2, force=False, dry_run=True, label="test")
            self.assertFalse(target2.exists())


if __name__ == "__main__":
    unittest.main()
