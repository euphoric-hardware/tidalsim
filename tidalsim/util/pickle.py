from pathlib import Path
from typing import Any
import pickle


def dump(obj: Any, file: Path) -> None:
    with file.open("wb") as f:
        pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)


def load(file: Path) -> Any:
    with file.open("rb") as f:
        return pickle.load(f)
