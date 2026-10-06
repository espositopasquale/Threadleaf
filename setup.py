import argparse
import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def set_model(config: str, key: str, value: str) -> str:
    
    section = re.search(r"(?ms)^\[models\][ \t]*\n(.*?)(?=^\[|\Z)", config)
    if section is None:
        raise ValueError("config.toml is missing its [models] section")
    body = section.group(1)
    replacement = f"{key} = {json.dumps(value, ensure_ascii=False)}"
    body, count = re.subn(rf"(?m)^{re.escape(key)}[ \t]*=.*$", lambda _: replacement, body)
    if count != 1:
        raise ValueError(f"Expected exactly one models.{key} entry in config.toml")
    return config[:section.start(1)] + body + config[section.end(1):]


def confirm(label: str, default: bool = False) -> bool:
    while True:
        answer = input(f"{label} {'[Y/n]' if default else '[y/N]'}: ").strip().lower()
        if not answer:
            return default
        if answer in {"y", "yes", "n", "no"}:
            return answer in {"y", "yes"}
        print("Enter yes or no.")


def model_name(value: str) -> str:
    value = value.strip()
    if not value or value.startswith("-") or any(c.isspace() for c in value):
        raise ValueError("Model names must be nonempty, contain no whitespace, and not start with '-'")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llm", help="Ollama chat model (default: current configuration)")
    parser.add_argument("--embedding", help="Ollama embedding model (default: current configuration)")
    parser.add_argument("--prompt-file", type=Path, help="UTF-8 file containing the new system prompt")
    parser.add_argument("--non-interactive", action="store_true", help="Use flags and current defaults without questions")
    parser.add_argument("--skip-pull", action="store_true", help="Save settings without downloading models")
    parser.add_argument("--ingest", action="store_true", help="Rebuild the document index after saving settings")
    args = parser.parse_args(argv)

    try:
        config_path = ROOT / "config.toml"
        prompt_path = ROOT / "system_prompt.txt"
        config = config_path.read_text(encoding="utf-8")
        cfg = tomllib.loads(config)
        old_models = cfg["models"]
        prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else (
            "You are a helpful assistant. Answer using only the provided context. "
            "If the context does not contain the answer, say you do not know.\n"
        )
        llm, embedding = args.llm, args.embedding
        if not args.non_interactive:
            print("RAG setup — press Enter to keep current settings.")
            if llm is None:
                llm = input(f"Chat model [{old_models['llm']}]: ").strip() or old_models["llm"]
            if embedding is None:
                embedding = input(f"Embedding model [{old_models['embedding']}]: ").strip() or old_models["embedding"]
        llm = model_name(llm if llm is not None else old_models["llm"])
        embedding = model_name(embedding if embedding is not None else old_models["embedding"])

        if args.prompt_file is not None:
            prompt = args.prompt_file.read_text(encoding="utf-8")
        elif not args.non_interactive:
            print(f"\nCurrent system prompt:\n{prompt.strip()}\n")
            if confirm("Replace the system prompt?"):
                print("Enter your prompt; finish with a line containing only END.")
                lines = []
                while (line := input()) != "END":
                    lines.append(line)
                prompt = "\n".join(lines) + "\n"
        if not prompt.strip():
            raise ValueError("The system prompt must not be empty")

        updated = set_model(set_model(config, "llm", llm), "embedding", embedding)
        tomllib.loads(updated)
        print(f"\nChat model: {llm}\nEmbedding model: {embedding}")
        changed_embedding = embedding != old_models["embedding"]
        if changed_embedding:
            print("Embedding model changed: rebuild the index before asking questions.")
        ingest = args.ingest
        if not args.non_interactive and not ingest:
            ingest = confirm("Rebuild the document index after setup?")

        # Download before saving so a failed pull keeps the previous settings.
        if not args.skip_pull:
            executable = shutil.which("ollama")
            if executable is None:
                raise ValueError("Ollama is not on PATH. Install it from https://ollama.com/download or use --skip-pull.")
            for model in dict.fromkeys((llm, embedding)):
                print(f"\nPulling {model}...", flush=True)
                subprocess.run([executable, "pull", model], check=True)

        docs_dir = ROOT / cfg["rag"]["docs_dir"]
        docs_dir.mkdir(parents=True, exist_ok=True)
        config_path.write_text(updated, encoding="utf-8")
        prompt_path.write_text(prompt, encoding="utf-8")
        print("Settings saved. Restart any running chat CLI or web server to load them.")
        if ingest:
            subprocess.run([sys.executable, str(ROOT / "ingest.py")], cwd=ROOT, check=True)
        else:
            print(f"Add PDF, TXT, or Markdown files to {docs_dir}, then run: python ingest.py")
        return 0
    except (EOFError, KeyboardInterrupt):
        print("\nSetup cancelled.", file=sys.stderr)
        return 130
    except subprocess.CalledProcessError as exc:
        print(f"Setup failed: command exited with status {exc.returncode}. Fix the error above and rerun setup.", file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError) as exc:
        print(f"Setup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
