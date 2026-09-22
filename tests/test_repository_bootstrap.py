import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


class RepositoryBootstrapTests(unittest.TestCase):
    def test_required_repository_files_exist(self):
        root = Path(__file__).resolve().parents[1]
        required = [
            root / "AGENTS.md",
            root / "docs" / "design.md",
            root / "docs" / "agents" / "implementation-workflow.md",
            root / ".sandcastle" / "main.mts",
            root / ".codex" / "config.toml",
            root / "package.json",
            root / "start.sh",
        ]
        self.assertEqual([], [str(path) for path in required if not path.is_file()])
        self.assertTrue(os.access(root / "start.sh", os.X_OK))

    def test_package_scripts_are_runnable_contracts(self):
        package = json.loads(Path("package.json").read_text())
        self.assertIn("sandcastle:reviewed", package["scripts"])
        self.assertIn("sandcastle:check", package["scripts"])
        self.assertEqual("python3 -m jev_demo", package["scripts"]["start"])

    def test_stdlib_application_module_not_yet_required_by_bootstrap(self):
        result = subprocess.run(
            [sys.executable, "-c", "import pathlib; assert pathlib.Path('docs/design.md').is_file()"],
            check=False,
        )
        self.assertEqual(0, result.returncode)


if __name__ == "__main__":
    unittest.main()
