"""The ``.llproj`` project file.

A ``.llproj`` file is the Supervertaler project JSON plus two keys that name
the format. An older ``.svproj`` file is read as it is and saved as a
``.llproj`` beside it; the ``.svproj`` is left untouched.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from localizelarge.paths import LEGACY_PROJECT_EXTENSION, PROJECT_EXTENSION

FORMAT_NAME = "localizelarge-project"
FORMAT_VERSION = 1

FILE_DIALOG_FILTER_OPEN = (
    "Localize Large Projects (*.llproj *.svproj);;Legacy Projects (*.json);;All Files (*.*)"
)
FILE_DIALOG_FILTER_SAVE = "Localize Large Projects (*.llproj);;All Files (*.*)"


def stamp(project_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Return the project data with the format keys first."""
    stamped: Dict[str, Any] = {"format": FORMAT_NAME, "formatVersion": FORMAT_VERSION}
    for key, value in project_dict.items():
        if key not in stamped:
            stamped[key] = value
    return stamped


def is_legacy(path: str) -> bool:
    return Path(path).suffix.lower() == LEGACY_PROJECT_EXTENSION


def save_path_for(opened_path: str) -> str:
    """Where a project opened from ``opened_path`` is saved.

    ``name.svproj`` becomes ``name.llproj`` in the same folder. Any other path
    is returned unchanged.
    """
    if is_legacy(opened_path):
        return str(Path(opened_path).with_suffix(PROJECT_EXTENSION))
    return opened_path


def check_version(data: Dict[str, Any]) -> None:
    """Refuse a project written by a newer format than this app knows."""
    version = data.get("formatVersion")
    if data.get("format") == FORMAT_NAME and isinstance(version, int) and version > FORMAT_VERSION:
        raise ValueError(
            f"This project was saved by a newer version of Localize Large "
            f"(project format {version}; this version reads up to {FORMAT_VERSION})."
        )
