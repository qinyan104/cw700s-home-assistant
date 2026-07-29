from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = {
    "custom_components/cw700s_downloader/__init__.py",
    "custom_components/cw700s_downloader/manifest.json",
    "custom_components/cw700s_downloader/services.yaml",
    "home-assistant/cw700s_download.py",
    "home-assistant/packages/cw700s_health_package.yaml",
    "home-assistant/packages/cw700s_ai_package.yaml",
    "home-assistant/scripts/cw700s_health.py",
    "home-assistant/scripts/cw700s_ai_status.py",
    "home-assistant/dashboard/cw700s_dashboard_card.yaml",
    "home-assistant/dashboard/cw700s_health_card.yaml",
    "home-assistant/dashboard/cw700s_ai_card.yaml",
    "home-assistant/www/cw700s-recent-card.js",
    "windows-ai/cw700s_ai_classifier.py",
    "windows-ai/运行CW700S_AI分类.bat",
    "windows-ai/run_ai_classifier.ps1",
    "windows-ai/show_recent_results.ps1",
}

FORBIDDEN_SUFFIXES = {".db", ".log", ".mp4", ".mov", ".avi", ".mkv", ".pt"}
PRIVATE_ENTITY_PATTERN = re.compile(
    r"camera\.isa_hlzoom_[a-z0-9]+_camera_control"
)


class RepositoryTests(unittest.TestCase):
    def test_private_entity_patterns_are_removed(self) -> None:
        matches = []
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file() or ".git" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if PRIVATE_ENTITY_PATTERN.search(text):
                matches.append(str(path.relative_to(ROOT)))
        self.assertEqual([], matches)

    def test_required_files_exist(self) -> None:
        missing = sorted(path for path in REQUIRED_FILES if not (ROOT / path).is_file())
        self.assertEqual([], missing)

    def test_manifest_is_valid(self) -> None:
        manifest = json.loads(
            (ROOT / "custom_components/cw700s_downloader/manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("cw700s_downloader", manifest["domain"])
        self.assertIn("xiaomi_miot", manifest["dependencies"])

    def test_python_files_parse(self) -> None:
        for path in sorted(ROOT.rglob("*.py")):
            with self.subTest(path=path.relative_to(ROOT)):
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    def test_yaml_files_are_nonempty_and_tab_free(self) -> None:
        for path in sorted(ROOT.rglob("*.yaml")):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertTrue(text.strip())
                self.assertNotIn("\t", text)

    def test_runtime_artifacts_are_not_committed(self) -> None:
        forbidden = sorted(
            str(path.relative_to(ROOT))
            for path in ROOT.rglob("*")
            if path.is_file() and path.suffix.lower() in FORBIDDEN_SUFFIXES
        )
        self.assertEqual([], forbidden)

if __name__ == "__main__":
    unittest.main()
