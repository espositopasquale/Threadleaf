import re
import unittest
from unittest.mock import MagicMock, patch
import numpy as np
from threadleaf import coreference


class CoreferenceTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(coreference, "_retry_after", 0)
        patcher.start()
        self.addCleanup(patcher.stop)

    def rewrite(self, text, question, links):
        return coreference._replace_mentions(text, text.index(question), list(re.finditer(r"\w+|[^\w\s]", text)), links)

    def test_english_and_italian_references_preserve_intent(self):
        self.assertEqual(self.rewrite("Who is Alex?\nWhat did he study?", "What did he study?", [((6, 6), (2, 2))]), "What did Alex study?")
        self.assertEqual(self.rewrite("Chi è Alex?\nDove vive lui?", "Dove vive lui?", [((6, 6), (2, 2))]), "Dove vive Alex?")

    def test_multiword_antecedent_and_chained_references(self):
        text = "Alex Smith arrived.\nHe spoke.\nWhere does he live?"
        self.assertEqual(self.rewrite(text, "Where does he live?", [((4, 4), (0, 1)), ((9, 9), (4, 4))]), "Where does Alex Smith live?")

    def test_new_topic_and_invalid_overlapping_links_stay_unchanged(self):
        text = "Alex arrived.\nWhat is quantum mechanics?"
        question = "What is quantum mechanics?"
        self.assertEqual(self.rewrite(text, question, []), question)
        self.assertEqual(self.rewrite(text, question, [((99, 99), (0, 0))]), question)
        self.assertEqual(self.rewrite(text, question, [((3, 4), (0, 0)), ((4, 4), (0, 0))]), question)

    def test_missing_model_preserves_question_and_uses_retry_cooldown(self):
        config = {"enabled": True, "model": "test", "revision": "test"}
        history = [{"role": "user", "content": "Who is Alex?"}]
        with patch.object(coreference, "_load", side_effect=RuntimeError("Missing")) as load, patch.object(coreference.logger, "warning"):
            for _ in range(2):
                self.assertEqual(coreference.resolve("What did he study?", history, config), "What did he study?")
        load.assert_called_once()

    def test_model_outputs_drive_reference_links(self):
        tokenizer = MagicMock()
        tokenizer.encode.return_value = MagicMock(ids=[0, 10, 11, 2], word_ids=[None, 0, 1, None])
        session = MagicMock()
        session.run.return_value = [np.array([[[0, 0], [1, 1]]]), np.array([[[0], [0]]]), np.array([[-1, 0]])]
        links = coreference._links(["Alex", "he"], session, tokenizer, {"max_span_width": 1, "max_spans": 3})
        self.assertEqual(links, [((1, 1), (0, 0))])
        inputs = session.run.call_args.args[1]
        self.assertEqual(inputs["offsets"].tolist(), [[[1, 1], [2, 2]]])
        self.assertEqual(inputs["spans"].tolist(), [[[0, 0], [1, 1], [-1, -1]]])

    def test_long_inputs_do_not_drop_question_mentions(self):
        tokenizer = MagicMock()
        tokenizer.encode.return_value = MagicMock(ids=list(range(513)))
        session = MagicMock()
        self.assertEqual(coreference._links(["Alex"], session, tokenizer, {"max_span_width": 5, "max_spans": 512}), [])
        session.run.assert_not_called()
