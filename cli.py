import argparse
import sys
from itertools import cycle
import ollama
from contextlib import nullcontext

from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich.filesize import decimal

from threadleaf import rag

LOADING_PHRASES = cycle(("Untangling the thread…", "Weaving the threads…", "Following the thread…", "Stitching ideas together…"))


def main():
    # Keep redirected output readable in UTF-8 on Windows as well.
    if not sys.stdout.isatty() and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="ThreadLeaf — document chat")
    parser.add_argument("--model", default=rag.CFG["models"]["llm"], help="Ollama chat model")
    parser.add_argument("--k", type=int, default=rag.CFG["rag"]["top_k"], help="chunks to retrieve")
    parser.add_argument("--lang", default=rag.CFG["language"]["answer"], help="answer language or 'auto'")
    parser.add_argument("--list-models", action="store_true", help="list locally installed Ollama models and exit")
    parser.add_argument("--debug", action="store_true", help="show retrieved chunks and prompt")
    args = parser.parse_args()
    if args.k < 1:
        parser.error("--k must be positive")
    model, k, lang, debug = args.model, args.k, args.lang, args.debug
    console = Console(theme=Theme({"accent": "#90b89a", "muted": "#8993a4"}))
    last_sources = []

    def list_models():
        try:
            models = ollama.list().models
        except Exception as exc:
            console.print(Panel(Text("Could not list models. Start Ollama and try again.\n" + str(exc)), title="Error", border_style="red"))
            return False
        if not models:
            console.print(Text("No models installed. Run python setup.py or ollama pull MODEL.", style="muted"))
            return True
        table = Table(title="Installed Ollama models", expand=True)
        for heading in ("Model", "Size", "Parameters", "Quantization", "Configured use"):
            table.add_column(heading)
        for item in sorted(models, key=lambda item: item.model or ""):
            name = item.model or "Unnamed model"
            details = item.details
            uses = []
            # Ollama expands untagged names to the latest tag in its listing.
            if name == (model if ":" in model else model + ":latest"):
                uses.append("Chat")
            embedding = rag.CFG["models"]["embedding"]
            if name == (embedding if ":" in embedding else embedding + ":latest"):
                uses.append("Embedding")
            table.add_row(Text(name, overflow="fold"), decimal(item.size) if item.size is not None else "—",
                          details.parameter_size or "—" if details else "—",
                          details.quantization_level or "—" if details else "—",
                          ", ".join(uses) or "—")
        console.print(table)
        console.print(Text("Use /model NAME to select a chat model. Embedding models are for indexing.", style="muted"))
        console.print()
        return True

    def settings():
        table = Table.grid(padding=(0, 2))
        table.add_column(style="muted")
        table.add_column()
        for label, value in (("Model", model), ("Chunks", str(k)),
                             ("Answer language", lang), ("Debug", "on" if debug else "off")):
            table.add_row(Text(label), Text(value))
        console.print(Panel(table, title="Settings", border_style="muted", expand=False))

    def banner():
        console.print()
        console.print(Panel(Group(Text.assemble(("Thread", "bold #77618a"), ("Leaf", "bold accent")),
                                  Text("Your documents, in conversation.", style="muted")),
                            border_style="muted", padding=(1, 2), expand=False))
        settings()
        console.print(Text("Ask a question · /help for commands · exit to quit", style="muted"))
        console.print()

    def help_commands():
        table = Table(title="Commands", box=None, padding=(0, 2))
        table.add_column("Command", style="accent", no_wrap=True)
        table.add_column("Description")
        for command, description in [
            ("/models", "List installed Ollama models"),
            ("/sources", "Show sources for the latest reply"),
            ("/help", "Show commands"),
            ("/settings", "Show settings"),
            ("/k N", "Number of chunks (positive integer)"),
            ("/model NAME", "Change the Ollama model"),
            ("/lang NAME|auto", "Answer language"),
            ("/debug", "Toggle retrieval details"),
            ("/clear", "Clear the screen"),
            ("exit · quit", "Exit the chat"),
        ]:
            table.add_row(command, description)
        console.print(table)
        console.print()

    if args.list_models:
        if not list_models():
            raise SystemExit(1)
        return
    banner()
    while True:
        try:
            question = console.input("[bold accent]You ›[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if question.lower() in {"exit", "quit"}:
            break
        if not question:
            continue
        if question.startswith("/"):
            command, _, value = question[1:].partition(" ")
            value = value.strip()
            if command == "sources" and not value:
                if last_sources:
                    table = Table(title="Sources for the latest reply", box=None)
                    table.add_column("#", style="muted")
                    table.add_column("Document")
                    for index, source in enumerate(last_sources, 1):
                        table.add_row(str(index), Text(source))
                    console.print(table)
                else:
                    console.print(Text("The latest reply has no document sources.", style="muted"))
                continue
            if command == "models" and not value:
                list_models()
                continue
            if command == "help" and not value:
                help_commands()
                continue
            if command == "clear" and not value:
                console.clear()
                banner()
                continue
            if command == "k" and value.isdecimal() and int(value) > 0:
                k = int(value)
            elif command == "model" and value:
                model = value
            elif command == "lang" and value:
                lang = value
            elif command == "debug" and not value:
                debug = not debug
            elif command != "settings" or value:
                console.print(Text("Invalid command. Use /help.", style="bold red"))
                continue
            settings()
            console.print()
            continue
        try:
            last_sources = []
            activity = console.status(next(LOADING_PHRASES), spinner="dots", spinner_style="accent") if console.is_terminal else nullcontext()
            with activity:
                output = rag.ask(question, lang=lang, k=k, model=model)
        except KeyboardInterrupt:
            console.print(Text("Request interrupted.", style="muted"))
            continue
        except Exception as exc:
            console.print(Panel(Text(str(exc)), title="Error", border_style="red"))
            continue
        console.print()
        console.print(Panel(Markdown(output["reply"]), title="ThreadLeaf", title_align="left", border_style="accent", padding=(1, 2)))
        last_sources = [] if output.get("answer_kind") in {"casual", "insufficient"} else list(dict.fromkeys(output.get("sources", [])))
        if last_sources:
            count = len(last_sources)
            console.print(Text(f"[{count} {'source' if count == 1 else 'sources'} · /sources]", style="muted"))
        if debug:
            table = Table(title="Debug", expand=True)
            for name in ("#", "Source", "Distance", "Passage"):
                table.add_column(name)
            for index, chunk in enumerate(output.get("chunks", []), 1):
                distance = chunk.get("distance")
                table.add_row(str(index), Text(chunk["source"]), f"{distance:.3f}" if distance is not None else "—", Text(chunk["text"]))
            console.print(table)
            console.print(Panel(Text(output.get("prompt", "")), title="Prompt", border_style="muted"))
        console.print()
    console.print(Text("\n" + "See you soon!", style="muted"))


if __name__ == "__main__":
    main()
