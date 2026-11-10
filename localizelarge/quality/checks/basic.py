"""Checks that look at one segment's text."""
from __future__ import annotations

import re
from typing import List

from ..model import Issue
from .base import Check, is_translated, source_of, squash, target_of, western_digits

_URL = re.compile(r"(?:https?://|www\.)[^\s<>\"'،؛]+[^\s<>\"'.,;:!?)\]}،؛。]", re.I)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)


class EmptyTarget(Check):
    id = "qa.empty"
    name = "Empty target"
    severity = "major"
    category = "accuracy/untranslated"

    def run(self, segment, ctx):
        if source_of(segment).strip() and not target_of(segment).strip():
            return [self.issue(segment, ctx, "The target is empty.")]
        return []


class SameAsSource(Check):
    id = "qa.same_as_source"
    name = "Target same as source"
    severity = "minor"
    category = "accuracy/untranslated"

    def run(self, segment, ctx):
        source, target = squash(source_of(segment)), squash(target_of(segment))
        if not target or source != target:
            return []
        # Text with nothing to translate: numbers, codes, URLs, e-mail addresses.
        rest = _EMAIL.sub("", _URL.sub("", source))
        if not _LETTER.search(rest):
            return []
        words = rest.split()
        if len(words) == 1 and (words[0].isupper() or any(ch.isdigit() for ch in words[0])
                                or "_" in words[0]):
            return []        # one code-like word: "OK", "USB", "V2", "MAX_SIZE"
        if ctx.base_lang("source") and ctx.base_lang("source") == ctx.base_lang("target"):
            return []
        return [self.issue(segment, ctx, "The target is the same as the source.")]


class Whitespace(Check):
    id = "qa.whitespace"
    name = "Spaces"
    severity = "minor"
    category = "linguistic-conventions/punctuation"

    def run(self, segment, ctx):
        if not is_translated(segment):
            return []
        source, target = source_of(segment), target_of(segment)
        found: List[Issue] = []
        lead_s, lead_t = len(source) - len(source.lstrip()), len(target) - len(target.lstrip())
        if bool(lead_s) != bool(lead_t):
            found.append(self.issue(
                segment, ctx,
                "The target starts with a space and the source does not." if lead_t
                else "The source starts with a space and the target does not.",
                start=0, end=lead_t))
        trail_s, trail_t = len(source) - len(source.rstrip()), len(target) - len(target.rstrip())
        if bool(trail_s) != bool(trail_t):
            found.append(self.issue(
                segment, ctx,
                "The target ends with a space and the source does not." if trail_t
                else "The source ends with a space and the target does not.",
                start=len(target) - trail_t, end=len(target)))
        if not re.search(r"\S {2,}\S", source):
            for match in re.finditer(r"(?<=\S) {2,}(?=\S)", target):
                found.append(self.issue(segment, ctx, "Two or more spaces in a row.",
                                        start=match.start(), end=match.end(), suggestion=" "))
        return found


class RepeatedWord(Check):
    id = "qa.repeated_word"
    name = "Repeated word"
    severity = "minor"
    category = "linguistic-conventions/grammar"
    _PAIR = re.compile(r"\b([^\W\d_]{2,})(\s+)\1\b", re.UNICODE | re.IGNORECASE)

    def run(self, segment, ctx):
        if not is_translated(segment):
            return []
        source_pairs = {m.group(1).casefold() for m in self._PAIR.finditer(source_of(segment))}
        found = []
        for match in self._PAIR.finditer(target_of(segment)):
            word = match.group(1)
            if word.casefold() in source_pairs:
                continue      # the source repeats a word too ("had had")
            found.append(self.issue(segment, ctx, f"The word “{word}” is written twice in a row.",
                                    start=match.start(), end=match.end(), suggestion=word))
        return found


class Length(Check):
    id = "qa.length"
    name = "Length"
    severity = "minor"
    category = "design-and-markup/truncation-text-expansion"
    params = {"min_ratio": 0.4, "max_ratio": 2.5, "min_chars": 20}

    def run(self, segment, ctx):
        if not is_translated(segment):
            return []
        source, target = source_of(segment).strip(), target_of(segment).strip()
        found = []
        limit = getattr(segment, "max_length", None)
        if isinstance(limit, int) and limit > 0 and len(target) > limit:
            found.append(self.issue(
                segment, ctx,
                f"The target has {len(target)} characters; the file allows {limit}.",
                start=limit, end=len(target)))
        if len(source) >= self.param(ctx, "min_chars"):
            ratio = len(target) / len(source)
            if ratio > self.param(ctx, "max_ratio"):
                found.append(self.issue(
                    segment, ctx, f"The target is {ratio:.1f} times as long as the source."))
            elif ratio < self.param(ctx, "min_ratio"):
                found.append(self.issue(
                    segment, ctx, f"The target is only {ratio:.1f} times the length of the source."))
        return found


class Capitalization(Check):
    id = "qa.capitalization"
    name = "Capital letter at the start"
    severity = "minor"
    category = "linguistic-conventions/spelling"

    @staticmethod
    def _first_letter(text: str):
        for index, char in enumerate(text):
            if char.isalpha():
                return index, char
            if char.isdigit():
                return None     # starts with a number: nothing to compare
        return None

    def run(self, segment, ctx):
        if not is_translated(segment):
            return []
        first_s = self._first_letter(source_of(segment))
        first_t = self._first_letter(target_of(segment))
        if not first_s or not first_t:
            return []
        (_, s), (pos, t) = first_s, first_t
        # Only scripts with upper and lower case: Arabic, Chinese etc. are neither.
        if s.isupper() == s.islower() or t.isupper() == t.islower():
            return []
        if s.isupper() and t.islower():
            return [self.issue(segment, ctx, "The source starts with a capital letter, the target does not.",
                               start=pos, end=pos + 1, suggestion=t.upper())]
        if s.islower() and t.isupper():
            # German nouns and proper names start with a capital anyway.
            if ctx.base_lang("target") == "de":
                return []
            return [self.issue(segment, ctx, "The target starts with a capital letter, the source does not.",
                               start=pos, end=pos + 1, suggestion=t.lower())]
        return []


# Sentence-end marks that mean the same in different scripts.
_END_CLASSES = [
    ("full stop", ".。۔।"),
    ("question mark", "?؟？"),
    ("exclamation mark", "!！"),
    ("comma", ",،，、"),
    ("semicolon", ";؛；"),
    ("colon", ":："),
    ("ellipsis", "…"),
]
_END_CLASS = {char: name for name, chars in _END_CLASSES for char in chars}
_CLOSERS = "\"'”’»)]}›」』）】"
# Languages that normally end a sentence without a full stop.
_NO_FULL_STOP = {"th", "lo", "km", "my"}


class EndPunctuation(Check):
    id = "qa.end_punctuation"
    name = "Punctuation at the end"
    severity = "minor"
    category = "linguistic-conventions/punctuation"

    @staticmethod
    def _ending(text: str):
        text = text.rstrip()
        while text and text[-1] in _CLOSERS:
            text = text[:-1].rstrip()
        if text.endswith("..."):
            return "ellipsis", len(text) - 3
        if text and text[-1] in _END_CLASS:
            return _END_CLASS[text[-1]], len(text) - 1
        return None, len(text)

    def run(self, segment, ctx):
        if not is_translated(segment):
            return []
        source, target = source_of(segment), target_of(segment)
        end_s, _ = self._ending(source)
        end_t, pos = self._ending(target)
        if end_s == end_t:
            return []
        if end_s == "full stop" and end_t is None and ctx.base_lang("target") in _NO_FULL_STOP:
            return []
        if end_t is None:
            return [self.issue(segment, ctx, f"The source ends with a {end_s}, the target with none.",
                               start=len(target.rstrip()), end=len(target.rstrip()))]
        if end_s is None:
            return [self.issue(segment, ctx, f"The target ends with a {end_t}, the source with none.",
                               start=pos, end=len(target.rstrip()))]
        return [self.issue(segment, ctx, f"The source ends with a {end_s}, the target with a {end_t}.",
                           start=pos, end=len(target.rstrip()))]


_PAIRS = [("(", ")"), ("[", "]"), ("{", "}"), ("«", "»"), ("“", "”"), ("‹", "›"),
          ("「", "」"), ("『", "』"), ("（", "）"), ("【", "】")]


class BracketsQuotes(Check):
    id = "qa.brackets_quotes"
    name = "Brackets and quotation marks"
    severity = "minor"
    category = "linguistic-conventions/punctuation"

    @staticmethod
    def _unbalanced(text: str):
        problems = []
        low_quotes = "„" in text      # German and others: „ opens, “ closes
        for opener, closer in _PAIRS:
            if opener == "“" and low_quotes:
                if text.count("„") != text.count("“"):
                    problems.append("„ “")
                continue
            if text.count(opener) != text.count(closer):
                problems.append(f"{opener} {closer}")
        if text.count('"') % 2:
            problems.append('"')
        return problems

    def run(self, segment, ctx):
        if not is_translated(segment):
            return []
        bad_source = set(self._unbalanced(source_of(segment)))
        found = []
        for kind in self._unbalanced(target_of(segment)):
            if kind in bad_source:
                continue      # the source is unpaired in the same way
            found.append(self.issue(segment, ctx, f"Unpaired {kind} in the target."))
        return found


__all__ = ["EmptyTarget", "SameAsSource", "Whitespace", "RepeatedWord", "Length",
           "Capitalization", "EndPunctuation", "BracketsQuotes", "western_digits"]
