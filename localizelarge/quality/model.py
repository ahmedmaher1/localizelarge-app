"""The issue: one record for everything that says "something may be wrong here".

QA checks, glossary checks, a person annotating with MQM, and AI pre-annotation all
produce the same ``Issue``. Issues are saved in the project file under
``"quality": {"issues": [...], "profile": ...}``.

Offsets (``start``/``end``) count characters of the *plain text* of the segment side:
the text with inline tags removed. ``text_hash`` is the SHA-1 of that plain text when
the issue was made. If the text changes, the hash no longer matches and the issue is
shown as "needs check"; a span is never moved silently.
"""
from __future__ import annotations

import getpass
import hashlib
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

ORIGINS = ("qa", "glossary", "human", "ai")
SEVERITIES = ("neutral", "minor", "major", "critical")
SIDES = ("source", "target")
STATUSES = ("open", "accepted", "rejected", "fixed")

# An inline tag as it is stored in a segment: <b>, </g1>, <x1/>, <bmk id="0">. "{0}" is
# a placeholder of the text, not a tag ("a < b" is neither: no space follows "<" in a tag).
_TAG = re.compile(r"<[^<>\s][^<>\n]{0,200}>")


def plain_text(text: Optional[str]) -> str:
    """The text of a segment side with inline tags removed. Offsets count in this."""
    return _TAG.sub("", text or "")


def text_hash(text: Optional[str]) -> str:
    """SHA-1 of the plain text of a segment side."""
    return hashlib.sha1(plain_text(text).encode("utf-8")).hexdigest()


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def current_author() -> str:
    """The name of the person at the keyboard (the Windows user name)."""
    try:
        return getpass.getuser() or "unknown"
    except Exception:
        return "unknown"


@dataclass
class Issue:
    segment_id: int
    origin: str                     # "qa" | "glossary" | "human" | "ai"
    rule_id: str                    # e.g. "qa.numbers", "glossary.required", "mqm"
    category: str                   # MQM category path, e.g. "accuracy/mistranslation"
    severity: str                   # "neutral" | "minor" | "major" | "critical"
    side: str = "target"            # "source" | "target"
    start: Optional[int] = None     # offsets in the plain text (tags removed)
    end: Optional[int] = None
    text_hash: str = ""             # sha1 of the plain text when created
    message: str = ""
    suggestion: Optional[str] = None
    comment: Optional[str] = None
    status: str = "open"            # "open" | "accepted" | "rejected" | "fixed"
    author: str = ""                # user name, or "AI: {provider}/{model}"
    created_at: str = ""            # ISO 8601 UTC
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self):
        if self.origin not in ORIGINS:
            raise ValueError(f"unknown origin: {self.origin!r}")
        if self.severity not in SEVERITIES:
            raise ValueError(f"unknown severity: {self.severity!r}")
        if self.side not in SIDES:
            raise ValueError(f"unknown side: {self.side!r}")
        if self.status not in STATUSES:
            raise ValueError(f"unknown status: {self.status!r}")
        if (self.start is None) != (self.end is None):
            raise ValueError("start and end must both be set or both be empty")
        if self.start is not None and not (0 <= self.start <= self.end):
            raise ValueError("start and end must satisfy 0 <= start <= end")
        if not self.created_at:
            self.created_at = now_utc()
        if not self.author:
            self.author = current_author()

    # ── saving ─────────────────────────────────────────────────────
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        # "id" first, as in the documented schema.
        return {"id": data.pop("id"), **data}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Issue":
        known = {name for name in cls.__dataclass_fields__}
        return cls(**{key: value for key, value in data.items() if key in known})

    # ── the span ───────────────────────────────────────────────────
    def is_stale(self, side_text: Optional[str]) -> bool:
        """True when the segment text changed since the issue was made ("needs check")."""
        return bool(self.text_hash) and self.text_hash != text_hash(side_text)

    def quoted(self, side_text: Optional[str]) -> str:
        """The text the issue points at, or "" for a whole-segment or stale issue."""
        if self.start is None or self.is_stale(side_text):
            return ""
        return plain_text(side_text)[self.start:self.end]

    def key(self) -> tuple:
        """What makes an automatic finding "the same finding" from one run to the next."""
        return (self.segment_id, self.rule_id, self.side, self.start, self.end, self.message)


def make_issue(segment, *, origin: str, rule_id: str, category: str, severity: str,
               message: str, side: str = "target", start: Optional[int] = None,
               end: Optional[int] = None, suggestion: Optional[str] = None,
               comment: Optional[str] = None, author: str = "", status: str = "open") -> Issue:
    """An issue on a segment, with the hash of the side's current text."""
    side_text = segment.source if side == "source" else segment.target
    return Issue(segment_id=int(segment.id), origin=origin, rule_id=rule_id, category=category,
                 severity=severity, side=side, start=start, end=end,
                 text_hash=text_hash(side_text), message=message, suggestion=suggestion,
                 comment=comment, author=author, status=status)


class IssueList:
    """The issues of a project."""

    def __init__(self, issues: Optional[Iterable[Issue]] = None):
        self._issues: List[Issue] = list(issues or [])

    def __iter__(self):
        return iter(self._issues)

    def __len__(self):
        return len(self._issues)

    def all(self) -> List[Issue]:
        return list(self._issues)

    def add(self, issue: Issue) -> Issue:
        self._issues.append(issue)
        return issue

    def remove(self, issue_id: str) -> bool:
        before = len(self._issues)
        self._issues = [i for i in self._issues if i.id != issue_id]
        return len(self._issues) != before

    def get(self, issue_id: str) -> Optional[Issue]:
        return next((i for i in self._issues if i.id == issue_id), None)

    def for_segment(self, segment_id: int) -> List[Issue]:
        return [i for i in self._issues if i.segment_id == segment_id]

    def replace_automatic(self, new_issues: Iterable[Issue], origins: Iterable[str] = ("qa", "glossary"),
                          segment_ids: Optional[Iterable[int]] = None) -> None:
        """Put the result of a new QA run in place of the old one.

        A finding that was there before keeps its id, status, comment and date, so a
        finding someone rejected stays rejected. Findings that no longer come up are
        dropped. Human and AI issues are never touched. With ``segment_ids``, only the
        findings of those segments are replaced.
        """
        origins = set(origins)
        scope = set(segment_ids) if segment_ids is not None else None

        def in_scope(issue: Issue) -> bool:
            return issue.origin in origins and (scope is None or issue.segment_id in scope)

        old = {i.key(): i for i in self._issues if in_scope(i)}
        kept = [i for i in self._issues if not in_scope(i)]
        for issue in new_issues:
            previous = old.get(issue.key())
            if previous is not None and previous.text_hash == issue.text_hash:
                issue.id = previous.id
                issue.status = previous.status
                issue.comment = previous.comment
                issue.created_at = previous.created_at
                issue.author = previous.author
            kept.append(issue)
        self._issues = kept

    # ── saving ─────────────────────────────────────────────────────
    def to_list(self) -> List[Dict[str, Any]]:
        return [i.to_dict() for i in self._issues]

    @classmethod
    def from_list(cls, data: Optional[Iterable[Dict[str, Any]]]) -> "IssueList":
        issues = []
        for item in data or []:
            try:
                issues.append(Issue.from_dict(item))
            except (TypeError, ValueError):
                continue        # a record this version cannot read is left out, not fatal
        return cls(issues)
