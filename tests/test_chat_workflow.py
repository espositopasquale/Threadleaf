import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from threadleaf.chat_workflow import ChatWorkflow
from tests.helpers import temporary_directory


class WorkflowTests(unittest.TestCase):
    def test_deletion_removes_all_saved_state_and_preserves_other_threads(self):
        with temporary_directory() as folder:
            database = Path(folder) / "chat.sqlite3"
            thread, other = str(uuid4()), str(uuid4())
            workflow = ChatWorkflow(database)
            with patch("threadleaf.rag.ask", return_value={"reply": "Answer", "sources": []}):
                workflow.ask(thread, "First question", None, None)
                workflow.ask(thread, "Follow-up", None, None)
                workflow.ask(other, "Keep this conversation", None, None)
            workflow.delete(thread)
            for table in ("checkpoints", "writes"):
                remaining = workflow.connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE thread_id = ?", (thread,)
                ).fetchone()[0]
                self.assertEqual(remaining, 0)
            workflow.close()
            workflow = ChatWorkflow(database)
            try:
                self.assertEqual(workflow.read(thread)["messages"], [])
                self.assertEqual([item["thread_id"] for item in workflow.list_conversations()], [other])
                self.assertEqual(len(workflow.read(other)["messages"]), 2)
                workflow.delete(thread)  # Repeated deletion is harmless.
            finally:
                workflow.close()

    def test_model_selection_applies_to_each_turn(self):
        workflow = ChatWorkflow(":memory:")
        thread = str(uuid4())
        try:
            with patch("threadleaf.rag.ask", return_value={"reply": "Answer", "sources": []}) as ask:
                workflow.ask(thread, "Hello", None, None, "small:1b")
                self.assertEqual(ask.call_args.kwargs["model"], "small:1b")
                workflow.ask(thread, "Hello again", None, None, "other:2b")
                self.assertEqual(ask.call_args.kwargs["model"], "other:2b")
                workflow.ask(thread, "Use default", None, None)
                self.assertIsNone(ask.call_args.kwargs["model"])
        finally:
            workflow.close()

    def test_restart_restores_history_and_isolates_threads(self):
        with temporary_directory() as folder:
            database = Path(folder) / "chat.sqlite3"
            thread = str(uuid4())
            workflow = ChatWorkflow(database)
            with patch("threadleaf.rag.ask", return_value={"reply": "Alex studies physics.", "sources": ["cv.pdf"], "answer_kind": "document"}):
                workflow.ask(thread, "Who is Alex?", "en", ["cv.pdf"])
            workflow.close()
            workflow = ChatWorkflow(database)
            try:
                saved = workflow.read(thread)
                self.assertEqual(len(saved["messages"]), 2)
                self.assertEqual(saved["sources"], ["cv.pdf"])
                self.assertEqual(saved["messages"][1]["sources"], ["cv.pdf"])
                self.assertEqual(saved["messages"][1]["answer_kind"], "document")
                self.assertEqual(workflow.list_conversations()[0]["title"], "Who is Alex?")
                with patch("threadleaf.rag.ask", return_value={"reply": "Physics", "sources": ["cv.pdf"]}) as ask:
                    workflow.ask(thread, "What did he study?", "en", ["cv.pdf"])
                    self.assertEqual(ask.call_args.kwargs["history"][0]["content"], "Who is Alex?")
                    workflow.ask(str(uuid4()), "Hello", "it", None)
                    self.assertEqual(ask.call_args.kwargs["history"], [])
                self.assertEqual(len(workflow.read(thread)["messages"]), 4)
                listed = workflow.list_conversations()
                self.assertEqual(len(listed), 2)
                self.assertEqual(listed[0]["title"], "Hello")
                self.assertEqual(listed[1]["message_count"], 4)
            finally:
                workflow.close()

    def test_failed_turn_is_not_added_and_context_is_bounded(self):
        workflow = ChatWorkflow(":memory:")
        thread = str(uuid4())
        try:
            with patch("threadleaf.rag.ask", return_value={"reply": "Answer", "sources": []}) as ask:
                for number in range(5):
                    workflow.ask(thread, f"Question {number}", None, None)
                self.assertEqual(len(ask.call_args.kwargs["history"]), 6)
            with patch("threadleaf.rag.ask", side_effect=ValueError("No documents")):
                with self.assertRaises(ValueError):
                    workflow.ask(thread, "Failed", None, [])
            self.assertEqual(len(workflow.read(thread)["messages"]), 10)
            self.assertEqual(len(workflow.list_conversations()), 1)
            with patch("threadleaf.rag.ask", return_value={"reply": "Recovered", "sources": []}):
                workflow.ask(thread, "Retry", None, None)
            self.assertEqual(len(workflow.read(thread)["messages"]), 12)
        finally:
            workflow.close()

    def test_empty_or_failed_threads_do_not_appear_in_history(self):
        workflow = ChatWorkflow(":memory:")
        try:
            self.assertEqual(workflow.list_conversations(), [])
            with patch("threadleaf.rag.ask", side_effect=ValueError("Failed")):
                with self.assertRaises(ValueError):
                    workflow.ask(str(uuid4()), "Failed", None, None)
            self.assertEqual(workflow.list_conversations(), [])
        finally:
            workflow.close()

    def test_search_matches_full_messages_case_insensitively(self):
        workflow = ChatWorkflow(":memory:")
        thread = str(uuid4())
        try:
            with patch("threadleaf.rag.ask", return_value={"reply": "A degree in linguistics", "sources": []}):
                workflow.ask(thread, "Who is Alex?", None, None)
            with patch("threadleaf.rag.ask", return_value={"reply": "Later answer", "sources": []}):
                workflow.ask(thread, "Tell me about university", None, None)
                workflow.ask(str(uuid4()), "Another topic", None, None)
            for query in (" ALEX ", "LINGUISTICS", "university"):
                results = workflow.list_conversations(query)
                self.assertEqual([item["thread_id"] for item in results], [thread])
            self.assertEqual(workflow.list_conversations("missing phrase"), [])
            self.assertEqual(len(workflow.list_conversations("  ")), 2)
        finally:
            workflow.close()


if __name__ == "__main__":
    unittest.main()
