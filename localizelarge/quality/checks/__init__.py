"""The QA checks, in the order they are listed in the app."""
from .base import Check, Context
from .basic import (BracketsQuotes, Capitalization, EmptyTarget, EndPunctuation, Length,
                    RepeatedWord, SameAsSource, Whitespace)
from .consistency import InconsistentSource, InconsistentTarget
from .spelling import SavedRegex, Spelling
from .tokens import Numbers, Placeholders, Tags, UrlsEmails

ALL_CHECKS = [
    EmptyTarget, SameAsSource, Tags, Numbers, Placeholders, UrlsEmails, Whitespace,
    EndPunctuation, BracketsQuotes, RepeatedWord, InconsistentTarget, InconsistentSource,
    Length, Capitalization, Spelling, SavedRegex,
]

__all__ = ["ALL_CHECKS", "Check", "Context"]
