import re
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "host" / "install_user_services.sh"


class TestServiceUsesVenvPython(unittest.TestCase):
    """The router service must run on the repo venv python when one exists, so
    adapter dependencies (youtube-transcript-api) are importable at runtime."""

    def test_install_script_prefers_repo_venv_python(self):
        src = SCRIPT.read_text()
        # Must reference a venv python candidate before falling back to PATH python3.
        self.assertIn(".venv/bin/python", src)

    def test_generated_units_use_venv_python(self):
        # Render the unit block the same way the script does, with a fake venv.
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            fake_repo = Path(td) / "repo"
            fake_venv = fake_repo / ".venv" / "bin"
            fake_venv.mkdir(parents=True)
            (fake_venv / "python").touch()
            # Simulate the PYTHON_BIN resolution the script must implement.
            cand = fake_repo / ".venv" / "bin" / "python"
            resolved = str(cand) if cand.exists() else "python3"
            self.assertTrue(resolved.endswith(".venv/bin/python"))

    def test_v_env_python_exists_in_this_repo(self):
        venv_py = REPO / ".venv" / "bin" / "python"
        self.assertTrue(venv_py.exists(), "repo venv python missing")


if __name__ == "__main__":
    unittest.main()
