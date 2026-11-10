"""The file formats the app can import through the Okapi sidecar.

The table lives in one file, ``okapi-sidecar/src/main/resources/formats.json``. The
sidecar reads it from its JAR; this module reads the same file, from the source tree
when the app runs from source and from the JAR in a built app.
"""
from __future__ import annotations

import json
import os
import sys
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Tuple

_TABLE_NAME = "formats.json"


@dataclass(frozen=True)
class Format:
    extensions: Tuple[str, ...]
    config_id: str
    description: str
    importable: bool

    @property
    def pattern(self) -> str:
        """The file-dialog pattern, for example ``*.html *.htm``."""
        return " ".join(f"*{ext}" for ext in self.extensions)


def _source_table() -> Path:
    return (Path(__file__).resolve().parent.parent / "okapi-sidecar" / "src" / "main"
            / "resources" / _TABLE_NAME)


def _jar_candidates() -> List[Path]:
    candidates = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "okapi-sidecar" / "okapi-sidecar.jar")
        candidates.append(Path(sys.executable).parent / "_internal" / "okapi-sidecar" / "okapi-sidecar.jar")
    root = Path(__file__).resolve().parent.parent
    candidates.append(root / "okapi-sidecar" / "dist" / "okapi-sidecar.jar")
    candidates.append(root / "okapi-sidecar" / "okapi-sidecar.jar")
    return candidates


def _read_table() -> dict:
    source = _source_table()
    if source.is_file():
        return json.loads(source.read_text(encoding="utf-8"))
    for jar in _jar_candidates():
        if jar.is_file():
            with zipfile.ZipFile(jar) as archive:
                return json.loads(archive.read(_TABLE_NAME).decode("utf-8"))
    raise FileNotFoundError(f"{_TABLE_NAME} was not found in the source tree or in the sidecar JAR")


@lru_cache(maxsize=1)
def all_formats() -> Tuple[Format, ...]:
    """Every row of the table, in table order."""
    rows = []
    for row in _read_table()["formats"]:
        rows.append(Format(
            extensions=tuple(ext.lower() for ext in row["extensions"]),
            config_id=row["configId"],
            description=row.get("description") or row["configId"],
            importable=bool(row.get("import", True)),
        ))
    return tuple(rows)


def import_formats() -> Tuple[Format, ...]:
    """The formats offered in the import dialog (everything except TMX)."""
    return tuple(f for f in all_formats() if f.importable)


def import_extensions() -> frozenset:
    """The extensions (lower case, with the dot) of the importable formats."""
    return frozenset(ext for f in import_formats() for ext in f.extensions)


def format_for(path: str) -> Optional[Format]:
    """The table row for a file name, or None when its extension is not in the table."""
    ext = os.path.splitext(str(path))[1].lower()
    for row in all_formats():
        if ext in row.extensions:
            return row
    return None


def dialog_filters() -> List[Tuple[str, str]]:
    """(name, pattern) pairs for the import file dialog, in table order."""
    return [(f.description, f.pattern) for f in import_formats()]
