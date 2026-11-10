"""MQM quality scores: the linear raw model and the linear calibrated model.

Implemented from the MQM Council's description: Lommel et al., "The Multi-Range Theory
of Translation Quality Measurement: MQM scoring models and Statistical Quality Control",
arXiv:2405.16969, Appendix A, and https://themqm.org/error-types-2/the-mqm-scoring-models/.

Terms, as the paper names them:

EWC   Evaluation Word Count: the words of the evaluated text.
RWC   Reference Word Count: usually 1000.
ETPT  Error Type Penalty Total = Σ (error count × severity multiplier) × error type weight.
APT   Absolute Penalty Total = Σ ETPT.
PWPT  Per-Word Penalty Total = APT / EWC.
NPT   Normed Penalty Total = PWPT × RWC.
APP   Acceptable Penalty Points for the RWC: the error tolerance.
PT    Passing Threshold on the calibrated scale.
DPI   Defined Passing Interval = 100 − PT.
SF    Scaling Factor = DPI / APP.

Raw score        = 100 × (1 − PWPT)          (the error-free part of the text)
Calibrated score = 100 − NPT × SF
Pass             : NPT ≤ APP. On the raw scale that is score ≥ 100 − APP × 100 / RWC;
                   on the calibrated scale it is score ≥ PT.

The paper's non-linear model (for very small and very large samples) is not implemented.
A score below 0, which the linear formulas give for many errors in a short text, is
reported as 0; the penalty totals are reported as calculated.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional

SEVERITIES = ("neutral", "minor", "major", "critical")
# "there should be an exponential difference between values for neutral, minor, major,
# and critical errors. For instance … 0, 1, 5, and 25" (arXiv:2405.16969, A.3).
DEFAULT_MULTIPLIERS = {"neutral": 0.0, "minor": 1.0, "major": 5.0, "critical": 25.0}
RAW = "raw"
CALIBRATED = "calibrated"


@dataclass
class ScoringProfile:
    """The numbers a score is calculated with. A quality profile or pack supplies them."""
    model: str = CALIBRATED
    multipliers: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_MULTIPLIERS))
    weights: Dict[str, float] = field(default_factory=dict)   # category path → weight; default 1
    reference_word_count: float = 1000.0                      # RWC
    acceptable_penalty_points: float = 10.0                   # APP per RWC
    passing_threshold: float = 90.0                           # PT, calibrated scale
    count_open: bool = True          # count issues nobody has decided on yet
    count_open_ai: bool = False      # … also those an AI proposed

    def weight(self, category: str) -> float:
        """The weight of a category: its own, else its dimension's, else 1."""
        if category in self.weights:
            return float(self.weights[category])
        dimension = (category or "").split("/")[0]
        return float(self.weights.get(dimension, 1.0))

    def multiplier(self, severity: str) -> float:
        return float(self.multipliers.get(severity, 0.0))

    @property
    def scaling_factor(self) -> float:
        return (100.0 - self.passing_threshold) / self.acceptable_penalty_points

    @property
    def raw_threshold(self) -> float:
        """The pass mark on the raw scale that the APP stands for."""
        return 100.0 - self.acceptable_penalty_points * 100.0 / self.reference_word_count

    def validate(self) -> None:
        if self.model not in (RAW, CALIBRATED):
            raise ValueError(f"unknown scoring model: {self.model!r}")
        if self.reference_word_count <= 0:
            raise ValueError("the reference word count must be more than 0")
        if self.acceptable_penalty_points <= 0:
            raise ValueError("the acceptable penalty points must be more than 0")
        if not 0 <= self.passing_threshold < 100:
            raise ValueError("the passing threshold must be from 0 to less than 100")
        if any(value < 0 for value in self.multipliers.values()):
            raise ValueError("a severity multiplier cannot be negative")
        if any(value < 0 for value in self.weights.values()):
            raise ValueError("a category weight cannot be negative")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ScoringProfile":
        data = dict(data or {})
        known = {name for name in cls.__dataclass_fields__}
        profile = cls(**{k: v for k, v in data.items() if k in known})
        profile.multipliers = {**DEFAULT_MULTIPLIERS, **{k: float(v) for k, v in profile.multipliers.items()}}
        profile.validate()
        return profile


@dataclass
class CategoryTotal:
    category: str
    counts: Dict[str, int]           # severity → number of issues
    weight: float
    penalty: float                   # ETPT


@dataclass
class Score:
    model: str
    evaluation_word_count: int       # EWC
    issue_count: int                 # issues that were counted
    absolute_penalty_total: float    # APT
    per_word_penalty_total: Optional[float]   # PWPT
    normed_penalty_total: Optional[float]     # NPT
    raw_score: Optional[float]
    calibrated_score: Optional[float]
    score: Optional[float]           # the one the profile's model reports
    threshold: float                 # on the same scale as ``score``
    passed: Optional[bool]           # None: no words were evaluated
    by_category: List[CategoryTotal]
    by_severity: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def counted(issues: Iterable[Any], profile: ScoringProfile) -> List[Any]:
    """The issues that count towards the score.

    Accepted issues count. Rejected and fixed ones do not. Open ones count when the
    profile says so; open AI proposals only when the profile says that too, so an AI
    cannot lower a score before a person has looked.
    """
    out = []
    for issue in issues:
        if issue.status == "accepted":
            out.append(issue)
        elif issue.status == "open" and profile.count_open:
            if issue.origin == "ai" and not profile.count_open_ai:
                continue
            out.append(issue)
    return out


def penalty_totals(issues: Iterable[Any], profile: ScoringProfile) -> List[CategoryTotal]:
    """ETPT for each category that has issues, in order of first appearance."""
    totals: Dict[str, CategoryTotal] = {}
    for issue in issues:
        total = totals.get(issue.category)
        if total is None:
            total = totals[issue.category] = CategoryTotal(
                issue.category, {s: 0 for s in SEVERITIES}, profile.weight(issue.category), 0.0)
        total.counts[issue.severity] = total.counts.get(issue.severity, 0) + 1
    for total in totals.values():
        total.penalty = sum(count * profile.multiplier(severity)
                            for severity, count in total.counts.items()) * total.weight
    return list(totals.values())


def calculate(issues: Iterable[Any], evaluation_word_count: int,
              profile: Optional[ScoringProfile] = None) -> Score:
    """The score of an evaluated text."""
    profile = profile or ScoringProfile()
    profile.validate()
    used = counted(issues, profile)
    by_category = penalty_totals(used, profile)
    apt = sum(total.penalty for total in by_category)
    by_severity = {s: sum(t.counts.get(s, 0) for t in by_category) for s in SEVERITIES}
    threshold = profile.raw_threshold if profile.model == RAW else profile.passing_threshold

    if evaluation_word_count <= 0:
        return Score(profile.model, 0, len(used), apt, None, None, None, None, None,
                     threshold, None, by_category, by_severity)

    pwpt = apt / evaluation_word_count
    npt = pwpt * profile.reference_word_count
    # On a short text a few errors push the linear formulas below zero (the paper's
    # non-linear model is its answer to that). A score is shown as 0 at the lowest.
    raw = max(0.0, 100.0 * (1.0 - pwpt))
    calibrated = max(0.0, 100.0 - npt * profile.scaling_factor)
    value = raw if profile.model == RAW else calibrated
    # The same test on either scale: the normed penalty is within the tolerance.
    passed = npt <= profile.acceptable_penalty_points + 1e-9
    return Score(profile.model, int(evaluation_word_count), len(used), apt, pwpt, npt, raw,
                 calibrated, value, threshold, passed, by_category, by_severity)


def word_count(segments: Iterable[Any]) -> int:
    """The Evaluation Word Count of segments: the words of their source text. In text
    written without spaces (Chinese, Japanese, Thai) each character counts as a word."""
    from localizelarge.tm.score import tokens_of
    return sum(len(tokens_of(getattr(segment, "source", "") or "")) for segment in segments)
