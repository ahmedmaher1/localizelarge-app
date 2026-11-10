"""Fuzzy match scores for translation-memory lookups.

``score(a, b)`` gives 0–100. 100 means the two segments are the same text: the same
words, tags, numbers, upper and lower case and punctuation (only the amount of white
space may differ). Anything else scores 99 or less.

How a score is made:

1. Both texts are normalised: Unicode NFC, case-folded, white space collapsed. Inline
   tags are taken out, and each number is replaced by one placeholder.
2. The base score is the mean of two rapidfuzz measures on the normalised word tokens:
   the word-level edit similarity (a changed word counts once, whatever its length) and
   the character-level similarity of the same tokens (so "colour"/"color" is a small
   difference, not a whole word).
3. Penalties, one point each: every inline tag that differs, every number that differs,
   a difference in upper/lower case only, a difference in punctuation only.

Chinese, Japanese and Thai are written without spaces; their tokens are single
characters.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

_TAG = re.compile(r"<[^<>]+>")
_NUMBER = re.compile(r"\d+(?:[.,:/٫٬]\d+)*")
_SPACE = re.compile(r"\s+")
_WORD = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*", re.UNICODE)
_NUMBER_TOKEN = "①"   # stands for any number in the token list
# Scripts written without spaces between words.
_NO_SPACE = re.compile(
    "[぀-ヿ㐀-䶿一-鿿豈-﫿฀-๿຀-໿"
    "က-႟ក-៿]")
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


@dataclass(frozen=True)
class Detail:
    """How a score was made."""
    base: float            # 0–100, before penalties
    tags: int              # inline tags that differ
    numbers: int           # numbers that differ
    case: bool             # differs in upper/lower case only somewhere
    punctuation: bool      # differs in punctuation only somewhere
    score: int             # the final score, 0–100


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text or "")


def _collapse(text: str) -> str:
    return _SPACE.sub(" ", text).strip()


def tags_of(text: str) -> List[str]:
    """The inline tags of a segment, in order."""
    return _TAG.findall(text or "")


def numbers_of(text: str) -> List[str]:
    """The numbers of a segment (tags excluded), in order, with Western digits."""
    return _NUMBER.findall(_TAG.sub(" ", text or "").translate(_ARABIC_DIGITS))


def tokens_of(text: str) -> List[str]:
    """The normalised word tokens of a segment: tags removed, case-folded, numbers
    replaced by one placeholder, punctuation dropped. Characters of scripts written
    without spaces are one token each."""
    plain = _TAG.sub(" ", _nfc(text)).translate(_ARABIC_DIGITS).casefold()
    plain = _NUMBER.sub(f" {_NUMBER_TOKEN} ", plain)
    tokens: List[str] = []
    for piece in plain.split():
        if piece == _NUMBER_TOKEN:
            tokens.append(piece)
            continue
        for word in _WORD.findall(piece):
            if _NO_SPACE.search(word):
                run = ""
                for char in word:
                    if _NO_SPACE.match(char):
                        if run:
                            tokens.append(run)
                            run = ""
                        tokens.append(char)
                    else:
                        run += char
                if run:
                    tokens.append(run)
            else:
                tokens.append(word)
    return tokens


def _multiset_difference(a: Iterable[str], b: Iterable[str]) -> int:
    """How many items would have to be changed, added or removed to make a into b."""
    ca, cb = Counter(a), Counter(b)
    only_a = sum((ca - cb).values())
    only_b = sum((cb - ca).values())
    return max(only_a, only_b)


def _base(tokens_a: Sequence[str], tokens_b: Sequence[str]) -> float:
    if not tokens_a and not tokens_b:
        return 100.0
    if not tokens_a or not tokens_b:
        return 0.0
    if tokens_a == tokens_b:
        return 100.0
    words = Levenshtein.normalized_similarity(tokens_a, tokens_b) * 100.0
    chars = fuzz.ratio(" ".join(tokens_a), " ".join(tokens_b))
    return (words + chars) / 2.0


class Scorer:
    """Scores many candidates against one source segment. The source is prepared
    once, and a candidate that cannot reach the cutoff is dismissed cheaply."""

    def __init__(self, source: str):
        self.source = _nfc(source)
        self._collapsed = _collapse(self.source)
        self._tokens = tokens_of(self.source)
        self._joined = " ".join(self._tokens)

    def score(self, candidate: str, cutoff: int = 0) -> int:
        """The score of a candidate, or 0 when it is certainly below ``cutoff``."""
        candidate = _nfc(candidate)
        if _collapse(candidate) == self._collapsed:
            return 100
        if cutoff > 0:
            tokens = tokens_of(candidate)
            if not could_reach(self._tokens, tokens, cutoff):
                return 0
            # The base is the mean of a word measure (at most 100) and the
            # character measure, so the character measure must be at least this.
            needed = 2.0 * cutoff - 100.0
            if needed > 0 and fuzz.ratio(self._joined, " ".join(tokens), score_cutoff=needed) == 0:
                return 0
        return explain(self.source, candidate).score


def explain(a: str, b: str) -> Detail:
    """The score of two segments with the parts it was made from."""
    a, b = _nfc(a), _nfc(b)
    if _collapse(a) == _collapse(b):
        return Detail(100.0, 0, 0, False, False, 100)

    tokens_a, tokens_b = tokens_of(a), tokens_of(b)
    base = _base(tokens_a, tokens_b)
    tags = _multiset_difference(tags_of(a), tags_of(b))
    numbers = _multiset_difference(numbers_of(a), numbers_of(b))

    # Case and punctuation: compare the text without tags, word by word.
    # Numbers are masked: a different number is counted above, not here.
    plain_a = _collapse(_NUMBER.sub("0", _TAG.sub(" ", a).translate(_ARABIC_DIGITS)))
    plain_b = _collapse(_NUMBER.sub("0", _TAG.sub(" ", b).translate(_ARABIC_DIGITS)))
    words_a = _WORD.findall(plain_a)
    words_b = _WORD.findall(plain_b)
    folded_same = [w.casefold() for w in words_a] == [w.casefold() for w in words_b]
    case = folded_same and words_a != words_b
    punctuation = False
    if folded_same:
        strip_a = _collapse(_WORD.sub("", plain_a)).replace(" ", "")
        strip_b = _collapse(_WORD.sub("", plain_b)).replace(" ", "")
        punctuation = strip_a != strip_b

    value = base - tags - numbers - (1 if case else 0) - (1 if punctuation else 0)
    # Not the same text, so never 100.
    value = min(value, 99.0)
    score_value = int(max(0.0, min(100.0, value)))
    return Detail(round(base, 2), tags, numbers, case, punctuation, score_value)


def score(a: str, b: str) -> int:
    """The fuzzy match score of two segments, 0–100. 100 means identical."""
    return explain(a, b).score


def similarity(a: str, b: str) -> float:
    """The score as a ratio, 0.0–1.0, for code that works with ratios."""
    return score(a, b) / 100.0


def could_reach(tokens_a: Sequence[str], tokens_b: Sequence[str], threshold: float) -> bool:
    """A cheap test: False when two token lists cannot score ``threshold`` (0–100) or
    more, judged by their lengths alone. Used to skip candidates before scoring."""
    la, lb = len(tokens_a), len(tokens_b)
    if not la or not lb:
        return la == lb
    # Both measures are at most this when the lengths differ.
    return 100.0 * min(la, lb) / max(la, lb) >= threshold - 15.0


def best(source: str, candidates: Iterable[Tuple[str, object]], threshold: int = 75,
         limit: int = 5) -> List[Tuple[int, str, object]]:
    """Score ``source`` against (text, payload) candidates. Returns up to ``limit``
    (score, text, payload) tuples scoring ``threshold`` or more, best first."""
    source_tokens = tokens_of(source)
    found: List[Tuple[int, str, object]] = []
    for text, payload in candidates:
        if not could_reach(source_tokens, tokens_of(text), threshold):
            continue
        value = score(source, text)
        if value >= threshold:
            found.append((value, text, payload))
    found.sort(key=lambda item: item[0], reverse=True)
    return found[:limit]
