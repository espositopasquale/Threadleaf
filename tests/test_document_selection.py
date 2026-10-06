import unittest
from unittest.mock import MagicMock, patch

import chromadb
from fastapi.testclient import TestClient

from threadleaf import rag
import server
from threadleaf import document_titles


class DocumentSelectionTests(unittest.TestCase):
    def setUp(self):
        intent_patch = patch.object(rag.grounded_answers, "is_casual", return_value=False)
        intent_patch.start()
        self.addCleanup(intent_patch.stop)
        config_patch = patch.dict(rag.CFG, {"reranker": {"enabled": False}})
        config_patch.start()
        self.addCleanup(config_patch.stop)
        self.client = chromadb.EphemeralClient()
        self.collection = self.client.create_collection("selection-test", embedding_function=None)
        self.collection.add(
            ids=["a:0", "a:1", "b:0"],
            documents=["Alpha text", "More alpha", "Beta text"],
            metadatas=[{"source": "a.pdf"}, {"source": "a.pdf"}, {"source": "b.pdf"}],
            embeddings=[[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]],
        )
        self.collection_patch = patch.object(rag, "_collection", return_value=self.collection)
        self.collection_patch.start()
        self.addCleanup(self.collection_patch.stop)
        self.addCleanup(self.client.delete_collection, "selection-test")
        self.embed_patch = patch.object(rag, "_embed", return_value=[[1.0, 0.0]])
        self.embed = self.embed_patch.start()
        self.addCleanup(self.embed_patch.stop)
        self.chat_patch = patch.object(rag.ollama, "chat", return_value={"message": {"content": "Answer"}})
        self.chat = self.chat_patch.start()
        self.addCleanup(self.chat_patch.stop)
        document_titles._generate.cache_clear()
        self.addCleanup(document_titles._generate.cache_clear)
        server.app.state.document_titles = {}
        server.app.state.failed_titles = set()
        self.addCleanup(setattr, server.app.state, "document_titles", {})
        self.addCleanup(setattr, server.app.state, "failed_titles", set())

    def test_each_server_startup_regenerates_titles_without_browser_calls(self):
        self.chat.return_value = {"message": {"content": '{"title": "Titolo pronto"}'}}
        for startup in range(2):
            with TestClient(server.app) as client:
                self.assertEqual(self.chat.call_count, (startup + 1) * 2)
                for _ in range(2):
                    response = client.get("/documents")
                    self.assertTrue(all(doc["title"] == "Titolo pronto" for doc in response.json()["documents"]))
                self.assertEqual(self.chat.call_count, (startup + 1) * 2)

    def test_startup_skips_readme_and_continues_if_generation_fails(self):
        documents = [{"source": "README.txt", "chunks": 1}, {"source": "a.pdf", "chunks": 2}]
        with patch.object(rag, "list_documents", return_value=documents), \
             patch.object(document_titles, "document_title", side_effect=RuntimeError("Model unavailable")) as generate, \
             patch.object(document_titles.logger, "warning"):
            with TestClient(server.app) as client:
                response = client.get("/documents")
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json()["documents"][1]["title_generation_failed"])
        generate.assert_called_once_with("a.pdf")

    def test_titles_use_chat_model_and_cache_without_changing_sources(self):
        self.chat.return_value = {"message": {"content": '{"title": "Documento Alpha"}'}}
        client = TestClient(server.app)
        for _ in range(2):
            response = client.post("/documents/title", json={"source": "a.pdf"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"source": "a.pdf", "title": "Documento Alpha"})
        self.chat.assert_called_once()
        self.assertEqual(self.chat.call_args.kwargs["model"], rag.CFG["models"]["llm"])
        self.assertIn("Alpha text", self.chat.call_args.kwargs["messages"][1]["content"])
        self.assertEqual(rag.list_documents()[0]["source"], "a.pdf")

    def test_titles_handle_missing_source_and_invalid_model_output(self):
        client = TestClient(server.app)
        self.assertEqual(client.post("/documents/title", json={"source": "missing.pdf"}).status_code, 404)
        self.chat.assert_not_called()
        self.chat.return_value = {"message": {"content": '{"title": ""}'}}
        self.assertEqual(client.post("/documents/title", json={"source": "a.pdf"}).status_code, 503)

    def test_title_cache_changes_with_model_and_content(self):
        self.chat.return_value = {"message": {"content": '{"title": "Titolo"}'}}
        document_titles._generate("a.pdf", "model-a", "original")
        document_titles._generate("a.pdf", "model-b", "original")
        document_titles._generate("a.pdf", "model-b", "updated")
        self.assertEqual(self.chat.call_count, 3)

    def test_document_inventory_counts_indexed_chunks(self):
        self.assertEqual(rag.list_documents(), [
            {"source": "a.pdf", "chunks": 2},
            {"source": "b.pdf", "chunks": 1},
        ])

    def test_filter_excludes_more_similar_unselected_document(self):
        result = rag.ask("Question", sources=["b.pdf"], k=10)
        self.assertEqual(result["sources"], ["b.pdf"])
        self.assertEqual([c["text"] for c in result["chunks"]], ["Beta text"])
        self.assertNotIn("Alpha text", result["prompt"])

    def test_omitted_selection_keeps_full_index_and_multiple_selection_works(self):
        self.assertEqual(rag.ask("Question")["sources"], ["a.pdf", "b.pdf"])
        self.assertEqual(rag.ask("Question", sources=["a.pdf", "b.pdf"])["sources"], ["a.pdf", "b.pdf"])

    def test_empty_and_stale_selections_never_call_model(self):
        for selection in ([], ["missing.pdf"], ["a.pdf", "missing.pdf"]):
            with self.assertRaises(ValueError):
                rag.ask("Question", sources=selection)
        self.chat.assert_not_called()
        self.embed.assert_not_called()

    def test_document_endpoint_and_chat_selection(self):
        from threadleaf.chat_workflow import ChatWorkflow
        workflow = ChatWorkflow(":memory:")
        self.addCleanup(workflow.close)
        workflow_patch = patch.object(server, "get_workflow", return_value=workflow)
        workflow_patch.start()
        self.addCleanup(workflow_patch.stop)
        client = TestClient(server.app)
        response = client.get("/documents")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["documents"], rag.list_documents())
        response = client.post("/chat", json={"message": "Question", "sources": ["b.pdf"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sources"], ["b.pdf"])
        self.assertEqual(client.post("/chat", json={"message": "Question", "sources": []}).status_code, 400)

    def test_inventory_reads_all_metadata_batches(self):
        collection = MagicMock()
        collection.get.side_effect = [
            {"ids": [str(i) for i in range(1000)], "metadatas": [{"source": "a.pdf"}] * 1000},
            {"ids": ["last"], "metadatas": [{"source": "b.pdf"}]},
        ]
        with patch.object(rag, "_collection", return_value=collection):
            self.assertEqual(rag.list_documents(), [
                {"source": "a.pdf", "chunks": 1000}, {"source": "b.pdf", "chunks": 1},
            ])
        self.assertEqual(collection.get.call_args.kwargs["offset"], 1000)


if __name__ == "__main__":
    unittest.main()
