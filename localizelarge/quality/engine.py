"""Runs the QA checks: on one segment when it is confirmed, on the whole project from
"Run QA"."""
from __future__ import annotations

from typing import Iterable, List, Optional, Sequence

from .checks import ALL_CHECKS, Check, Context
from .model import Issue


def checks(only: Optional[Iterable[str]] = None) -> List[Check]:
    """One instance of every check, or of those whose ids are given."""
    wanted = set(only) if only is not None else None
    return [cls() for cls in ALL_CHECKS if wanted is None or cls.id in wanted]


def run_segment(segment, ctx: Context, only: Optional[Iterable[str]] = None) -> List[Issue]:
    """The checks that need only this segment."""
    found: List[Issue] = []
    for check in checks(only):
        if check.project_wide or not check.enabled(ctx):
            continue
        found.extend(check.run(segment, ctx))
    return found


def run_project(segments: Sequence, ctx: Context, only: Optional[Iterable[str]] = None,
                progress=None) -> List[Issue]:
    """Every check on every segment."""
    active = [c for c in checks(only) if c.enabled(ctx)]
    per_segment = [c for c in active if not c.project_wide]
    found: List[Issue] = []
    total = len(segments)
    for number, segment in enumerate(segments, 1):
        for check in per_segment:
            found.extend(check.run(segment, ctx))
        if progress and (number % 200 == 0 or number == total):
            progress(number, total)
    for check in active:
        if check.project_wide:
            found.extend(check.run_project(segments, ctx))
    return found
