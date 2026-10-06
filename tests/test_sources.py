import unittest
from unittest.mock import MagicMock, patch
from threadleaf import rag


class SourceTests(unittest.TestCase):
    def test_small_talk_skips_retrieval_and_sources(self):
        collection = MagicMock()
        collection.count.return_value = 2
        with patch.object(rag, "_collection", return_value=collection), \
             patch.object(rag.grounded_answers, "is_casual", return_value=True), \
             patch.object(rag, "_embed") as embed, \
             patch.object(rag.retrieval, "retrieve") as retrieve, \
             patch.object(rag.ollama, "chat", return_value={"message": {"content": "Glad to chat!"}}) as chat:
            result = rag.ask("Hey what'up?", history=[{"role": "assistant", "content": "Una risposta precedente in italiano."}])
        self.assertEqual(result["answer_kind"], "casual")
        self.assertEqual(result["sources"], [])
        embed.assert_not_called()
        retrieve.assert_not_called()
        messages = chat.call_args.kwargs["messages"]
        self.assertEqual(messages[-1]["content"], "Hey what'up?")
        self.assertNotIn("The context documents are written in", messages[0]["content"])
        self.assertNotIn("CONTEXT:", result["prompt"])
        self.assertNotIn("RESOLVED QUESTION:", messages[-1]["content"])
        self.assertIn("Answer in the same language as the question", messages[0]["content"])

    def test_extractive_answer_lists_only_selected_passage_or_no_sources(self):
        collection = MagicMock()
        collection.count.return_value = 2
        chunks = [{"source": "a.pdf", "text": "An unrelated document", "distance": 0.1},
                  {"source": "b.pdf", "text": "Alex has a degree in physics.", "distance": 0.1}]
        for passage, expected in ((2, ["b.pdf"]), (0, [])):
            with patch.object(rag, "_collection", return_value=collection), \
                 patch.dict(rag.CFG["llm"], {"answer_mode": "extractive"}), \
                 patch.object(rag.grounded_answers, "is_casual", return_value=False), \
                 patch.object(rag, "_embed", return_value=[[1.0]]), \
                 patch.object(rag.retrieval, "retrieve", return_value=chunks), \
                 patch.object(rag.ollama, "chat", return_value={"message": {"content": f'{{"passage":{passage}}}'}}):
                self.assertEqual(rag.ask("What degree does Alex have?")["sources"], expected)
