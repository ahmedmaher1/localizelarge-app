"""Glossary checks: is the approved term used, is a forbidden term used, and is one
term translated the same way everywhere.

``glossary.required``      a source term is in the source, but none of its approved target
                           terms or variants is in the target.
``glossary.forbidden``     a forbidden target term of that entry is in the target.
``glossary.inconsistent``  one source term is translated with different approved variants
                           in the project.

Matching
--------
* Whole words by default. Text written without spaces (Chinese, Japanese, Thai) is
  searched as a string.
* Text is compared in Unicode NFC, and case-folded unless the entry is case-sensitive.
* Arabic script: tatweel and diacritics are ignored and the alef forms أ إ آ ٱ are read
  as ا. In Arabic, a word may also carry the attached prefixes و ف ب ل ك ال and their
  combinations (والمضخة, بالمضخة, للمضخة for مضخة).
* A target term found only through the Arabic rules is reported as "possibly" the term,
  with minor severity, not as missing. (``report_possible`` switches that off.)
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .model import Issue, make_issue, plain_text

REQUIRED = "glossary.required"
FORBIDDEN = "glossary.forbidden"
INCONSISTENT = "glossary.inconsistent"

DEFAULTS: Dict[str, Dict[str, Any]] = {
    REQUIRED: {"severity": "major", "category": "terminology/wrong-term",
               "possible_severity": "minor", "report_possible": True},
    FORBIDDEN: {"severity": "major", "category": "terminology/inconsistent-with-terminology-resource"},
    INCONSISTENT: {"severity": "minor", "category": "terminology/inconsistent-use-of-terminology"},
}

EXACT, LOOSE = 0, 1     # how a term was found: as written, or only by the Arabic rules

# A word: letters and digits, with the combining marks written on them (Arabic
# diacritics, accents in decomposed form) and an apostrophe inside.
_WORD = re.compile(r"(?:[^\W_]|[\u0300-\u036f\u064b-\u065f\u0670\u06d6-\u06ed])+"
                   r"(?:['’](?:[^\W_]|[\u0300-\u036f\u064b-\u065f\u0670])+)*", re.UNICODE)
_NO_SPACE = re.compile("[぀-ヿ㐀-䶿一-鿿豈-﫿฀-๿]")
_ARABIC_SCRIPT = {"ar", "fa", "ur", "ps", "ckb", "ug", "sd"}
_AR_MARKS = re.compile("[ـً-ٰٟۖ-ۭ]")
_AR_ALEF = str.maketrans("أإآٱ", "اااا")
# Conjunction, then preposition, then the article; "لل" is ل + ال with the alef dropped.
_AR_PREFIX = re.compile("^([وف]?)(?:(لل)|([بلك]?)(ال)?)")


def _base(lang: Optional[str]) -> str:
    return (lang or "").replace("_", "-").split("-")[0].lower()


def arabic_normal(text: str) -> str:
    """Arabic-script text without tatweel and diacritics, alef forms unified."""
    return _AR_MARKS.sub("", text).translate(_AR_ALEF)


def arabic_stems(word: str) -> set:
    """The word itself and what is left when attached prefixes are taken off."""
    word = arabic_normal(word)
    stems = {word}
    match = _AR_PREFIX.match(word)
    conj, lam_lam, prep, article = match.groups()
    position = len(conj)
    cuts = set()
    if conj:
        cuts.add(position)                    # و|المضخة
    if lam_lam:
        cuts.add(position + 2)                # لل|مضخة
    else:
        if prep:
            cuts.add(position + 1)            # ب|المضخة
        if article:
            cuts.add(position + len(prep) + 2)   # (ب)ال|مضخة
    for cut in cuts:
        if len(word) - cut >= 2:
            stems.add(word[cut:])
    return stems


@dataclass
class Token:
    text: str        # NFC, as written
    folded: str      # case-folded
    start: int
    end: int


def tokenize(text: str) -> List[Token]:
    text = unicodedata.normalize("NFC", text or "")
    return [Token(m.group(0), m.group(0).casefold(), m.start(), m.end()) for m in _WORD.finditer(text)]


@dataclass
class GlossaryEntry:
    source: str
    targets: List[str] = field(default_factory=list)          # approved: main term and variants
    forbidden: List[str] = field(default_factory=list)        # must not be used
    source_variants: List[str] = field(default_factory=list)
    case_sensitive: bool = False
    glossary: str = ""
    uid: str = ""


@dataclass
class Hit:
    entry: GlossaryEntry
    start: int
    end: int
    level: int
    term: str        # the term (or variant) that was found


class _TermIndex:
    """Finds many terms in a text quickly: terms are looked up by their first word."""

    def __init__(self, lang: str):
        self.lang = _base(lang)
        self.arabic_script = self.lang in _ARABIC_SCRIPT
        self.prefixes = self.lang == "ar"
        self._by_first: Dict[str, List[Tuple[List[Token], Any, bool, str]]] = defaultdict(list)
        self._strings: List[Tuple[str, Any, bool, str]] = []    # terms in no-space scripts

    def _key(self, token: Token) -> str:
        key = token.folded
        if self.arabic_script:
            key = arabic_normal(key)
            if self.prefixes and key.startswith("ال") and len(key) > 3:
                key = key[2:]
        return key

    def keys_of(self, token: Token) -> set:
        """Every key under which a term starting at this word may be filed."""
        keys = {self._key(token)}
        if self.prefixes:
            keys |= {stem[2:] if stem.startswith("ال") and len(stem) > 3 else stem
                     for stem in arabic_stems(token.folded)}
        return keys

    def add(self, term: str, payload: Any, case_sensitive: bool) -> None:
        term = unicodedata.normalize("NFC", (term or "").strip())
        if not term:
            return
        if _NO_SPACE.search(term):
            self._strings.append((term, payload, case_sensitive, term))
            return
        tokens = tokenize(term)
        if tokens:
            self._by_first[self._key(tokens[0])].append((tokens, payload, case_sensitive, term))

    def _token_level(self, text_token: Token, term_token: Token, case_sensitive: bool,
                     first: bool) -> Optional[int]:
        if text_token.text == term_token.text:
            return EXACT
        if not case_sensitive and text_token.folded == term_token.folded:
            return EXACT
        if case_sensitive and text_token.folded == term_token.folded and not self.arabic_script:
            return None
        if self.arabic_script:
            if arabic_normal(text_token.folded) == arabic_normal(term_token.folded):
                return LOOSE
            if self.prefixes and first:
                term_stems = arabic_stems(term_token.folded)
                if arabic_stems(text_token.folded) & term_stems:
                    return LOOSE
        return None

    def find(self, text: str, tokens: Optional[List[Token]] = None) -> List[Tuple[Any, int, int, int, str]]:
        """(payload, start, end, level, term) for every term found in the text."""
        text = unicodedata.normalize("NFC", text or "")
        tokens = tokens if tokens is not None else tokenize(text)
        found = []
        for index, token in enumerate(tokens):
            for key in self.keys_of(token):
                for term_tokens, payload, case_sensitive, term in self._by_first.get(key, ()):
                    if index + len(term_tokens) > len(tokens):
                        continue
                    level = EXACT
                    for offset, term_token in enumerate(term_tokens):
                        token_level = self._token_level(tokens[index + offset], term_token,
                                                        case_sensitive, offset == 0)
                        if token_level is None:
                            level = None
                            break
                        level = max(level, token_level)
                    if level is not None:
                        found.append((payload, token.start, tokens[index + len(term_tokens) - 1].end,
                                      level, term))
        if self._strings:
            folded = text.casefold()
            for term, payload, case_sensitive, shown in self._strings:
                position = text.find(term) if case_sensitive else folded.find(term.casefold())
                if position >= 0:
                    found.append((payload, position, position + len(term), EXACT, shown))
        return found


class Glossary:
    """The entries to check against, prepared for one language pair."""

    def __init__(self, entries: Iterable[GlossaryEntry], source_lang: str = "", target_lang: str = ""):
        self.entries = list(entries)
        self.source_lang, self.target_lang = source_lang, target_lang
        self._source = _TermIndex(source_lang)
        for entry in self.entries:
            for term in [entry.source, *entry.source_variants]:
                self._source.add(term, entry, entry.case_sensitive)
        self._target = _TermIndex(target_lang)
        self._target_cache: Dict[int, Any] = {}

    def __len__(self):
        return len(self.entries)

    def source_hits(self, source_text: str) -> List[Hit]:
        """The entries whose source term is in a source text; one hit per entry, the
        longest and best match first."""
        best: Dict[int, Hit] = {}
        for entry, start, end, level, term in self._source.find(plain_text(source_text)):
            hit = Hit(entry, start, end, level, term)
            known = best.get(id(entry))
            if known is None or (hit.level, -(hit.end - hit.start)) < (known.level, -(known.end - known.start)):
                best[id(entry)] = hit
        hits = sorted(best.values(), key=lambda h: (h.start, -(h.end - h.start)))
        # A longer term covers a shorter one inside it ("pressure gauge" over "gauge").
        kept: List[Hit] = []
        for hit in hits:
            if not any(k.start <= hit.start and hit.end <= k.end and (k.end - k.start) > (hit.end - hit.start)
                       for k in kept):
                kept.append(hit)
        return kept

    def _target_terms(self, entry: GlossaryEntry):
        """The entry's approved and forbidden terms, tokenised once."""
        cached = self._target_cache.get(id(entry))
        if cached is None:
            def prepare(terms):
                out = []
                for term in terms:
                    term = unicodedata.normalize("NFC", (term or "").strip())
                    if term:
                        out.append((term, None if _NO_SPACE.search(term) else tokenize(term)))
                return out
            cached = self._target_cache[id(entry)] = (prepare(entry.targets), prepare(entry.forbidden))
        return cached

    def prepare_target(self, target_text: str) -> "_Prepared":
        """A target text made ready for looking up many terms."""
        return _Prepared(unicodedata.normalize("NFC", plain_text(target_text)), self._target)

    def target_use(self, entry: GlossaryEntry, target, tokens=None):
        """(approved hits, forbidden hits) of an entry in a target text; each hit is
        (term, start, end, level). ``target`` is a text or a prepared text."""
        prepared = target if isinstance(target, _Prepared) else self.prepare_target(target)
        approved, forbidden = self._target_terms(entry)
        return (prepared.find(approved, entry.case_sensitive),
                prepared.find(forbidden, entry.case_sensitive))


class _Prepared:
    """A text with its words indexed by the keys a term's first word can have."""

    def __init__(self, text: str, index: _TermIndex):
        self.text = text
        self.index = index
        self.tokens = tokenize(text)
        self._folded: Optional[str] = None
        self.positions: Dict[str, List[int]] = defaultdict(list)
        for number, token in enumerate(self.tokens):
            for key in index.keys_of(token):
                self.positions[key].append(number)

    def find(self, terms, case_sensitive: bool) -> List[Tuple[str, int, int, int]]:
        found = []
        for term, term_tokens in terms:
            if term_tokens is None:                       # a no-space script: plain search
                if self._folded is None:
                    self._folded = self.text.casefold()
                position = self.text.find(term) if case_sensitive else self._folded.find(term.casefold())
                if position >= 0:
                    found.append((term, position, position + len(term), EXACT))
                continue
            for start in self.positions.get(self.index._key(term_tokens[0]), ()):
                if start + len(term_tokens) > len(self.tokens):
                    continue
                level = EXACT
                for offset, term_token in enumerate(term_tokens):
                    token_level = self.index._token_level(self.tokens[start + offset], term_token,
                                                          case_sensitive, offset == 0)
                    if token_level is None:
                        level = None
                        break
                    level = max(level, token_level)
                if level is not None:
                    found.append((term, self.tokens[start].start,
                                  self.tokens[start + len(term_tokens) - 1].end, level))
        return found


def _setting(settings: Optional[Dict[str, Dict[str, Any]]], rule: str, name: str) -> Any:
    return (settings or {}).get(rule, {}).get(name, DEFAULTS[rule].get(name))


def _issue(segment, rule: str, settings, message: str, *, severity: Optional[str] = None,
           side: str = "target", start=None, end=None, suggestion=None) -> Issue:
    return make_issue(segment, origin="glossary", rule_id=rule,
                      category=_setting(settings, rule, "category"),
                      severity=severity or _setting(settings, rule, "severity"),
                      message=message, side=side, start=start, end=end, suggestion=suggestion)


def check_segment(segment, glossary: Glossary,
                  settings: Optional[Dict[str, Dict[str, Any]]] = None) -> List[Issue]:
    """``glossary.required`` and ``glossary.forbidden`` for one segment."""
    target = getattr(segment, "target", "") or ""
    if not target.strip() or not len(glossary):
        return []
    hits = glossary.source_hits(getattr(segment, "source", "") or "")
    if not hits:
        return []
    prepared = glossary.prepare_target(target)
    target_plain = prepared.text
    found: List[Issue] = []
    for hit in hits:
        entry = hit.entry
        approved, forbidden = glossary.target_use(entry, prepared)
        if (settings or {}).get(FORBIDDEN, {}).get("enabled", True):
            for term, start, end, _level in forbidden:
                found.append(_issue(
                    segment, FORBIDDEN, settings,
                    f"“{term}” must not be used for “{hit.term}”."
                    + (f" Use “{entry.targets[0]}”." if entry.targets else ""),
                    start=start, end=end, suggestion=entry.targets[0] if entry.targets else None))
        if not entry.targets or not (settings or {}).get(REQUIRED, {}).get("enabled", True):
            continue
        if any(level == EXACT for _, _, _, level in approved):
            continue
        wanted = " or ".join(f"“{t}”" for t in entry.targets[:3])
        if approved:
            if _setting(settings, REQUIRED, "report_possible"):
                term, start, end, _ = approved[0]
                found.append(_issue(
                    segment, REQUIRED, settings,
                    f"“{target_plain[start:end]}” is possibly the glossary term {wanted} for “{hit.term}”, "
                    "written differently. Check it.",
                    severity=_setting(settings, REQUIRED, "possible_severity"), start=start, end=end))
            continue
        found.append(_issue(
            segment, REQUIRED, settings,
            f"The source has “{hit.term}”. The glossary term {wanted} is not in the target.",
            suggestion=entry.targets[0]))
    return found


def check_project(segments: Sequence[Any], glossary: Glossary,
                  settings: Optional[Dict[str, Dict[str, Any]]] = None) -> List[Issue]:
    """``glossary.inconsistent``: one source term, different approved variants."""
    if not len(glossary) or not (settings or {}).get(INCONSISTENT, {}).get("enabled", True):
        return []
    uses: Dict[int, Dict[str, List[Tuple[Any, int, int]]]] = defaultdict(lambda: defaultdict(list))
    entries: Dict[int, Tuple[GlossaryEntry, str]] = {}
    for segment in segments:
        target = getattr(segment, "target", "") or ""
        if not target.strip():
            continue
        prepared = None
        for hit in glossary.source_hits(getattr(segment, "source", "") or ""):
            if len(hit.entry.targets) < 2:
                continue
            prepared = prepared or glossary.prepare_target(target)
            approved, _ = glossary.target_use(hit.entry, prepared)
            for term, start, end, _level in approved[:1]:
                uses[id(hit.entry)][term].append((segment, start, end))
                entries[id(hit.entry)] = (hit.entry, hit.term)
    found: List[Issue] = []
    for key, by_term in uses.items():
        if len(by_term) < 2:
            continue
        entry, source_term = entries[key]
        most_used = max(by_term, key=lambda term: (len(by_term[term]), -entry.targets.index(term)))
        for term, places in by_term.items():
            if term == most_used:
                continue
            for segment, start, end in places:
                found.append(_issue(
                    segment, INCONSISTENT, settings,
                    f"“{source_term}” is translated as “{term}” here and as “{most_used}” in "
                    f"{len(by_term[most_used])} other segment(s).",
                    start=start, end=end, suggestion=most_used))
    return found


def run(segments: Sequence[Any], glossary: Glossary,
        settings: Optional[Dict[str, Dict[str, Any]]] = None) -> List[Issue]:
    """All three glossary checks on a project."""
    found: List[Issue] = []
    for segment in segments:
        found.extend(check_segment(segment, glossary, settings))
    found.extend(check_project(segments, glossary, settings))
    return found


def entries_from_termbase(termbase_mgr, termbase_id: int, name: str = "") -> List[GlossaryEntry]:
    """The entries of a termbase in the app's database."""
    from localizelarge.terms import store
    cursor = termbase_mgr.db_manager.cursor
    cursor.execute("SELECT term_uuid, COALESCE(case_sensitive, 0) FROM termbase_terms "
                   "WHERE termbase_id = CAST(? AS TEXT)", (termbase_id,))
    case_by_uid = {row[0]: bool(row[1]) for row in cursor.fetchall()}
    out: List[GlossaryEntry] = []
    for entry in store.export_entries(termbase_mgr, termbase_id):
        targets = [] if entry.forbidden else [entry.target]
        forbidden = [entry.target] if entry.forbidden else []
        for variant in entry.target_variants:
            (forbidden if variant.forbidden else targets).append(variant.text)
        out.append(GlossaryEntry(
            source=entry.source, targets=targets, forbidden=forbidden,
            source_variants=[v.text for v in entry.source_variants if not v.forbidden],
            case_sensitive=case_by_uid.get(entry.uid, False), glossary=name, uid=entry.uid))
    return out
