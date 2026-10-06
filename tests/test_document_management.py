import unittest
import uuid
from unittest.mock import patch

import chromadb
from fastapi.testclient import TestClient

from threadleaf import document_management, rag
import server
from tests.helpers import temporary_directory


class DocumentManagementTests(unittest.TestCase):
    def setUp(self):
        self.root = self.enterContext(temporary_directory())
        self.config = {**rag.CFG, "rag": {**rag.CFG["rag"], "docs_dir": str(self.root)}}
        config_patch = patch.object(rag, "CFG", self.config)
        config_patch.start()
        self.addCleanup(config_patch.stop)
        client = chromadb.EphemeralClient()
        name = "management-" + uuid.uuid4().hex
        self.collection = client.create_collection(name, embedding_function=None)
        self.addCleanup(client.delete_collection, name)
        collection_patch = patch.object(rag, "_collection", return_value=self.collection)
        collection_patch.start()
        self.addCleanup(collection_patch.stop)
        embed_patch = patch.object(rag, "_embed", side_effect=lambda texts: [[1.0, 0.0] for _ in texts])
        self.embed = embed_patch.start()
        self.addCleanup(embed_patch.stop)
        titles_patch = patch.object(server.document_titles, "document_title", return_value="Generated title")
        titles_patch.start()
        self.addCleanup(titles_patch.stop)
        state_patch = patch.object(server.app.state, "document_jobs", document_management.DocumentJobs())
        state_patch.start()
        self.addCleanup(state_patch.stop)
        self.jobs = server.app.state.document_jobs
        self.addCleanup(self.jobs.wait)
        server.app.state.document_titles = {}
        server.app.state.failed_titles = set()
        self.addCleanup(setattr, server.app.state, "document_titles", {})
        self.addCleanup(setattr, server.app.state, "failed_titles", set())
        self.api = TestClient(server.app)

    def upload(self, source="folder/new.txt", content=b"New document text"):
        response = self.api.post("/documents/upload", params={"source": source}, content=content)
        self.assertEqual(response.status_code, 202, response.text)
        self.jobs.wait()
        return self.api.get("/documents/operations").json()

    def test_upload_indexes_in_folder_reports_progress_and_keeps_other_sources(self):
        self.collection.add(ids=["existing:0"], documents=["Existing"], metadatas=[{"source": "existing.txt"}], embeddings=[[0.0, 1.0]])
        job = self.upload()
        self.assertEqual(job["state"], "complete")
        self.assertEqual(job["done"], job["total"])
        self.assertGreater(job["total"], 0)
        self.assertTrue((self.root / "folder/new.txt").is_file())
        self.assertEqual(self.collection.count(), 2)
        self.assertIn("Generated title", str(self.api.get("/documents").json()))

    def test_delete_removes_only_requested_file_and_index(self):
        self.upload("a.txt")
        self.upload("b.txt")
        response = self.api.request("DELETE", "/documents", json={"source": "a.txt"})
        self.assertEqual(response.status_code, 202)
        self.jobs.wait()
        self.assertFalse((self.root / "a.txt").exists())
        self.assertTrue((self.root / "b.txt").exists())
        self.assertEqual(rag.list_documents(), [{"source": "b.txt", "chunks": 1}])

    def test_upload_rejects_traversal_overwrite_reserved_names_and_empty_files(self):
        for source in ("../outside.txt", "C:/outside.txt", "folder/../../outside.txt", "CON.txt", "unsupported.exe"):
            response = self.api.post("/documents/upload", params={"source": source}, content=b"text")
            self.assertEqual(response.status_code, 400, source)
        self.assertEqual(self.api.post("/documents/upload", params={"source": "README.txt"}, content=b"text").status_code, 400)
        self.assertEqual(self.api.post("/documents/upload", params={"source": "empty.txt"}, content=b"").status_code, 400)
        self.upload("a.txt")
        self.assertEqual(self.api.post("/documents/upload", params={"source": "a.txt"}, content=b"replacement").status_code, 409)
        self.assertEqual((self.root / "a.txt").read_bytes(), b"New document text")

    def test_failed_embedding_preserves_other_index_and_allows_retry(self):
        self.collection.add(ids=["existing:0"], documents=["Existing"], metadatas=[{"source": "existing.txt"}], embeddings=[[0.0, 1.0]])
        with patch.object(rag, "_embed", side_effect=RuntimeError("Embedding unavailable")), patch.object(document_management.logger, "exception"):
            self.assertEqual(self.upload()["state"], "failed")
        self.assertEqual(self.collection.count(), 1)
        response = self.api.post("/documents/reindex", json={"source": "folder/new.txt"})
        self.assertEqual(response.status_code, 202)
        self.jobs.wait()
        self.assertEqual(self.jobs.status()["state"], "complete")
        self.assertEqual(self.collection.count(), 2)

    def test_busy_job_blocks_mutations_and_chat(self):
        with self.jobs.lock:
            self.jobs.job["state"] = "running"
        self.assertEqual(self.api.post("/chat", json={"message": "Question"}).status_code, 409)
        self.assertEqual(self.api.post("/documents/upload", params={"source": "new.txt"}, content=b"text").status_code, 409)


if __name__ == "__main__":
    unittest.main()
