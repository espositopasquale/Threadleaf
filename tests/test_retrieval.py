import unittest
import uuid
from unittest.mock import patch

import chromadb
from threadleaf import retrieval


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.client = chromadb.EphemeralClient()
        self.name = "retrieval-" + uuid.uuid4().hex
        self.col = self.client.create_collection(self.name, embedding_function=None)
        self.addCleanup(self.client.delete_collection, self.name)
        retrieval.invalidate()
        self.addCleanup(retrieval.invalidate)
        self.col.add(ids=["a:0", "b:0"], documents=["General document unrelated to astronomy", "A quasar emits radiation"],
                     metadatas=[{"source": "a.txt"}, {"source": "b.txt"}], embeddings=[[1.0, 0.0], [0.0, 1.0]])

    def test_keyword_evidence_recovers_semantically_missed_passage(self):
        result = retrieval.retrieve(self.col, "quasar", [1.0, 0.0], 1, 2, candidates=1)
        self.assertEqual(result[0]["source"], "b.txt")
        self.assertIsNone(result[0]["distance"])

    def test_keyword_candidates_respect_selected_sources(self):
        result = retrieval.retrieve(self.col, "quasar", [1.0, 0.0], 2, 1, {"source": {"$in": ["a.txt"]}})
        self.assertEqual([chunk["source"] for chunk in result], ["a.txt"])

    def test_no_keyword_matches_keeps_semantic_ranking(self):
        result = retrieval.retrieve(self.col, "unmatched", [1.0, 0.0], 2, 2)
        self.assertEqual([chunk["source"] for chunk in result], ["a.txt", "b.txt"])

    def test_cache_invalidation_refreshes_same_count_replacements(self):
        retrieval.retrieve(self.col, "quasar", [1.0, 0.0], 1, 2)
        self.col.update(ids=["b:0"], documents=["An updated pulsar document"], embeddings=[[0.0, 1.0]])
        retrieval.invalidate()
        result = retrieval.retrieve(self.col, "pulsar", [1.0, 0.0], 1, 2, candidates=1)
        self.assertIn("pulsar", result[0]["text"])

    def test_accents_case_and_punctuation_match(self):
        self.assertEqual(retrieval.tokens("CAPACITÀ, giuridica!"), retrieval.tokens("capacita giuridica"))

    def test_generic_section_heading_boosts_definition_over_incidental_mentions(self):
        self.col.update(ids=["a:0", "b:0"], documents=["Radiation is emitted by a quasar, a distant quasar", "(Quasar).\nA quasar is a luminous astronomical object."], embeddings=[[1.0, 0.0], [0.0, 1.0]])
        result = retrieval.retrieve(self.col, "Define quasar", [1.0, 0.0], 1, 2)
        self.assertEqual(result[0]["source"], "b.txt")

    def test_words_that_can_be_names_are_not_removed_from_search(self):
        self.col.update(ids=["b:0"], documents=["The The is a band formed in London."], embeddings=[[0.0, 1.0]])
        result = retrieval.retrieve(self.col, "The The", [1.0, 0.0], 1, 2, candidates=1)
        self.assertEqual(result[0]["source"], "b.txt")


if __name__ == "__main__":
    unittest.main()
