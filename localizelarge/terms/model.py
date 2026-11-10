"""One glossary entry, independent of file format and of the database."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class Variant:
    """Another term for the same concept in one language."""
    text: str
    forbidden: bool = False


@dataclass
class Entry:
    """A concept with its main term in the source and the target language."""
    source: str
    target: str
    source_variants: List[Variant] = field(default_factory=list)
    target_variants: List[Variant] = field(default_factory=list)
    forbidden: bool = False          # the main target term must not be used
    part_of_speech: str = ""
    definition: str = ""
    notes: str = ""
    domain: str = ""
    uid: str = ""                    # the entry's id in the file or the database
