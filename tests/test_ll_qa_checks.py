"""Phase 5a: the QA checks (localizelarge/quality/checks) and the issue model."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from localizelarge.mqm import typology  # noqa: E402
from localizelarge.quality import engine  # noqa: E402
from localizelarge.quality.checks import ALL_CHECKS, Context  # noqa: E402
from localizelarge.quality.checks.tokens import _readings, numbers_in, placeholders_in  # noqa: E402
from localizelarge.quality.model import Issue, IssueList, make_issue, plain_text, text_hash  # noqa: E402


def seg(source, target, id=1, **extra):
    return SimpleNamespace(id=id, source=source, target=target, **extra)


def run(check_id, source, target, ctx=None, **extra):
    """The messages of one check on one segment."""
    ctx = ctx or Context("en", "fr")
    return [i.message for i in engine.run_segment(seg(source, target, **extra), ctx, only=[check_id])]


def found(check_id, source, target, ctx=None, **extra):
    return bool(run(check_id, source, target, ctx, **extra))


# ── The set of checks ─────────────────────────────────────────────────

def test_every_planned_check_exists_once_with_a_category_from_mqm_core():
    ids = [c.id for c in ALL_CHECKS]
    assert ids == ["qa.empty", "qa.same_as_source", "qa.tags", "qa.numbers", "qa.placeholders",
                   "qa.urls_emails", "qa.whitespace", "qa.end_punctuation", "qa.brackets_quotes",
                   "qa.repeated_word", "qa.inconsistent_target", "qa.inconsistent_source",
                   "qa.length", "qa.capitalization", "qa.spelling", "qa.regex"]
    for check in ALL_CHECKS:
        assert check.name and check.severity in ("neutral", "minor", "major", "critical")
        assert typology.get(check.category) is not None, (check.id, check.category)


# ── qa.empty, qa.same_as_source ───────────────────────────────────────

def test_empty():
    assert found("qa.empty", "Save the file.", "")
    assert found("qa.empty", "Save the file.", "  ")
    assert found("qa.empty", "Save", "<b></b>")
    assert not found("qa.empty", "Save the file.", "Enregistrez le fichier.")
    assert not found("qa.empty", "", "")


def test_same_as_source():
    assert found("qa.same_as_source", "Save the file.", "Save the file.")
    assert found("qa.same_as_source", "Save the <b>file</b>.", "Save the file.")
    for untranslatable in ("12345", "3.5 × 4", "https://example.com/a", "info@example.com",
                           "OK", "USB", "V2", "MAX_SIZE", "42 %"):
        assert not found("qa.same_as_source", untranslatable, untranslatable), untranslatable
    assert not found("qa.same_as_source", "Save the file.", "Enregistrez le fichier.")
    # The same language on both sides (en-US → en-GB): nothing to say.
    assert not found("qa.same_as_source", "Save the file.", "Save the file.", Context("en-US", "en-GB"))


# ── qa.tags ───────────────────────────────────────────────────────────

def test_tags():
    assert not found("qa.tags", "Click <b>Save</b>.", "Cliquez sur <b>Enregistrer</b>.")
    assert run("qa.tags", "Click <b>Save</b>.", "Cliquez sur Enregistrer.") == \
        ["Missing in the target: <b> </b>"]
    assert run("qa.tags", "Click Save.", "Cliquez <i>ici</i>.") == \
        ["In the target but not in the source: <i> </i>"]
    # Moved pairs are fine; a closing tag before its opening tag is not.
    assert not found("qa.tags", "<b>A</b> and <i>B</i>", "<i>B</i> et <b>A</b>")
    assert found("qa.tags", "Click <b>Save</b>.", "Cliquez sur </b>Enregistrer<b>.")
    assert found("qa.tags", "<b><i>A</i></b>", "<b><i>A</b></i>")
    assert not found("qa.tags", "Line<x1/>two <g1>a</g1>", "<g1>a</g1> deux<x1/>ligne")


# ── qa.numbers ────────────────────────────────────────────────────────

@pytest.mark.parametrize("source,target", [
    ("Page 5 of 10", "Page 5 sur 10"),
    ("1,000.5 kg", "1.000,5 kg"),               # the same number, other locale
    ("1,000.5 kg", "1 000,5 kg"),               # French: space as group separator
    ("1,234,567 items", "1.234.567 Elemente"),
    ("Add 3.5 ml", "Ajoutez 3,5 ml"),
    ("In 2024 we sold 15 units", "في عام ٢٠٢٤ بعنا ١٥ وحدة"),       # Arabic-Indic digits
    ("In 2024 we sold 15 units", "در سال ۲۰۲۴ ما ۱۵ واحد فروختیم"),  # Persian digits
    ("3.5 kg", "٣٫٥ كجم"),                      # Arabic decimal separator
    ("12,500 users", "١٢٬٥٠٠ مستخدم"),          # Arabic thousands separator
    ("Step 2: press 1", "Appuyez sur 1 à l'étape 2"),   # order may change
    ("No numbers here", "Pas de chiffres ici"),
    ("Version 2.0", "Version 2.0"),
    ("−5 °C", "-5 °C"),
])
def test_numbers_that_are_the_same(source, target):
    assert run("qa.numbers", source, target) == []


def test_numbers_that_differ():
    assert run("qa.numbers", "Page 5 of 10", "Page 6 sur 10") == [
        "The number 5 of the source is not in the target.", "The number 6 is not in the source."]
    assert run("qa.numbers", "Take 200 mg", "Prenez 20 mg")[0].startswith("The number 200")
    assert found("qa.numbers", "1,000.5 kg", "1.000,6 kg")
    assert found("qa.numbers", "15 units", "١٦ وحدة")
    assert run("qa.numbers", "Wait.", "Attendez 5 minutes.") == ["The number 5 is not in the source."]
    assert run("qa.numbers", "Press 1 twice: 1", "Appuyez sur 1") == [
        "The number 1 of the source is not in the target."]
    # A number inside a tag is not text.
    assert not found("qa.numbers", "<g1>Hello</g1>", "<g1>Bonjour</g1>")


def test_number_readings_and_positions():
    assert _readings("1,000.5") & _readings("1.000,5") == {"1000.5"}
    assert _readings("1,234") == {"1234", "1.234"}
    assert _readings("٣٫٥") == {"3.5"}
    assert not (_readings("1.5") & _readings("15"))
    issue = engine.run_segment(seg("Wait.", "Attendez ٥ minutes."), Context("en", "ar"), only=["qa.numbers"])[0]
    assert plain_text("Attendez ٥ minutes.")[issue.start:issue.end] == "٥"
    assert [n for n, _, _ in numbers_in("a 1,5 b 2024 c")] == ["1,5", "2024"]


# ── qa.placeholders ───────────────────────────────────────────────────

def test_placeholders_are_recognised():
    assert placeholders_in("{0} %s %1$s %d %.2f {{name}} ${user} %(count)d {name} %@") == \
        ["{0}", "%s", "%1$s", "%d", "%.2f", "{{name}}", "${user}", "%(count)d", "{name}", "%@"]
    assert placeholders_in("{count, plural, one {# file} other {# files}}")[0] == "{count, plural"
    assert placeholders_in("100% sure, 50 % off") == []


def test_placeholders():
    assert not found("qa.placeholders", "Hello {0}, you have %d files", "Bonjour {0}, vous avez %d fichiers")
    assert not found("qa.placeholders", "%1$s of %2$s", "%2$s من %1$s")
    assert run("qa.placeholders", "Hello {0}", "Bonjour") == [
        "The placeholder {0} of the source is not in the target."]
    assert run("qa.placeholders", "Hello {{name}}", "Bonjour {{nom}}") == [
        "The placeholder {{name}} of the source is not in the target.",
        "The placeholder {{nom}} is not in the source."]
    assert not found("qa.placeholders",
                     "{count, plural, one {# file} other {# files}}",
                     "{count, plural, one {# fichier} other {# fichiers}}")
    assert found("qa.placeholders", "{count, plural, one {# file} other {# files}}", "{count} fichiers")


# ── qa.urls_emails ────────────────────────────────────────────────────

def test_urls_and_emails():
    assert not found("qa.urls_emails", "See https://example.com/a?b=1.", "Voir https://example.com/a?b=1.")
    assert not found("qa.urls_emails", "Write to help@example.com", "اكتب إلى help@example.com")
    assert found("qa.urls_emails", "See https://example.com/en", "Voir https://example.com/fr")
    assert found("qa.urls_emails", "Write to help@example.com", "Écrivez à aide@example.com")
    assert run("qa.urls_emails", "See www.example.com", "Voir le site")[0].startswith("The URL www.example.com")


# ── qa.whitespace ─────────────────────────────────────────────────────

def test_whitespace():
    assert not found("qa.whitespace", "Save the file.", "Enregistrez le fichier.")
    assert "starts with a space" in run("qa.whitespace", "Save", " Enregistrer")[0]
    assert "ends with a space" in run("qa.whitespace", "Save", "Enregistrer ")[0]
    assert found("qa.whitespace", "Save ", "Enregistrer")
    assert run("qa.whitespace", "Save the file", "Enregistrez  le fichier") == ["Two or more spaces in a row."]
    assert not found("qa.whitespace", "Save  the file", "Enregistrez  le fichier")   # the source has it too


# ── qa.end_punctuation ────────────────────────────────────────────────

@pytest.mark.parametrize("source,target,target_lang", [
    ("Is it ready?", "هل هو جاهز؟", "ar"),
    ("First, second;", "أولا، ثانيا؛", "ar"),
    ("One, two,", "واحد، اثنان،", "ar"),
    ("It is ready.", "准备好了。", "zh"),
    ("Is it ready?", "准备好了吗？", "zh"),
    ("Done!", "完了！", "ja"),
    ("He said \"Stop.\"", "Il a dit « Stop. »", "fr"),
    ("Wait...", "Attendez…", "fr"),
    ("Save the file.", "บันทึกไฟล์", "th"),        # Thai ends without a full stop
    ("Title", "Titre", "fr"),
])
def test_end_punctuation_that_matches(source, target, target_lang):
    assert run("qa.end_punctuation", source, target, Context("en", target_lang)) == []


def test_end_punctuation_that_differs():
    assert run("qa.end_punctuation", "Is it ready?", "هل هو جاهز.", Context("en", "ar")) == [
        "The source ends with a question mark, the target with a full stop."]
    assert run("qa.end_punctuation", "It is ready.", "C'est prêt") == [
        "The source ends with a full stop, the target with none."]
    assert run("qa.end_punctuation", "Title", "Titre.") == [
        "The target ends with a full stop, the source with none."]


# ── qa.brackets_quotes, qa.repeated_word ──────────────────────────────

def test_brackets_and_quotes():
    assert not found("qa.brackets_quotes", "Press (OK) now", "Appuyez sur (OK)")
    assert run("qa.brackets_quotes", "Press (OK) now", "Appuyez sur (OK") == ["Unpaired ( ) in the target."]
    assert found("qa.brackets_quotes", 'Say "yes"', 'Dites "oui')
    assert found("qa.brackets_quotes", "Say «yes»", "قل «نعم")
    assert not found("qa.brackets_quotes", "Say “yes”", "Sagen Sie „ja“")       # German pair
    assert found("qa.brackets_quotes", "Say “yes”", "Sagen Sie „ja")
    assert not found("qa.brackets_quotes", "a) first", "a) premier")            # the source is unpaired too
    assert not found("qa.brackets_quotes", "It's John's", "C'est à John")       # apostrophes are not quotes


def test_repeated_word():
    assert run("qa.repeated_word", "Check the valve.", "Vérifiez la la vanne.") == [
        "The word “la” is written twice in a row."]
    assert found("qa.repeated_word", "Check it", "افحص من من الصمام")
    assert not found("qa.repeated_word", "Check the valve.", "Vérifiez la vanne.")
    assert not found("qa.repeated_word", "Bye bye", "Bye bye")                  # the source repeats it
    assert not found("qa.repeated_word", "10 10 10", "10 10 10")


# ── qa.length, qa.capitalization ──────────────────────────────────────

def test_length():
    source = "Switch off the power supply before opening the housing."
    assert not found("qa.length", source, "Coupez l'alimentation avant d'ouvrir le boîtier.")
    assert "times as long" in run("qa.length", source, source * 3)[0]
    assert "only" in run("qa.length", source, "Coupez.")[0]
    assert not found("qa.length", "OK", "D'accord, c'est entendu")              # too short to judge
    assert run("qa.length", "Save", "Enregistrer", max_length=8) == [
        "The target has 11 characters; the file allows 8."]
    wide = Context("en", "fr", settings={"qa.length": {"max_ratio": 5.0}})
    assert not found("qa.length", source, source * 3, wide)


def test_capitalization():
    assert not found("qa.capitalization", "Save the file", "Enregistrez le fichier")
    assert found("qa.capitalization", "Save the file", "enregistrez le fichier")
    assert found("qa.capitalization", "save the file", "Enregistrez le fichier")
    assert not found("qa.capitalization", "save the file", "Datei speichern", Context("en", "de"))
    assert not found("qa.capitalization", "Save the file", "احفظ الملف", Context("en", "ar"))   # no case
    assert not found("qa.capitalization", "Save", "保存", Context("en", "zh"))
    assert not found("qa.capitalization", "5 files", "cinq fichiers")
    assert found("qa.capitalization", "<b>Save</b> it", "<b>enregistrez</b>-le")


# ── qa.spelling, qa.regex ─────────────────────────────────────────────

def test_spelling_uses_the_dictionary_it_is_given():
    known = {"enregistrez", "le", "fichier", "dans"}
    ctx = Context("en", "fr", spell_check=lambda word: word.lower() in known)
    assert run("qa.spelling", "Save the file in FlowMax", "Enregistrez le fichiier dans FlowMax", ctx) == [
        "“fichiier” is not in the dictionary."]     # FlowMax is in the source: a name
    assert run("qa.spelling", "Save", "Enregistrez", Context("en", "fr")) == []   # no dictionary: no findings
    issue = engine.run_segment(seg("Save", "le <b>fichiier</b>"), ctx, only=["qa.spelling"])[0]
    assert plain_text("le <b>fichiier</b>")[issue.start:issue.end] == "fichiier"


def test_saved_regex_checks_run_through_the_engine():
    from modules.find_replace_qt import FindReplaceOperation
    check = FindReplaceOperation(find_text=r" +[.,](?=\s|$)", search_in="target", use_regex=True,
                                 check_only=True, note="Space before a full stop")
    segments = [seg("The pump runs.", "La pompe tourne .", id=1), seg("Done.", "Fini.", id=2)]
    issues = engine.run_project(segments, Context("en", "fr", segments, regex_checks=[check]), only=["qa.regex"])
    assert [(i.segment_id, i.rule_id, i.origin) for i in issues] == [(1, "qa.regex", "qa")]
    assert issues[0].message.startswith("Space before a full stop")
    assert plain_text(segments[0].target)[issues[0].start:issues[0].end] == " ."


# ── Project-wide checks ───────────────────────────────────────────────

def test_inconsistent_target_and_source():
    segments = [seg("Save", "Enregistrer", 1), seg("Save", "Sauvegarder", 2), seg("Save", "Enregistrer", 3),
                seg("Open", "Ouvrir", 4), seg("Start", "Ouvrir", 5), seg("Close", "", 6)]
    issues = engine.run_project(segments, Context("en", "fr", segments),
                                only=["qa.inconsistent_target", "qa.inconsistent_source"])
    by_rule = {}
    for issue in issues:
        by_rule.setdefault(issue.rule_id, []).append(issue.segment_id)
    assert by_rule == {"qa.inconsistent_target": [1, 2, 3], "qa.inconsistent_source": [4, 5]}
    message = next(i.message for i in issues if i.segment_id == 1)
    assert "2: Sauvegarder" in message
    # They do not run on a single segment.
    assert engine.run_segment(segments[0], Context("en", "fr", segments),
                              only=["qa.inconsistent_target"]) == []


# ── The engine ────────────────────────────────────────────────────────

def test_untranslated_segments_get_only_the_empty_finding():
    issues = engine.run_project([seg("Save {0} files (now)?", "")], Context("en", "fr"))
    assert [i.rule_id for i in issues] == ["qa.empty"]


def test_a_clean_translation_has_no_findings():
    segments = [seg("Click <b>Save</b> to store 3 files.", "Cliquez sur <b>Enregistrer</b> pour stocker 3 fichiers."),
                seg("Is it ready?", "Est-ce prêt ?", 2)]
    assert engine.run_project(segments, Context("en", "fr", segments)) == []


def test_settings_can_switch_a_check_off_and_change_its_severity_and_category():
    segment = seg("Hello {0}", "Bonjour")
    off = Context("en", "fr", settings={"qa.placeholders": {"enabled": False}})
    assert engine.run_segment(segment, off, only=["qa.placeholders"]) == []
    changed = Context("en", "fr", settings={"qa.placeholders": {"severity": "critical",
                                                              "category": "accuracy/omission"}})
    issue = engine.run_segment(segment, changed, only=["qa.placeholders"])[0]
    assert (issue.severity, issue.category) == ("critical", "accuracy/omission")


def test_findings_are_issues_with_origin_qa_and_the_hash_of_the_text():
    segment = seg("Page 5", "Page <b>6</b>", id=7)
    issue = next(i for i in engine.run_segment(segment, Context("en", "fr")) if i.start is not None)
    assert (issue.origin, issue.rule_id, issue.segment_id, issue.status) == ("qa", "qa.numbers", 7, "open")
    assert issue.text_hash == text_hash("Page <b>6</b>")
    assert issue.quoted(segment.target) == "6"
    assert not issue.is_stale(segment.target)
    assert issue.is_stale("Page 7") and issue.quoted("Page 7") == ""


# ── The issue model ───────────────────────────────────────────────────

def test_issue_round_trip_and_validation():
    issue = make_issue(seg("Source text", "Target <i>text</i>", id=3), origin="human", rule_id="mqm",
                       category="accuracy/mistranslation", severity="major", message="Wrong",
                       start=7, end=11, comment="c", suggestion="s", author="Tester")
    data = issue.to_dict()
    assert list(data)[0] == "id" and data["created_at"].endswith("Z")
    assert Issue.from_dict(data) == issue
    assert Issue.from_dict({**data, "unknown_field": 1}) == issue
    for bad in ({"origin": "robot"}, {"severity": "huge"}, {"side": "middle"}, {"status": "done"},
                {"start": 5, "end": None}, {"start": 9, "end": 2}):
        with pytest.raises(ValueError):
            Issue.from_dict({**data, **bad})


def test_plain_text_removes_tags_only():
    assert plain_text("a <b>b</b> {0} <x1/> 1 < 2 > 0") == "a b {0}  1 < 2 > 0"


def test_a_new_qa_run_keeps_decisions_and_never_touches_human_issues():
    segment = seg("Page 5", "Page 6", id=1)
    ctx = Context("en", "fr")
    issues = IssueList()
    human = issues.add(make_issue(segment, origin="human", rule_id="mqm", category="style/awkward-style",
                                  severity="minor", message="Awkward"))
    issues.replace_automatic(engine.run_segment(segment, ctx))
    first = [i for i in issues if i.origin == "qa"]
    assert len(first) == 2
    first[0].status, first[0].comment = "rejected", "Intended"
    kept_id = first[0].id

    issues.replace_automatic(engine.run_segment(segment, ctx))
    again = {i.id: i for i in issues if i.origin == "qa"}
    assert len(again) == 2 and again[kept_id].status == "rejected" and again[kept_id].comment == "Intended"

    segment.target = "Feuille 5"                    # fixed: the findings go away
    issues.replace_automatic(engine.run_segment(segment, ctx), segment_ids=[1])
    assert [i.id for i in issues] == [human.id]
    assert IssueList.from_list(issues.to_list()).all() == issues.all()
    assert IssueList.from_list([{"nonsense": True}]).all() == []
