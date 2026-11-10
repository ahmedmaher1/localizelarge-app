"""The quality profile: which checks run, how severe their findings are, and how the
score is calculated. A project has one profile; a quality pack (Phase 6) supplies one."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from localizelarge.mqm.scoring import ScoringProfile

DEFAULT_NAME = "Default profile"


@dataclass
class QualityProfile:
    name: str = DEFAULT_NAME
    version: str = "1"
    source: str = "built-in"                 # "built-in", or the pack it came from
    scoring: ScoringProfile = field(default_factory=ScoringProfile)
    checks: Dict[str, Dict[str, Any]] = field(default_factory=dict)   # rule id → settings
    categories: Optional[list] = None        # category paths offered when annotating; None = all of MQM Core

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "version": self.version, "source": self.source,
                "scoring": self.scoring.to_dict(), "checks": self.checks,
                "categories": self.categories}

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "QualityProfile":
        data = data if isinstance(data, dict) else {}
        try:
            scoring = ScoringProfile.from_dict(data.get("scoring"))
        except (TypeError, ValueError):
            scoring = ScoringProfile()
        checks = data.get("checks") if isinstance(data.get("checks"), dict) else {}
        categories = data.get("categories") if isinstance(data.get("categories"), list) else None
        return cls(name=str(data.get("name") or DEFAULT_NAME), version=str(data.get("version") or "1"),
                   source=str(data.get("source") or "built-in"), scoring=scoring,
                   checks={str(k): dict(v) for k, v in checks.items() if isinstance(v, dict)},
                   categories=categories)

    def is_default(self) -> bool:
        return self.to_dict() == QualityProfile().to_dict()
