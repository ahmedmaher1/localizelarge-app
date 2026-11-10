"""The MQM Core typology (localizelarge/data/mqm_core.json).

The data is the MQM Council's (themqm.org), licensed CC BY 4.0; names and definitions
are as published. A category is written as a path: "accuracy/mistranslation" for a
subtype, "accuracy" for a whole dimension.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_FILE = Path(__file__).resolve().parent.parent / "data" / "mqm_core.json"


@dataclass(frozen=True)
class Category:
    path: str            # "accuracy/mistranslation" or "accuracy"
    name: str
    definition: str
    dimension: str       # the dimension's id
    dimension_name: str

    @property
    def label(self) -> str:
        """"Accuracy › Mistranslation", or "Accuracy" for a dimension."""
        return self.dimension_name if "/" not in self.path else f"{self.dimension_name} › {self.name}"


@lru_cache(maxsize=1)
def load() -> dict:
    return json.loads(_FILE.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def categories() -> Tuple[Category, ...]:
    """Every dimension, each followed by its subtypes, in the typology's order."""
    out: List[Category] = []
    for dim in load()["dimensions"]:
        out.append(Category(dim["id"], dim["name"], dim["definition"], dim["id"], dim["name"]))
        for sub in dim["subtypes"]:
            name = sub["name"][:1].upper() + sub["name"][1:]
            out.append(Category(f'{dim["id"]}/{sub["id"]}', name, sub["definition"], dim["id"], dim["name"]))
    return tuple(out)


@lru_cache(maxsize=1)
def _by_path() -> Dict[str, Category]:
    return {c.path: c for c in categories()}


def get(path: str) -> Optional[Category]:
    return _by_path().get(path or "")


def label(path: str) -> str:
    """A readable name for a category path; the path itself when it is not in MQM Core
    (a pack may define its own categories)."""
    found = get(path)
    return found.label if found else (path or "")


def dimension_of(path: str) -> str:
    return (path or "").split("/")[0]


def attribution() -> str:
    return load()["attribution"]
