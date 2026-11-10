"""Phase 5: MQM scoring, checked against the worked examples of the MQM Council's paper
(arXiv:2405.16969, Appendix A) and scoring page (themqm.org, "The MQM scoring models").

Each test names the passage it reproduces.
"""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from localizelarge.mqm import scoring  # noqa: E402
from localizelarge.mqm.scoring import CALIBRATED, RAW, ScoringProfile, calculate  # noqa: E402


def issues(minor=0, major=0, critical=0, neutral=0, category="accuracy/mistranslation",
           status="accepted", origin="human"):
    return [SimpleNamespace(category=category, severity=severity, status=status, origin=origin)
            for severity, count in (("minor", minor), ("major", major), ("critical", critical),
                                    ("neutral", neutral))
            for _ in range(count)]


def test_default_severity_multipliers():
    """A.3: "the values could be 0, 1, 5, and 25" for neutral, minor, major, critical."""
    assert scoring.DEFAULT_MULTIPLIERS == {"neutral": 0, "minor": 1, "major": 5, "critical": 25}


def test_error_type_penalty_total():
    """A.4.2: ETPT = ((minor count × minor multiplier) + (major count × major multiplier)
    + (critical count × critical multiplier)) × error type weight."""
    profile = ScoringProfile(weights={"accuracy/mistranslation": 2})
    (total,) = scoring.penalty_totals(issues(minor=3, major=2, critical=1, neutral=4), profile)
    assert total.penalty == ((3 * 1) + (2 * 5) + (1 * 25)) * 2 == 76


def test_absolute_per_word_and_normed_penalty_totals():
    """A.4.3–A.4.5: APT = Σ ETPT; PWPT = APT / EWC; NPT = PWPT × RWC = (APT × RWC) / EWC."""
    found = issues(minor=4, category="accuracy/omission") + issues(major=1, category="style/awkward-style")
    result = calculate(found, 500, ScoringProfile(model=RAW))
    assert result.absolute_penalty_total == 9
    assert result.per_word_penalty_total == pytest.approx(9 / 500)
    assert result.normed_penalty_total == pytest.approx(9 * 1000 / 500) == pytest.approx(18)


@pytest.mark.parametrize("penalty_points, raw_score", [
    (5, 99.5),     # A.5.1: "a Raw Score of 99.5 (e.g., five penalty points for a thousand-word RWC)"
    (28, 97.2),    # A.5.1: "a raw score of 97.2 (e.g., 28 penalty points for the same RWC)"
    (20, 98.0),    # A.6.2: "the raw passing threshold is 98 … a maximum of 20 raw penalty points … 1000 words"
    (10, 99.0),    # A.6.2: "10 minor errors OR 2 major errors per 1000 words, which yields a Raw Quality Score of 99"
])
def test_raw_score_examples(penalty_points, raw_score):
    result = calculate(issues(minor=penalty_points), 1000, ScoringProfile(model=RAW))
    assert result.raw_score == pytest.approx(raw_score)
    assert result.score == pytest.approx(raw_score)


def test_ten_minor_or_two_major_errors_per_1000_words_are_the_same():
    """A.6.2: "10 minor errors OR 2 major errors per 1000 words … Raw Quality Score of 99"."""
    assert calculate(issues(major=2), 1000, ScoringProfile(model=RAW)).raw_score == pytest.approx(99.0)
    assert calculate(issues(minor=10), 1000, ScoringProfile(model=RAW)).raw_score == pytest.approx(99.0)


def test_raw_score_pass_interval():
    """A.5.1: with an acceptable "portion with errors" of 1, "any quality score between
    100–99 … produces the Pass rating"."""
    profile = ScoringProfile(model=RAW, acceptable_penalty_points=10)
    assert profile.raw_threshold == pytest.approx(99.0)
    assert calculate(issues(minor=10), 1000, profile).passed is True
    assert calculate(issues(minor=11), 1000, profile).passed is False
    assert calculate([], 1000, profile).score == 100.0


def test_calibrated_example_with_scaling_factor_0_75():
    """A.6.2: raw threshold 98 (20 points per 1000 words), calibrated passing interval 15
    (85 to 100): "The Scaling Parameter … will be 15/20=0.75". Raw score 98.44 means
    NPT = 15.6; 15.6 × 0.75 = 11.7; "the calibrated score will be 100-11.7=88.3"."""
    profile = ScoringProfile(model=CALIBRATED, acceptable_penalty_points=20, passing_threshold=85)
    assert profile.scaling_factor == pytest.approx(0.75)
    # 78 penalty points in 5,000 words: NPT 15.6.
    result = calculate(issues(minor=78), 5000, profile)
    assert result.normed_penalty_total == pytest.approx(15.6)
    assert result.raw_score == pytest.approx(98.44)
    assert result.calibrated_score == pytest.approx(88.3)
    assert result.score == pytest.approx(88.3)
    assert result.threshold == 85 and result.passed is True


def test_calibrated_example_with_scaling_factor_1():
    """Scoring page 2.5.2.3: "the Scaling factor is 1 … 100-90=10 … 10/10=1". Paper,
    Figure 10: "90 is defined as the Passing Threshold. This score is achieved if the
    Normed Penalty Total … is 10. If it is greater … the evaluation result is FAIL"."""
    profile = ScoringProfile(model=CALIBRATED, acceptable_penalty_points=10, passing_threshold=90)
    assert profile.scaling_factor == pytest.approx(1.0)
    at_limit = calculate(issues(minor=10), 1000, profile)
    assert at_limit.score == pytest.approx(90.0) and at_limit.passed is True
    over = calculate(issues(minor=11), 1000, profile)
    assert over.score == pytest.approx(89.0) and over.passed is False


def test_the_passing_threshold_stands_for_the_acceptable_penalty_points():
    """A.5.2: "the 85 Passing Threshold corresponds to the maximum acceptable number of
    errors on a Raw Score scale (… five penalty points for the legal translation or 28
    for the technical help example)"."""
    for app in (5, 28):
        profile = ScoringProfile(model=CALIBRATED, acceptable_penalty_points=app, passing_threshold=85)
        assert calculate(issues(minor=app), 1000, profile).score == pytest.approx(85.0)
        assert calculate(issues(minor=app), 1000, profile).passed is True
        assert calculate(issues(minor=app + 1), 1000, profile).passed is False


def test_raw_and_calibrated_models_agree_on_pass_and_fail():
    for points in range(0, 60, 3):
        raw = calculate(issues(minor=points), 800, ScoringProfile(model=RAW, acceptable_penalty_points=20))
        calibrated = calculate(issues(minor=points), 800,
                               ScoringProfile(model=CALIBRATED, acceptable_penalty_points=20, passing_threshold=85))
        assert raw.passed == calibrated.passed


# ── Which issues count, weights, and edge cases ───────────────────────

def test_neutral_issues_cost_nothing():
    assert calculate(issues(neutral=50), 1000).absolute_penalty_total == 0


def test_category_weight_falls_back_to_the_dimension_then_to_1():
    profile = ScoringProfile(weights={"accuracy": 2, "accuracy/omission": 3})
    assert profile.weight("accuracy/omission") == 3
    assert profile.weight("accuracy/addition") == 2
    assert profile.weight("style/awkward-style") == 1


def test_which_issues_are_counted():
    mixed = (issues(minor=1, status="accepted") + issues(minor=1, status="rejected")
             + issues(minor=1, status="fixed") + issues(minor=1, status="open")
             + issues(minor=1, status="open", origin="ai") + issues(minor=1, status="accepted", origin="ai"))
    assert calculate(mixed, 1000, ScoringProfile()).issue_count == 3            # accepted ×2, open human
    assert calculate(mixed, 1000, ScoringProfile(count_open=False)).issue_count == 2
    assert calculate(mixed, 1000, ScoringProfile(count_open_ai=True)).issue_count == 4


def test_no_words_means_no_score():
    result = calculate(issues(minor=3), 0)
    assert result.score is None and result.passed is None and result.absolute_penalty_total == 3


def test_configurable_multipliers():
    profile = ScoringProfile(model=RAW, multipliers={"minor": 1, "major": 10, "critical": 100})
    assert calculate(issues(major=1, critical=1), 1000, profile).absolute_penalty_total == 110
    assert profile.multiplier("neutral") == 0


def test_profile_round_trip_and_validation():
    profile = ScoringProfile(model=RAW, weights={"accuracy": 2}, acceptable_penalty_points=5)
    assert ScoringProfile.from_dict(profile.to_dict()) == profile
    for bad in ({"model": "other"}, {"acceptable_penalty_points": 0}, {"passing_threshold": 100},
                {"reference_word_count": 0}, {"multipliers": {"minor": -1}}):
        with pytest.raises(ValueError):
            ScoringProfile.from_dict(bad)


def test_word_count():
    segments = [SimpleNamespace(source="Click the <b>Save</b> button."), SimpleNamespace(source="你好世界"),
                SimpleNamespace(source="")]
    assert scoring.word_count(segments) == 4 + 4


def test_totals_per_category_and_severity():
    found = issues(minor=2, major=1, category="accuracy/omission") + issues(critical=1, category="terminology/wrong-term")
    result = calculate(found, 1000, ScoringProfile())
    assert [(t.category, t.penalty) for t in result.by_category] == [
        ("accuracy/omission", 7.0), ("terminology/wrong-term", 25.0)]
    assert result.by_severity == {"neutral": 0, "minor": 2, "major": 1, "critical": 1}
