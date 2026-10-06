import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import ollama
from threadleaf import grounded_answers, rag


@unittest.skipUnless(os.environ.get("THREADLEAF_TEST_OLLAMA") == "1", "Requires local Ollama; set THREADLEAF_TEST_OLLAMA=1")
class IntentIntegrationTests(unittest.TestCase):
    def test_greetings_and_mixed_document_requests(self):
        cases = json.loads((Path(__file__).parent / "fixtures" / "intent_regression.json").read_text(encoding="utf-8"))
        client = ollama.Client(timeout=60)
        grounded_answers._intent_classifier.cache_clear()
        self.addCleanup(grounded_answers._intent_classifier.cache_clear)
        with patch.object(grounded_answers.ollama, "embed", client.embed):
            for case in cases:
                with self.subTest(question=case["question"]):
                    result = grounded_answers.is_casual(case["question"], rag.CFG["models"]["embedding"])
                    self.assertEqual(result, case["casual"])
