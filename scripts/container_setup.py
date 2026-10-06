import os
import tomllib

import ollama

from threadleaf.paths import ROOT


def main():
    config = tomllib.loads((ROOT / "config.toml").read_text(encoding="utf-8"))
    installed = {item.model for item in ollama.list().models}
    for name in dict.fromkeys(config["models"].values()):
        canonical = name if ":" in name else name + ":latest"
        if canonical not in installed:
            print(f"Downloading Ollama model: {name}", flush=True)
            ollama.pull(name)
    if config.get("reranker", {}).get("enabled"):
        from scripts.prepare_reranker import main as prepare_reranker
        prepare_reranker()
    if os.environ.get("PREPARE_LAYOUT", "false").lower() == "true" and config.get("layout", {}).get("enabled"):
        from scripts.prepare_layout import main as prepare_layout
        prepare_layout()
    print("Models ready. Existing documents can be indexed with docker compose run --rm threadleaf python ingest.py")


if __name__ == "__main__":
    main()
