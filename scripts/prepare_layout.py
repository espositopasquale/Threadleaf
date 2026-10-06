
import tomllib

from huggingface_hub import snapshot_download

from threadleaf.document_layout import model_directory
from threadleaf.paths import ROOT


def main():
    config = tomllib.loads((ROOT / "config.toml").read_text(encoding="utf-8"))["layout"]
    folder = model_directory(config)
    snapshot_download(repo_id="PaddlePaddle/" + config["model"], revision=config.get("revision", "main"),
                      allow_patterns=["inference.json", "inference.pdiparams", "inference.yml", "config.json"],
                      local_dir=folder, max_workers=2)
    print(f"Layout model downloaded to {folder}")
    print("Install requirements-layout.txt, then run python ingest.py to rebuild the index.")


if __name__ == "__main__":
    main()
