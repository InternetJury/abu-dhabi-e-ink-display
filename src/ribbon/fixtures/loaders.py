from __future__ import annotations

import json
from pathlib import Path

from ribbon.models.snapshot import RibbonSnapshot


DATA_DIR = Path(__file__).resolve().parent / "data"


def list_fixture_names() -> list[str]:
    return sorted(path.stem for path in DATA_DIR.glob("*.json"))


def load_fixture_document(name: str) -> dict:
    path = DATA_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Unknown fixture: {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_fixture_snapshot(name: str) -> RibbonSnapshot:
    document = load_fixture_document(name)
    return RibbonSnapshot.model_validate(document["snapshot"])
