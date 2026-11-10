"""Checks that compare the "hard" items of source and target: inline tags, numbers,
placeholders, URLs and e-mail addresses."""
from __future__ import annotations

import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Set, Tuple

from ..model import Issue
from .base import Check, Context, is_translated, source_of, target_of, western_digits

_TAG = re.compile(r"<[^<>\s][^<>\n]{0,200}>")


def _tags(text: str, ctx: Context) -> List[str]:
    if ctx.extract_tags is not None:
        return list(ctx.extract_tags(text or ""))
    return _TAG.findall(text or "")


class Tags(Check):
    id = "qa.tags"
    name = "Inline tags"
    severity = "major"
    category = "design-and-markup/markup-tag"

    def run(self, segment, ctx):
        if not is_translated(segment):
            return []
        source_tags = _tags(getattr(segment, "source", ""), ctx)
        target_tags = _tags(getattr(segment, "target", ""), ctx)
        if source_tags == target_tags:
            return []
        have, want = Counter(target_tags), Counter(source_tags)
        missing = list((want - have).elements())
        extra = list((have - want).elements())
        found = []
        if missing:
            found.append(self.issue(segment, ctx, "Missing in the target: " + " ".join(missing)))
        if extra:
            found.append(self.issue(segment, ctx, "In the target but not in the source: " + " ".join(extra)))
        if not missing and not extra:
            # The same tags in another order. A moved pair is normal in translation;
            # what is wrong is a closing tag before its opening tag, or crossed pairs.
            problem = _nesting_problem(target_tags)
            if problem:
                found.append(self.issue(segment, ctx, problem))
        return found


def _nesting_problem(tags: List[str]) -> Optional[str]:
    stack: List[str] = []
    for tag in tags:
        inner = tag.strip("<>")
        if inner.endswith("/"):
            continue                              # a placeholder: <x1/>
        name = inner.lstrip("/").split()[0]
        if inner.startswith("/"):
            if not stack:
                return f"{tag} closes a tag that was not opened before it."
            if stack[-1] != name:
                return f"{tag} closes before the tag inside it is closed."
            stack.pop()
        else:
            stack.append(name)
    return None


# ── Numbers ───────────────────────────────────────────────────────────

_NUMBER = re.compile(r"(?<![\w.,])[-−+]?\d+(?:[.,٫٬'’   ](?=\d)\d+)*(?![\w])"
                     r"|\d+(?:[.,٫٬]\d+)*")


def _readings(token: str) -> Set[str]:
    """Every value a written number can stand for.

    "1,000.5" and "1.000,5" are the same number written for different locales, and
    "1,234" may be 1234 or 1.234. A token is read both ways; two numbers are equal
    when their readings overlap.
    """
    text = western_digits(token).replace("−", "-").lstrip("+")
    text = re.sub(r"['’   ٬]", "", text)       # group separators that are never decimal
    text = text.replace("٫", ".")                         # the Arabic decimal separator
    readings: Set[str] = set()
    for group, decimal in ((",", "."), (".", ",")):
        parts = text.split(decimal)
        if len(parts) > 2:
            continue
        whole = parts[0]
        # A group separator is followed by exactly three digits.
        chunks = whole.lstrip("-").split(group)
        if len(chunks) > 1 and not (1 <= len(chunks[0]) <= 3 and all(len(c) == 3 for c in chunks[1:])):
            continue
        number = whole.replace(group, "") + ("." + parts[1] if len(parts) == 2 else "")
        try:
            value = Decimal(number)
        except InvalidOperation:
            continue
        readings.add(format(value.normalize(), "f") if value != 0 else "0")
    if not readings:
        readings.add(re.sub(r"\D", "", text))
    return readings


def numbers_in(text: str) -> List[Tuple[str, int, int]]:
    """(number as written, start, end) for each number in a plain text."""
    return [(m.group(0), m.start(), m.end()) for m in _NUMBER.finditer(western_digits(text))]


class Numbers(Check):
    id = "qa.numbers"
    name = "Numbers"
    severity = "major"
    category = "accuracy/mistranslation"

    def run(self, segment, ctx):
        if not is_translated(segment):
            return []
        source, target = source_of(segment), target_of(segment)
        source_numbers = numbers_in(source)
        target_numbers = numbers_in(target)
        unmatched_target = list(target_numbers)
        missing = []
        for written, _, _ in source_numbers:
            readings = _readings(written)
            hit = next((t for t in unmatched_target if readings & _readings(t[0])), None)
            if hit is None:
                missing.append(written)
            else:
                unmatched_target.remove(hit)
        found: List[Issue] = []
        for written in missing:
            found.append(self.issue(segment, ctx, f"The number {written} of the source is not in the target."))
        for written, start, end in unmatched_target:
            found.append(self.issue(segment, ctx, f"The number {target[start:end]} is not in the source.",
                                    start=start, end=end))
        return found


# ── Placeholders ──────────────────────────────────────────────────────

_PLACEHOLDERS = re.compile(
    r"%(?:\d+\$)?[-+0#]*\d*(?:\.\d+)?(?:hh|h|ll|l|L|z|j|t)?[sdiufFxXcoeEgG@]"   # %s %d %1$s %.2f %@
    r"|%\([A-Za-z_]\w*\)[sdif]"                                                 # %(name)s
    r"|\{\{\s*[\w.]+\s*\}\}"                                                    # {{name}}
    r"|\$\{[\w.]+\}"                                                            # ${name}
    r"|\{[A-Za-z_][\w.]*\s*,\s*(?:plural|select|selectordinal|number|date|time)\b"  # ICU head
    r"|\{[A-Za-z_][\w.]*\}"                                                     # {name}
    r"|\{\d+\}"                                                                 # {0}
)


def placeholders_in(text: str) -> List[str]:
    """The placeholders of a text. An ICU message is named by its head only
    ("{count, plural"), because the words inside it are translated."""
    out = []
    for match in _PLACEHOLDERS.finditer(text or ""):
        token = match.group(0)
        if re.match(r"\{[A-Za-z_][\w.]*\s*,", token):
            name, kind = token[1:].split(",", 1)
            token = "{" + name.strip() + ", " + kind.strip()
        out.append(token)
    return out


class Placeholders(Check):
    id = "qa.placeholders"
    name = "Placeholders"
    severity = "major"
    category = "accuracy/mistranslation"

    def run(self, segment, ctx):
        if not is_translated(segment):
            return []
        want = Counter(placeholders_in(source_of(segment)))
        have = Counter(placeholders_in(target_of(segment)))
        found = []
        for token in sorted((want - have).elements()):
            found.append(self.issue(segment, ctx, f"The placeholder {token} of the source is not in the target."))
        for token in sorted((have - want).elements()):
            found.append(self.issue(segment, ctx, f"The placeholder {token} is not in the source."))
        return found


# ── URLs and e-mail addresses ─────────────────────────────────────────

_URL = re.compile(r"(?:https?://|ftp://|www\.)[^\s<>\"'،؛]*[^\s<>\"'.,;:!?)\]}،؛。]", re.I)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")


class UrlsEmails(Check):
    id = "qa.urls_emails"
    name = "URLs and e-mail addresses"
    severity = "major"
    category = "accuracy/mistranslation"

    def run(self, segment, ctx):
        if not is_translated(segment):
            return []
        source, target = source_of(segment), target_of(segment)
        found = []
        for label, pattern in (("URL", _URL), ("e-mail address", _EMAIL)):
            want = Counter(m.group(0) for m in pattern.finditer(source))
            have = Counter(m.group(0) for m in pattern.finditer(target))
            for item in sorted((want - have).elements()):
                found.append(self.issue(segment, ctx, f"The {label} {item} of the source is not in the target."))
            for item in sorted((have - want).elements()):
                found.append(self.issue(segment, ctx, f"The {label} {item} is not in the source."))
        return found
