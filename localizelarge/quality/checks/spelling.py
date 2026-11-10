"""Spelling, with the dictionaries on this computer, and the user's saved regex checks."""
from __future__ import annotations

import re
from typing import List

from ..model import Issue, make_issue, plain_text
from .base import Check, is_translated, source_of, target_of

_WORD = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*", re.UNICODE)


class Spelling(Check):
    id = "qa.spelling"
    name = "Spelling"
    severity = "minor"
    category = "linguistic-conventions/spelling"

    def run(self, segment, ctx):
        if ctx.spell_check is None or not is_translated(segment):
            return []
        target = target_of(segment)
        in_source = {w.casefold() for w in _WORD.findall(source_of(segment))}
        found: List[Issue] = []
        seen = set()
        for match in _WORD.finditer(target):
            word = match.group(0)
            if len(word) < 2 or word.casefold() in in_source or word in seen:
                continue      # a name or product name carried over from the source
            if word.isupper() and len(word) <= 6:
                continue      # an abbreviation
            try:
                correct = ctx.spell_check(word)
            except Exception:
                correct = True
            if not correct:
                seen.add(word)
                found.append(self.issue(segment, ctx, f"“{word}” is not in the dictionary.",
                                        start=match.start(), end=match.end()))
        return found


class SavedRegex(Check):
    """The find-only operations a user saved as QA checks (the base app's QA sets)."""
    id = "qa.regex"
    name = "Your own checks"
    severity = "minor"
    category = "style/organization-style"
    project_wide = True

    def run_project(self, segments, ctx):
        if not ctx.regex_checks:
            return []
        from modules.qa_checks import run_checks
        findings, _problems = run_checks(segments, ctx.regex_checks)
        by_id = {getattr(s, "id", None): s for s in segments}
        found: List[Issue] = []
        for finding in findings:
            segment = by_id.get(finding.segment_id)
            if segment is None:
                continue
            side_text = segment.source if finding.side == "source" else segment.target
            # The saved checks search the text with its tags; an issue's offsets count
            # in the plain text. They agree only when nothing before the match is a tag.
            plain = plain_text(side_text)
            same = plain[finding.start:finding.end] == finding.text and side_text[:finding.start] == plain[:finding.start]
            found.append(make_issue(
                segment, origin="qa", rule_id=self.id,
                category=ctx.setting(self.id, "category", self.category),
                severity=ctx.setting(self.id, "severity", self.severity),
                message=f"{finding.check}: {finding.context}", side=finding.side,
                start=finding.start if same else None, end=finding.end if same else None))
        return found
