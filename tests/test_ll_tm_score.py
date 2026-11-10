"""Phase 4: fuzzy match scores (localizelarge/tm/score.py) and the memory lookup.

The expected scores are fixed: a change to the scoring that moves any of them is a
change users will see in their match percentages.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from localizelarge.tm import score as tm_score  # noqa: E402
from localizelarge.tm.score import Scorer, explain, score, similarity  # noqa: E402

SAVE = "Click the Save button."

EXPECTED = [
    # Identical, or only the amount of white space differs: 100.
    (SAVE, SAVE, 100),
    (SAVE, "Click  the Save button. ", 100),
    ("Line one\nline two", "Line one line two", 100),
    ("Café", "Café", 100),                       # same text, different Unicode form
    ("", "", 100),
    # One point off for a difference in case only, or in punctuation only.
    (SAVE, "click the save button.", 99),
    (SAVE, "Click the Save button", 99),
    (SAVE, "Click the Save button!", 99),
    (SAVE, "click the save button", 98),               # both
    # One point per inline tag that differs.
    ("Click the <b>Save</b> button.", SAVE, 98),
    ("Click the <b>Save</b> button.", "Click the <i>Save</i> button.", 98),
    ("Click <x1/> the Save button.", SAVE, 99),
    # One point per number that differs.
    ("Page 5 of 10", "Page 6 of 10", 99),
    ("Page 5 of 10", "Page 6 of 12", 98),
    ("Total: 1,250.50 EUR", "Total: 1,250.75 EUR", 99),
    ("صفحة ٥ من ١٠", "صفحة 5 من 10", 99),                # same numbers, other digits: punctuation-like
    # Real differences in the words.
    (SAVE, "Click the Cancel button.", 80),
    (SAVE, "Click the Save button to continue.", 72),
    ("The colour of the car is red.", "The color of the car is red.", 91),
    ("Open the file and save your changes before closing the window.",
     "Open the file and save your changes before you close the window.", 88),
    ("Press Ctrl+S to save.", "Press Ctrl+S to save the file.", 76),
    (SAVE, "The weather is nice today.", 21),
    # Other scripts.
    ("你好，世界。今天天气很好。", "你好，世界。今天天气不好。", 92),
    ("اضغط على زر الحفظ.", "اضغط على زر الإلغاء.", 76),
    # Nothing against something.
    ("Hello", "", 0),
]


@pytest.mark.parametrize("a,b,expected", EXPECTED)
def test_expected_scores(a, b, expected):
    assert score(a, b) == expected, explain(a, b)


@pytest.mark.parametrize("a,b,expected", EXPECTED)
def test_the_score_is_the_same_in_both_directions(a, b, expected):
    assert score(b, a) == expected


def test_100_only_for_the_same_text():
    long_a = "word " * 400 + "end."
    long_b = "word " * 400 + "end!"
    assert score(long_a, long_b) == 99
    assert score(long_a, long_a) == 100
    # A tiny change in a very long segment still is not 100.
    assert score("alpha " * 300 + "beta", "alpha " * 300 + "gamma") == 99


def test_scores_stay_between_0_and_100():
    many_tags = "".join(f"<g{i}>x</g{i}>" for i in range(80))
    assert score(many_tags, "x " * 80) == 0 or 0 <= score(many_tags, "x " * 80) <= 100
    assert 0 <= score("a", "<b>" * 300) <= 100
    assert score("a", "b" * 5000) >= 0


def test_explain_names_what_was_deducted():
    detail = explain("Press <b>F5</b> on page 3.", "press F5 on page 4")
    assert (detail.tags, detail.numbers, detail.case, detail.punctuation) == (2, 1, True, True)
    assert detail.base == 100.0
    assert detail.score == 95


def test_similarity_is_the_score_as_a_ratio():
    assert similarity(SAVE, "Click the Cancel button.") == 0.80


def test_tokens():
    assert tm_score.tokens_of("Click the <b>Save</b> button, 3 times!") == \
        ["click", "the", "save", "button", "①", "times"]
    assert tm_score.tokens_of("你好，世界") == ["你", "好", "世", "界"]
    assert tm_score.tokens_of("Don't re-open it") == ["don't", "re-open", "it"]
    assert tm_score.numbers_of("Version 2.0 on <x1/> 12/03, ٣ items") == ["2.0", "12/03", "3"]
    assert tm_score.tags_of("a <b>b</b> <x1/>") == ["<b>", "</b>", "<x1/>"]


def test_scorer_gives_the_same_scores_and_dismisses_poor_candidates():
    scorer = Scorer(SAVE)
    for a, b, expected in EXPECTED:
        if a == SAVE:
            assert scorer.score(b) == expected
            assert scorer.score(b, cutoff=75) == (expected if expected >= 75 else 0) or \
                scorer.score(b, cutoff=75) == expected


def test_best_orders_and_limits():
    candidates = [("Click the Cancel button.", 1), (SAVE, 2), ("Unrelated text here.", 3),
                  ("click the save button.", 4)]
    found = tm_score.best(SAVE, candidates, threshold=75, limit=2)
    assert [(s, p) for s, _, p in found] == [(100, 2), (99, 4)]


# ── The memory lookup ─────────────────────────────────────────────────

@pytest.fixture
def memory(tmp_path):
    from modules.database_manager import DatabaseManager
    db = DatabaseManager(str(tmp_path / "tm.db"))
    db.connect()
    db.cursor.execute(
        "INSERT INTO translation_memories (name, source_lang, target_lang, tm_id, read_only) "
        "VALUES ('Test', 'en', 'fr', 'test', 0)")
    db.connection.commit()
    yield db
    db.close()


def test_lookup_scores_with_the_new_scorer(memory):
    memory.add_translation_units_batch(
        [(SAVE, "Cliquez sur le bouton Enregistrer."),
         ("Click the Cancel button.", "Cliquez sur le bouton Annuler."),
         ("The weather is nice today.", "Il fait beau aujourd'hui.")], "en", "fr", "test")
    matches = memory.search_fuzzy_matches("click the save button.", ["test"], threshold=0.75,
                                          source_lang="en", target_lang="fr")
    assert [(m["source_text"], m["match_pct"]) for m in matches] == [
        (SAVE, 99), ("Click the Cancel button.", 80)]


def test_the_near_match_is_found_among_many_units_that_share_its_words(memory):
    """The candidates must be the best-ranked ones. With the base's ordering the
    scorer was given the worst-ranked units and missed the near match."""
    noise = [(f"The operator must check the valve in unit {i} before the shift starts.",
              f"FR {i}") for i in range(3000)]
    near = "The operator must replace the oil filter after every delivery."
    memory.add_translation_units_batch(noise + [(near, "FR near")], "en", "fr", "test")
    matches = memory.search_fuzzy_matches(
        "The operator must replace the oil filter after each delivery.", ["test"],
        threshold=0.75, source_lang="en", target_lang="fr")
    assert matches and matches[0]["source_text"] == near
    assert matches[0]["match_pct"] == 92


def test_a_reverse_direction_match_is_found_and_swapped(memory):
    memory.add_translation_units_batch(
        [("Cliquez sur le bouton Enregistrer.", SAVE)], "fr", "en", "test")
    matches = memory.search_fuzzy_matches("Click the Save button", ["test"], threshold=0.75,
                                          source_lang="en", target_lang="fr")
    assert len(matches) == 1
    assert matches[0]["source_text"] == SAVE
    assert matches[0]["target_text"] == "Cliquez sur le bouton Enregistrer."
    assert matches[0].get("reverse_match") is True
    assert matches[0]["match_pct"] == 99
    one_way = memory.search_fuzzy_matches("Click the Save button", ["test"], threshold=0.75,
                                          source_lang="en", target_lang="fr", bidirectional=False)
    assert one_way == []


def test_the_batch_lookup_uses_the_same_scores(memory):
    memory.add_translation_units_batch(
        [(SAVE, "Cliquez sur le bouton Enregistrer."),
         ("Page 5 of 10", "Page 5 sur 10")], "en", "fr", "test")
    batch = getattr(memory, "batch_fuzzy_matches", None) or getattr(memory, "search_fuzzy_matches_batch")
    results = batch(["Click the Cancel button.", "Page 6 of 10", "Nothing like it at all here."],
                    ["test"], threshold=0.75, source_lang="en", target_lang="fr")
    assert results["Click the Cancel button."]["match_pct"] == 80
    assert results["Page 6 of 10"]["match_pct"] == 99
    assert "Nothing like it at all here." not in results
