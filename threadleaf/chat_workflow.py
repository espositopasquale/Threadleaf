import sqlite3
import threading
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.sqlite import SqliteSaver

from . import rag


class ChatState(TypedDict, total=False):
    question: str
    language: str | None
    model: str | None
    selected_sources: list[str] | None
    messages: list[dict]
    response: dict


class ChatWorkflow:
    def __init__(self, database: str | Path):
        if str(database) != ":memory:":
            Path(database).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(database), check_same_thread=False)
        self.lock = threading.RLock()
        saver = SqliteSaver(self.connection)
        self.saver = saver
        builder = StateGraph(ChatState)
        builder.add_node("answer", self._answer)
        builder.add_edge(START, "answer")
        builder.add_edge("answer", END)
        self.graph = builder.compile(checkpointer=saver)

    @staticmethod
    def _answer(state: ChatState) -> dict:
        messages = state.get("messages", [])
        history = [{"role": m["role"], "content": m["content"][:2000]} for m in messages[-6:]]
        result = rag.ask(state["question"], state.get("language"),
                         sources=state.get("selected_sources"), history=history, model=state.get("model"))
        response = {key: result[key] for key in (
            "reply", "sources", "answer_kind", "reranker_applied", "retrieval_question"
        ) if key in result}
        return {"response": response, "messages": messages + [
            {"role": "user", "content": state["question"]},
            {"role": "assistant", "content": result["reply"], "sources": result.get("sources", []),
             "answer_kind": result.get("answer_kind")},
        ]}

    def ask(self, thread_id: str, question: str, language: str | None, sources: list[str] | None, model: str | None = None) -> dict:
        with self.lock:
            state = self.graph.invoke({"question": question, "language": language,
                                       "selected_sources": sources, "model": model},
                                      {"configurable": {"thread_id": thread_id}})
            return {**state["response"], "thread_id": thread_id}

    def read(self, thread_id: str) -> dict:
        with self.lock:
            state = self.graph.get_state({"configurable": {"thread_id": thread_id}}).values
            return {"thread_id": thread_id, "messages": state.get("messages", []),
                    "sources": state.get("selected_sources")}

    def list_conversations(self, query: str = "") -> list[dict]:
        query = query.strip().casefold()
        with self.lock:
            seen = set()
            conversations = []
            for saved in self.saver.list(None):
                thread_id = saved.config["configurable"]["thread_id"]
                if thread_id in seen:
                    continue
                seen.add(thread_id)
                messages = saved.checkpoint.get("channel_values", {}).get("messages", [])
                if not messages:
                    continue
                match = next((m["content"] for m in messages if query in m["content"].casefold()), None)
                if query and match is None:
                    continue
                title = next((m["content"] for m in messages if m["role"] == "user"), "")
                conversations.append({"thread_id": thread_id, "title": title[:100],
                                      "updated_at": saved.checkpoint["ts"], "message_count": len(messages)})
            return sorted(conversations, key=lambda item: item["updated_at"], reverse=True)

    def delete(self, thread_id: str) -> None:
       
        with self.lock:
            self.saver.delete_thread(thread_id)

    def close(self):
        with self.lock:
            self.connection.close()
