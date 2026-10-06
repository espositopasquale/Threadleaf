import unittest
from unittest.mock import MagicMock, patch

from threadleaf import reranker
from tests import test_retrieval
from threadleaf import retrieval


CONFIG = {"enabled": True, "model": "test/model", "revision": "test", "top_n": 24}


class RerankerTests(unittest.TestCase):
    def setUp(self):
        reranker._retry_after.clear()
        reranker._scores.cache_clear()
        self.addCleanup(reranker._retry_after.clear)
        self.addCleanup(reranker._scores.cache_clear)

    def test_scores_sort_candidates_before_final_cut_and_preserve_metadata(self):
        chunks = [{"id": str(i), "text": f"Text {i}", "source": "selected.pdf", "distance": 0.4} for i in range(3)]
        with patch.object(reranker, "_scores", return_value=(0.2, -1.0, 4.5)):
            result = reranker.rerank("Question", chunks, 1, CONFIG)
        self.assertEqual(result[0]["id"], "2")
        self.assertEqual(result[0]["rerank_score"], 4.5)
        self.assertEqual(result[0]["source"], "selected.pdf")
        self.assertEqual(result[0]["distance"], 0.4)
        self.assertNotIn("rerank_score", chunks[2])

    def test_disabled_and_empty_input_do_not_load_model(self):
        with patch.object(reranker, "_scores") as scores:
            self.assertEqual(reranker.rerank("Question", [], 4, CONFIG), [])
            self.assertEqual(reranker.rerank("Question", [{"text": "Text"}], 4, {"enabled": False}), [{"text": "Text"}])
        scores.assert_not_called()

    def test_missing_model_falls_back_and_uses_retry_cooldown(self):
        chunks = [{"text": "First"}, {"text": "Second"}]
        with patch.object(reranker, "_scores", side_effect=RuntimeError("Missing weights")) as scores, patch.object(reranker.logger, "warning"):
            for _ in range(2):
                self.assertEqual(reranker.rerank("Question", chunks, 1, CONFIG), chunks[:1])
        scores.assert_called_once()

    def test_onnx_batches_pairs_and_caches_repeated_scores(self):
        import numpy as np
        tokenizer = MagicMock()
        tokenizer.encode.return_value.ids = [1, 2]
        tokenizer.decode.return_value = "Question"
        encoding = MagicMock(ids=[1, 2, 3], attention_mask=[1, 1, 1], type_ids=[0, 0, 0])
        tokenizer.encode_batch.side_effect = [[encoding, encoding], [encoding]]
        session = MagicMock()
        item = MagicMock()
        item.name = "input_ids"
        item.type = "tensor(int64)"
        session.get_inputs.return_value = [item]
        session.run.side_effect = [[np.array([[1.0], [2.0]])], [np.array([[3.0]])]]
        args = ("test/model", "test", "weights.onnx", 384, 2, 2, "Question", ("A", "B", "C"))
        with patch.object(reranker, "_load", return_value=(tokenizer, session)):
            self.assertEqual(reranker._scores(*args), (1.0, 2.0, 3.0))
            self.assertEqual(reranker._scores(*args), (1.0, 2.0, 3.0))
        self.assertEqual(session.run.call_count, 2)
        self.assertEqual(tokenizer.encode_batch.call_args_list[0].args[0], [("Question", "A"), ("Question", "B")])


class RerankerRetrievalTests(unittest.TestCase):
    setUp = test_retrieval.RetrievalTests.setUp
    def test_reranker_sees_more_than_final_k_without_unselected_sources(self):
        with patch.object(reranker, "_scores", return_value=(0.0, 5.0)) as scores:
            chunks = retrieval.retrieve(self.col, "unmatched", [1.0, 0.0], 1, 2, rerank_config=CONFIG)
        self.assertEqual(chunks[0]["source"], "b.txt")
        self.assertEqual(len(scores.call_args.args[-1]), 2)
        with patch.object(reranker, "_scores", return_value=(1.0,)) as scores:
            chunks = retrieval.retrieve(self.col, "quasar", [1.0, 0.0], 1, 1,
                                        where={"source": {"$in": ["a.txt"]}}, rerank_config=CONFIG)
        self.assertEqual(chunks[0]["source"], "a.txt")
        self.assertEqual(len(scores.call_args.args[-1]), 1)


if __name__ == "__main__":
    unittest.main()
