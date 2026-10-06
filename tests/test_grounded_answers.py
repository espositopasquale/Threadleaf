import unittest
from unittest.mock import patch
from threadleaf import grounded_answers


class GroundedAnswerTests(unittest.TestCase):
    def test_returns_only_original_passage_and_discards_invented_summary(self):
        reply, kind = grounded_answers.render('{"passage":1,"answer":"Invented summary"}', [{"text":"The minimum age is 18 years."}], "en")
        self.assertEqual(kind, "document")
        self.assertIn("The minimum age is 18 years.", reply)
        self.assertNotIn("Invented", reply)

    def test_invalid_json_bad_ids_and_missing_context_abstain(self):
        for content in ('Invented answer', '{"passage":0}', '{"passage":2}', '{"passage":true}', '{"passage":"1"}', '{"answer":"Invented"}'):
            _, kind = grounded_answers.render(content, [{"text":"Actual passage"}], "en")
            self.assertEqual(kind, "insufficient")
        self.assertEqual(grounded_answers.render('{"passage":1}', [], "en")[1], "insufficient")

    def test_casual_bypass_does_not_accept_document_question_after_greeting(self):
        with patch.object(grounded_answers, "_intent_classifier", return_value=grounded_answers.np.array([1, -1, 0])), \
             patch.object(grounded_answers.ollama, "embed", return_value={"embeddings": [[1, 0]]}) as embed:
            self.assertTrue(grounded_answers.is_casual("How's your day going?", "test-model"))
            self.assertEqual(embed.call_args.kwargs["model"], "test-model")
        with patch.object(grounded_answers, "_intent_classifier", return_value=grounded_answers.np.array([1, -1, 0])), \
             patch.object(grounded_answers.ollama, "embed", return_value={"embeddings": [[0.7, 0.7]]}):
            self.assertFalse(grounded_answers.is_casual("Hello, summarize the CV", "test-model"))

    def test_invalid_intent_classification_never_bypasses_grounding(self):
        for vectors in ([], [[0, 0]], [[float("nan"), 0]]):
            with patch.object(grounded_answers, "_intent_classifier", return_value=grounded_answers.np.array([1, -1, 0])), \
                 patch.object(grounded_answers.ollama, "embed", return_value={"embeddings": vectors}):
                self.assertFalse(grounded_answers.is_casual("Question", "test-model"))

    def test_abstention_uses_question_language(self):
        self.assertIn("The retrieved", grounded_answers.render('{"passage":0}', [], "auto", "What is the password?")[0])
        self.assertIn("I passaggi", grounded_answers.render('{"passage":0}', [], "auto", "Qual ? la password?")[0])


    def test_sentence_extraction_skips_headings_and_preserves_multiline_prose(self):
        text = "INTRODUCTION\n(Telescope).\nThe telescope collects light\nfrom distant astronomical objects.\nOther equipment is described elsewhere."
        reply, kind = grounded_answers.render('{"passage":1}', [{"text": text}], "en", "Define telescope")
        self.assertEqual(kind, "document")
        self.assertIn("The telescope collects light from distant astronomical objects.", reply)
        self.assertNotIn("INTRODUCTION", reply)

    def test_unsupported_topic_abstains_despite_model_selecting_passage(self):
        chunks = [{"text": "An inventory is made by an appointed official.", "distance": 0.75}]
        _, kind = grounded_answers.render('{"passage":1}', chunks, "en", "What is my account password?")
        self.assertEqual(kind, "insufficient")

    def test_semantically_close_synonyms_can_work_without_identical_query_words(self):
        chunks = [{"text": "An adult reaches maturity at eighteen years.", "distance": 0.3}]
        _, kind = grounded_answers.render('{"passage":1}', chunks, "en", "When does someone become legally grown up?")
        self.assertEqual(kind, "document")


if __name__ == "__main__":
    unittest.main()
