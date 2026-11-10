"""The quality data of a project: its issues and its quality profile.

In the project file this is ``"quality": {"issues": [...], "profile": {...}}``. In memory
a ``ProjectQuality`` object hangs on the project; ``quality_of(project)`` gives it.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .model import IssueList
from .profile import QualityProfile

_ATTRIBUTE = "_ll_quality"


class ProjectQuality:
    def __init__(self, issues: Optional[IssueList] = None, profile: Optional[QualityProfile] = None):
        self.issues = issues or IssueList()
        self.profile = profile or QualityProfile()

    def to_dict(self) -> Dict[str, Any]:
        return {"issues": self.issues.to_list(), "profile": self.profile.to_dict()}

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ProjectQuality":
        data = data if isinstance(data, dict) else {}
        return cls(IssueList.from_list(data.get("issues")), QualityProfile.from_dict(data.get("profile")))


def quality_of(project) -> ProjectQuality:
    """The quality data of a project, read from what was loaded the first time."""
    quality = getattr(project, _ATTRIBUTE, None)
    if quality is None:
        quality = ProjectQuality.from_dict(getattr(project, "quality", None))
        setattr(project, _ATTRIBUTE, quality)
    return quality


def to_saved(project) -> Optional[Dict[str, Any]]:
    """What goes into the project file, or None when there is nothing to save."""
    quality = getattr(project, _ATTRIBUTE, None)
    if quality is None:
        saved = getattr(project, "quality", None)
        return saved if isinstance(saved, dict) and saved else None
    if not len(quality.issues) and quality.profile.is_default():
        return None
    return quality.to_dict()
