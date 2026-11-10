"""Phase 5b: glossary checks (localizelarge/quality/glossary_check.py)."""
import os
import random
import sys
import time
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from localizelarge.mqm import typology  # noqa: E402
from localizelarge.quality import glossary_check as gc  # noqa: E402
from localizelarge.quality.glossary_check import Glossary, GlossaryEntry  # noqa: E402
from localizelarge.quality.model import plain_text  # noqa: E402


def seg(source, target, id=1):
    return SimpleNamespace(id=id, source=source, target=target)


def check(source, target, entries, source_lang="en", target_lang="ar", settings=None):
    glossary = Glossary(entries, source_lang, target_lang)
    return gc.check_segment(seg(source, target), glossary, settings)


PUMP = GlossaryEntry("pump", targets=["مضخة"], forbidden=["طلمبة"])
GAUGE = GlossaryEntry("pressure gauge", targets=["مقياس الضغط", "مانومتر"], source_variants=["manometer"])


def rules(issues):
    return [(i.rule_id, i.severity) for i in issues]


def test_defaults_use_categories_from_mqm_core():
    for rule, values in gc.DEFAULTS.items():
        assert typology.get(values["category"]) is not None, rule
    assert gc.DEFAULTS[gc.REQUIRED]["category"] == "terminology/wrong-term"


# ── glossary.required ─────────────────────────────────────────────────

def test_the_approved_term_is_used():
    assert check("Check the pump.", "افحص مضخة الماء.", [PUMP]) == []
    assert check("Read the pressure gauge.", "اقرأ مقياس الضغط.", [GAUGE]) == []
    assert check("Read the pressure gauge.", "اقرأ مانومتر.", [GAUGE]) == []          # a variant
    assert check("Read the manometer.", "اقرأ مقياس الضغط.", [GAUGE]) == []            # source variant


def test_the_approved_term_is_missing():
    (issue,) = check("Check the pump.", "افحص الجهاز.", [PUMP])
    assert (issue.rule_id, issue.origin, issue.severity, issue.category) == \
        ("glossary.required", "glossary", "major", "terminology/wrong-term")
    assert "“pump”" in issue.message and "“مضخة”" in issue.message
    assert issue.suggestion == "مضخة" and issue.start is None


def test_no_source_term_no_finding_and_untranslated_segments_are_skipped():
    assert check("Check the valve.", "افحص الصمام.", [PUMP]) == []
    assert check("Check the pump.", "", [PUMP]) == []
    assert check("Check the pump.", "افحص", []) == []


def test_whole_words_only():
    assert check("Check the pumps.", "افحص الأجهزة.", [PUMP]) == []                    # "pumps" is another word
    assert check("The pumping station", "محطة", [PUMP]) == []
    english = GlossaryEntry("valve", targets=["vanne"])
    assert rules(check("Open the valve.", "Ouvrez la vannerie.", [english], "en", "fr")) == \
        [("glossary.required", "major")]


def test_case_folding_and_case_sensitive_terms():
    plain = GlossaryEntry("user guide", targets=["Guide de l'utilisateur"])
    assert check("Read the User Guide.", "Lisez le guide de l'utilisateur.", [plain], "en", "fr") == []
    strict = GlossaryEntry("FlowMax", targets=["FlowMax"], case_sensitive=True)
    assert check("Start FlowMax.", "Démarrez FlowMax.", [strict], "en", "fr") == []
    assert rules(check("Start FlowMax.", "Démarrez flowmax.", [strict], "en", "fr")) == \
        [("glossary.required", "major")]
    assert check("Start flowmax.", "Démarrez autre chose.", [strict], "en", "fr") == []   # not the term


def test_unicode_forms_are_the_same_text():
    entry = GlossaryEntry("coffee", targets=["café"])
    assert check("Hot coffee", "Café chaud", [entry], "en", "fr") == []


def test_a_longer_term_wins_over_a_term_inside_it():
    gauge = GlossaryEntry("gauge", targets=["مقياس"])
    issues = check("Read the pressure gauge.", "اقرأ المؤشر.", [GAUGE, gauge])
    assert len(issues) == 1 and "pressure gauge" in issues[0].message


# ── Arabic matching ───────────────────────────────────────────────────

@pytest.mark.parametrize("target", [
    "افحص المضخة.",          # the article
    "افحص والمضخة.",         # و + ال
    "اعمل بالمضخة.",         # ب + ال
    "قطع غيار للمضخة.",      # ل + ال → لل
    "فبالمضخة نبدأ.",        # ف + ب + ال
    "كمضخة صغيرة.",          # ك
    "افحص مِضَخَّة الماء.",     # diacritics
    "افحص مضـــخة الماء.",    # tatweel
])
def test_arabic_forms_count_as_possible_not_missing(target):
    (issue,) = check("Check the pump.", target, [PUMP])
    assert (issue.rule_id, issue.severity) == ("glossary.required", "minor")
    assert "possibly" in issue.message
    assert issue.start is not None and plain_text(target)[issue.start:issue.end]


def test_alef_forms_are_unified():
    entry = GlossaryEntry("tool", targets=["أداة"])
    assert rules(check("Use the tool.", "استخدم اداة.", [entry])) == [("glossary.required", "minor")]
    assert check("Use the tool.", "استخدم أداة.", [entry]) == []
    assert gc.arabic_normal("إِعْدَادَات آمِنَة ٱلْ") == "اعدادات امنة ال"


def test_possible_matches_can_be_switched_off():
    quiet = {"glossary.required": {"report_possible": False}}
    assert check("Check the pump.", "افحص المضخة.", [PUMP], settings=quiet) == []
    assert rules(check("Check the pump.", "افحص الجهاز.", [PUMP], settings=quiet)) == \
        [("glossary.required", "major")]


def test_arabic_prefixes_are_not_used_for_other_languages():
    entry = GlossaryEntry("book", targets=["livre"])
    assert rules(check("The book", "Le balivre", [entry], "en", "fr")) == [("glossary.required", "major")]


def test_an_arabic_source_term_is_found_with_its_prefixes():
    entry = GlossaryEntry("مضخة", targets=["pump"])
    assert rules(check("افحص المضخة.", "Check the device.", [entry], "ar", "en")) == \
        [("glossary.required", "major")]
    assert check("افحص بالمضخة.", "Check the pump.", [entry], "ar", "en") == []


def test_arabic_stems():
    assert gc.arabic_stems("والمضخة") >= {"المضخة", "مضخة"}
    assert gc.arabic_stems("للمضخة") >= {"مضخة"}
    assert gc.arabic_stems("مضخة") == {"مضخة"}


# ── glossary.forbidden ────────────────────────────────────────────────

def test_forbidden_term():
    target = "افحص طلمبة الماء."
    issues = check("Check the pump.", target, [PUMP])
    forbidden = next(i for i in issues if i.rule_id == "glossary.forbidden")
    assert forbidden.severity == "major"
    assert forbidden.category == "terminology/inconsistent-with-terminology-resource"
    assert plain_text(target)[forbidden.start:forbidden.end] == "طلمبة"
    assert forbidden.suggestion == "مضخة"
    # The approved term is missing too.
    assert ("glossary.required", "major") in rules(issues)


def test_forbidden_term_with_the_approved_term_also_present():
    issues = check("Check the pump.", "افحص مضخة (طلمبة).", [PUMP])
    assert rules(issues) == [("glossary.forbidden", "major")]


def test_a_forbidden_only_entry():
    entry = GlossaryEntry("e-mail", forbidden=["mél"])
    assert rules(check("Send an e-mail.", "Envoyez un mél.", [entry], "en", "fr")) == \
        [("glossary.forbidden", "major")]
    assert check("Send an e-mail.", "Envoyez un courriel.", [entry], "en", "fr") == []


def test_rules_can_be_switched_off_and_their_severity_changed():
    off = {"glossary.forbidden": {"enabled": False}, "glossary.required": {"enabled": False}}
    assert check("Check the pump.", "افحص طلمبة.", [PUMP], settings=off) == []
    critical = {"glossary.required": {"severity": "critical"}}
    assert rules(check("Check the pump.", "افحص الجهاز.", [PUMP], settings=critical)) == \
        [("glossary.required", "critical")]


# ── glossary.inconsistent ─────────────────────────────────────────────

def test_inconsistent_variants_across_the_project():
    segments = [seg("Read the pressure gauge.", "اقرأ مقياس الضغط.", 1),
                seg("Clean the pressure gauge.", "نظف مقياس الضغط.", 2),
                seg("Replace the pressure gauge.", "استبدل مانومتر.", 3),
                seg("Check the pump.", "افحص مضخة.", 4)]
    glossary = Glossary([GAUGE, PUMP], "en", "ar")
    issues = gc.check_project(segments, glossary)
    assert [(i.segment_id, i.rule_id, i.severity) for i in issues] == [(3, "glossary.inconsistent", "minor")]
    assert "“مانومتر”" in issues[0].message and "“مقياس الضغط”" in issues[0].message
    assert issues[0].suggestion == "مقياس الضغط"
    assert plain_text(segments[2].target)[issues[0].start:issues[0].end] == "مانومتر"
    # Consistent use gives nothing.
    assert gc.check_project(segments[:2], glossary) == []
    assert [i.rule_id for i in gc.run(segments, glossary)] == ["glossary.inconsistent"]


# ── No-space scripts, tags ────────────────────────────────────────────

def test_chinese_and_japanese_terms_are_found_as_strings():
    entry = GlossaryEntry("pump", targets=["泵"], forbidden=["抽水机"])
    assert check("Check the pump.", "检查泵的状态。", [entry], "en", "zh") == []
    assert rules(check("Check the pump.", "检查设备。", [entry], "en", "zh")) == [("glossary.required", "major")]
    assert ("glossary.forbidden", "major") in rules(check("Check the pump.", "检查抽水机。", [entry], "en", "zh"))
    chinese_source = GlossaryEntry("压力表", targets=["pressure gauge"])
    assert rules(check("请检查压力表。", "Check the device.", [chinese_source], "zh", "en")) == \
        [("glossary.required", "major")]


def test_tags_inside_the_text_do_not_hide_a_term():
    assert check("Check the <b>pump</b>.", "افحص <b>مضخة</b> الماء.", [PUMP]) == []
    target = "افحص <b>طلمبة</b>."
    forbidden = next(i for i in check("Check the <b>pump</b>.", target, [PUMP]) if i.rule_id == "glossary.forbidden")
    assert plain_text(target)[forbidden.start:forbidden.end] == "طلمبة"


# ── From a termbase, and speed ────────────────────────────────────────

def test_entries_from_a_termbase(tmp_path):
    from localizelarge.terms import store, tbx
    from modules.database_manager import DatabaseManager
    from modules.termbase_manager import TermbaseManager
    db = DatabaseManager(db_path=str(tmp_path / "t.db"), log_callback=lambda *_: None)
    db.connect()
    try:
        manager = TermbaseManager(db, lambda *_: None)
        termbase_id = manager.create_termbase("Pumps", "en", "ar")
        fixture = os.path.join(os.path.dirname(__file__), "fixtures", "terms", "sample.tbx")
        store.import_entries(manager, termbase_id, tbx.read_tbx(fixture, "en", "ar").entries, "en", "ar")
        entries = gc.entries_from_termbase(manager, termbase_id, "Pumps")
        pump = next(e for e in entries if e.source == "pump")
        assert pump.targets == ["مضخة"] and pump.forbidden == ["طلمبة"] and pump.glossary == "Pumps"
        gauge = next(e for e in entries if e.source == "pressure gauge")
        assert gauge.targets == ["مقياس الضغط", "مانومتر"] and gauge.source_variants == ["manometer"]
        assert ("glossary.forbidden", "major") in rules(check("Check the pump.", "افحص طلمبة.", entries))
    finally:
        db.close()


def test_50000_entries_check_1000_segments_in_under_a_second():
    rng = random.Random(7)
    letters = "abcdefghijklmnopqrstuvwxyz"

    def term(number):
        """A made-up word that is different for every number."""
        word = ""
        while True:
            word += letters[number % 26]
            number //= 26
            if not number:
                return "q" + word

    filler = ["the", "operator", "checks", "and", "cleans", "every", "week", "before", "starting",
              "machine", "with", "care", "after", "use", "when", "needed"]
    entries = [GlossaryEntry(f"{term(i)} {term(i + 7)}" if i % 3 else term(i),
                             targets=[term(100_000 + i), term(200_000 + i)], forbidden=[term(300_000 + i)])
               for i in range(50_000)]
    segments = []
    for i in range(1000):
        first, second = rng.sample(entries, 2)
        words = rng.sample(filler, 8)
        source = f"{' '.join(words[:4])} {first.source} {' '.join(words[4:])} {second.source}."
        # The first term is translated with its approved term, the second is not.
        target = f"{' '.join(words[:4])} {first.targets[0]} {' '.join(words[4:])} autre."
        segments.append(seg(source, target, i + 1))

    started = time.perf_counter()
    glossary = Glossary(entries, "en", "fr")
    built = time.perf_counter() - started
    started = time.perf_counter()
    issues = gc.run(segments, glossary)
    elapsed = time.perf_counter() - started
    print(f"index built in {built:.2f} s; 1000 segments checked in {elapsed:.3f} s; {len(issues)} findings")
    assert sum(1 for i in issues if i.rule_id == "glossary.required") == 1000
    assert elapsed < 1.0
