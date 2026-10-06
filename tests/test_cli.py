import io
import sys
import unittest
from unittest.mock import patch

import ollama
from rich.console import Console
import cli


class CliTests(unittest.TestCase):
    def run_cli(self, arguments, response=None, error=None, inputs=()):
        buffer = io.StringIO()
        with patch.object(sys, "argv", ["cli.py", *arguments]), \
             patch.object(cli, "Console", side_effect=lambda **kw: Console(file=buffer, width=100, no_color=True, **kw)), \
             patch.object(cli.ollama, "list", return_value=response, side_effect=error), \
             patch("builtins.input", side_effect=inputs), \
             patch.object(cli.rag, "ask") as ask:
            cli.main()
        ask.assert_not_called()
        return buffer.getvalue()

    def test_lists_installed_models_without_starting_chat(self):
        response = ollama.ListResponse(models=[
            {"model": "qwen2.5:0.5b", "size": 397800000, "details": {"parameter_size": "494M", "quantization_level": "Q4_K_M"}},
            {"model": "nomic-embed-text-v2-moe:latest", "size": 957700000},
        ])
        text = self.run_cli(["--list-models", "--model", "qwen2.5:0.5b"], response=response)
        for value in ("Installed Ollama models", "qwen2.5:0.5b", "nomic-embed-text-v2-moe:latest", "Chat", "Embedding", "Q4_K_M"):
            self.assertIn(value, text)
        self.assertNotIn("You ›", text)

    def test_english_help_and_interactive_model_command(self):
        text = self.run_cli([], response=ollama.ListResponse(models=[]), inputs=["/help", "/models", "exit"])
        self.assertIn("Your documents, in conversation.", text)
        self.assertIn("Commands", text)
        self.assertIn("/models", text)
        self.assertIn("No models installed", text)
        self.assertNotIn("Impostazioni", text)

    def test_offline_ollama_has_clear_error_and_nonzero_exit(self):
        with self.assertRaises(SystemExit) as caught:
            self.run_cli(["--list-models"], error=ConnectionError("Unavailable"))
        self.assertEqual(caught.exception.code, 1)

    def test_interactive_model_listing_error_keeps_cli_usable(self):
        text = self.run_cli([], error=ConnectionError("Unavailable"), inputs=["/models", "exit"])
        self.assertIn("Start Ollama and try again", text)
        self.assertIn("See you soon!", text)

    def test_sources_are_on_demand_and_cleared_after_small_talk(self):
        buffer = io.StringIO()
        commands = iter(["Question", "/sources", "Hello", "/sources", "exit"])
        def read_input(*args):
            command = next(commands)
            if command == "/sources" and "Document answer" in buffer.getvalue() and "Hello there" not in buffer.getvalue():
                self.assertNotIn("private-document.pdf", buffer.getvalue())
                self.assertIn("[1 source · /sources]", buffer.getvalue())
            return command
        with patch.object(sys, "argv", ["cli.py"]), \
             patch.object(cli, "Console", side_effect=lambda **kw: Console(file=buffer, width=100, no_color=True, **kw)), \
             patch("builtins.input", side_effect=read_input), \
             patch.object(cli.rag, "ask", side_effect=[
                 {"reply": "Document answer", "sources": ["private-document.pdf"], "answer_kind": "document"},
                 {"reply": "Hello there", "sources": ["should-not-appear.pdf"], "answer_kind": "casual"}]):
            cli.main()
        text = buffer.getvalue()
        self.assertEqual(text.count("private-document.pdf"), 1)
        self.assertNotIn("should-not-appear.pdf", text)
        self.assertEqual(text.count("[1 source · /sources]"), 1)
        self.assertIn("The latest reply has no document sources.", text)


if __name__ == "__main__":
    unittest.main()
