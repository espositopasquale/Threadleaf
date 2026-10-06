import tomllib

from huggingface_hub import snapshot_download
from threadleaf import reranker
from threadleaf.paths import ROOT


def main():
    config = tomllib.loads((ROOT / "config.toml").read_text(encoding="utf-8"))["reranker"]
    folder = reranker.model_directory(config)
    snapshot_download(repo_id=config["model"], revision=config.get("revision", "main"),
                      allow_patterns=["tokenizer.json", config["file"]], local_dir=folder,
                      max_workers=2)
    # Verify both artifacts are usable, without calling the conversational model.
    with reranker._lock:
        reranker._load(config["model"], config.get("revision", "main"), config["file"], config.get("max_length", 384), config.get("threads", 2))
    print(f"Reranker ready: {folder}")


if __name__ == "__main__":
    main()
