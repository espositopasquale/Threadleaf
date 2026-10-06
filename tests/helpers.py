import shutil
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4


@contextmanager
def temporary_directory():
    root = Path(__file__).resolve().parent / ".tmp"
    root.mkdir(exist_ok=True)
    folder = root / uuid4().hex
    # Default permissions also work inside restricted Windows workspaces.
    folder.mkdir()
    try:
        yield folder
    finally:
        if folder.resolve().parent != root.resolve():
            raise ValueError("Test directory outside test workspace")
        shutil.rmtree(folder)
        if not any(root.iterdir()):
            root.rmdir()
