import tomllib
from huggingface_hub import snapshot_download
from threadleaf import coreference
from threadleaf.paths import ROOT


def main():
    config = tomllib.loads((ROOT / "config.toml").read_text(encoding="utf-8"))["coreference"]
    folder = coreference.model_directory(config)
    snapshot_download(repo_id=config["model"], revision=config["revision"], local_dir=folder,
                      allow_patterns=["config.json", "tokenizer.json", "model.onnx"], max_workers=2)
    with coreference._lock:
        coreference._load.cache_clear()
        coreference._load(config["model"], config["revision"], config.get("threads", 2))
    print(f"Coreference model ready: {folder}")


if __name__ == "__main__":
    main()
