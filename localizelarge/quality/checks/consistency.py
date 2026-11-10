"""Checks that need the whole project: the same source translated differently, and
different sources with the same translation."""
from __future__ import annotations

from collections import defaultdict
from typing import List

from ..model import Issue
from .base import Check, is_translated, source_of, squash, target_of


def _short(text: str, limit: int = 60) -> str:
    return text if len(text) <= limit else text[:limit - 1] + "…"


class InconsistentTarget(Check):
    id = "qa.inconsistent_target"
    name = "Same source, different targets"
    severity = "minor"
    category = "style/inconsistent-style"
    project_wide = True

    def run_project(self, segments, ctx):
        groups = defaultdict(list)
        for segment in segments:
            if is_translated(segment) and squash(source_of(segment)):
                groups[squash(source_of(segment))].append(segment)
        found: List[Issue] = []
        for group in groups.values():
            targets = {squash(target_of(s)) for s in group}
            if len(targets) < 2:
                continue
            for segment in group:
                others = sorted({f"{s.id}: {_short(squash(target_of(s)))}" for s in group
                                 if squash(target_of(s)) != squash(target_of(segment))})
                found.append(self.issue(
                    segment, ctx,
                    "The same source is translated differently in segment " + "; ".join(others[:3])
                    + (" …" if len(others) > 3 else "")))
        return found


class InconsistentSource(Check):
    id = "qa.inconsistent_source"
    name = "Same target, different sources"
    severity = "minor"
    category = "accuracy/mistranslation"
    project_wide = True

    def run_project(self, segments, ctx):
        groups = defaultdict(list)
        for segment in segments:
            if is_translated(segment):
                groups[squash(target_of(segment))].append(segment)
        found: List[Issue] = []
        for group in groups.values():
            sources = {squash(source_of(s)).casefold() for s in group}
            if len(sources) < 2:
                continue
            for segment in group:
                others = sorted({f"{s.id}: {_short(squash(source_of(s)))}" for s in group
                                 if squash(source_of(s)).casefold() != squash(source_of(segment)).casefold()})
                found.append(self.issue(
                    segment, ctx,
                    "The same target is used for another source in segment " + "; ".join(others[:3])
                    + (" …" if len(others) > 3 else "")))
        return found
