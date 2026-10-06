import contextlib
import io
import tomllib
import unittest
from unittest.mock import patch

import setup
from tests.helpers import temporary_directory


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.root = self.enterContext(temporary_directory())
        self.config = (setup.ROOT / "config.toml").read_text(encoding="utf-8")
        (self.root / "config.toml").write_text(self.config, encoding="utf-8")
        (self.root / "system_prompt.txt").write_text("Original prompt", encoding="utf-8")
        self.root_patch = patch.object(setup, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def run_setup(self, *args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return setup.main(list(args))

    def test_noninteractive_update_and_rerun_preserve_other_settings(self):
        prompt = self.root / "new.txt"
        prompt.write_text('Rispondi in italiano.\nUsa "citazioni".', encoding="utf-8")
        with patch.object(setup.subprocess, "run") as run:
            self.assertEqual(self.run_setup("--non-interactive", "--skip-pull", "--llm", "new:1b", "--embedding", "new-embed", "--prompt-file", str(prompt)), 0)
            run.assert_not_called()
        updated = tomllib.loads((self.root / "config.toml").read_text(encoding="utf-8"))
        original = tomllib.loads(self.config)
        self.assertEqual(updated["models"], {"llm": "new:1b", "embedding": "new-embed"})
        for section in original.keys() - {"models"}:
            self.assertEqual(updated[section], original[section])
        self.assertEqual(self.run_setup("--non-interactive", "--skip-pull"), 0)
        self.assertEqual((self.root / "system_prompt.txt").read_text(encoding="utf-8"), prompt.read_text(encoding="utf-8"))

    def test_failed_pull_does_not_save_settings(self):
        error = setup.subprocess.CalledProcessError(1, ["ollama", "pull"])
        with patch.object(setup.shutil, "which", return_value="ollama"), patch.object(setup.subprocess, "run", side_effect=error):
            self.assertEqual(self.run_setup("--non-interactive", "--llm", "new:1b"), 1)
        self.assertEqual((self.root / "config.toml").read_text(encoding="utf-8"), self.config)

    def test_pull_then_ingest_with_saved_settings(self):
        def command(argv, **kwargs):
            if argv[0] == setup.sys.executable:
                cfg = tomllib.loads((self.root / "config.toml").read_text(encoding="utf-8"))
                self.assertEqual(cfg["models"]["embedding"], "new-embed")
        with patch.object(setup.shutil, "which", return_value="ollama"), patch.object(setup.subprocess, "run", side_effect=command) as run:
            self.assertEqual(self.run_setup("--non-interactive", "--embedding", "new-embed", "--ingest"), 0)
            self.assertEqual(run.call_count, 3)
            self.assertEqual(run.call_args.args[0], [setup.sys.executable, str(self.root / "ingest.py")])

    def test_interactive_defaults_and_empty_prompt(self):
        with patch("builtins.input", side_effect=["", "", "n", "n"]):
            self.assertEqual(self.run_setup("--skip-pull"), 0)
        empty = self.root / "empty.txt"
        empty.write_text(" ", encoding="utf-8")
        self.assertEqual(self.run_setup("--non-interactive", "--skip-pull", "--prompt-file", str(empty)), 1)
        self.assertEqual((self.root / "system_prompt.txt").read_text(encoding="utf-8"), "Original prompt")


if __name__ == "__main__":
    unittest.main()
