"""What every QA check shares."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from ..model import Issue, make_issue, plain_text


@dataclass
class Context:
    """What a check may know besides the segment in front of it."""
    source_lang: str = ""
    target_lang: str = ""
    segments: Sequence[Any] = ()                     # every segment of the project
    settings: Dict[str, Dict[str, Any]] = field(default_factory=dict)   # rule id → overrides
    spell_check: Optional[Callable[[str], bool]] = None   # word → is it spelled right
    regex_checks: Sequence[Any] = ()                 # saved find-only operations
    extract_tags: Optional[Callable[[str], List[str]]] = None

    def setting(self, rule_id: str, name: str, default: Any) -> Any:
        return self.settings.get(rule_id, {}).get(name, default)

    def base_lang(self, which: str) -> str:
        code = self.target_lang if which == "target" else self.source_lang
        return (code or "").replace("_", "-").split("-")[0].lower()


class Check:
    """A QA check. Subclasses set the class attributes and write ``run`` (one segment)
    or ``run_project`` (all segments at once)."""
    id = ""
    name = ""
    severity = "minor"
    category = ""            # MQM category path
    project_wide = False     # True: needs every segment, runs only on "Run QA"
    params: Dict[str, Any] = {}

    def enabled(self, ctx: Context) -> bool:
        return bool(ctx.setting(self.id, "enabled", True))

    def param(self, ctx: Context, name: str) -> Any:
        return ctx.setting(self.id, name, self.params[name])

    def issue(self, segment, ctx: Context, message: str, *, side: str = "target",
              start: Optional[int] = None, end: Optional[int] = None,
              suggestion: Optional[str] = None) -> Issue:
        return make_issue(
            segment, origin="qa", rule_id=self.id,
            category=ctx.setting(self.id, "category", self.category),
            severity=ctx.setting(self.id, "severity", self.severity),
            message=message, side=side, start=start, end=end, suggestion=suggestion)

    def run(self, segment, ctx: Context) -> List[Issue]:
        return []

    def run_project(self, segments: Sequence[Any], ctx: Context) -> List[Issue]:
        return []


def source_of(segment) -> str:
    return plain_text(getattr(segment, "source", "") or "")


def target_of(segment) -> str:
    return plain_text(getattr(segment, "target", "") or "")


def is_translated(segment) -> bool:
    return bool((getattr(segment, "target", "") or "").strip())


_SPACE = re.compile(r"\s+")


def squash(text: str) -> str:
    """NFC, white space collapsed and trimmed: for comparing two texts."""
    return _SPACE.sub(" ", unicodedata.normalize("NFC", text or "")).strip()


_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def western_digits(text: str) -> str:
    """Arabic-Indic (٠–٩) and Persian (۰–۹) digits as 0–9. Same length as the input."""
    return (text or "").translate(_DIGITS)
