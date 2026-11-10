"""Phase 5d: AI pre-annotation. The model is a stand-in; nothing leaves the computer."""
import json
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from localizelarge.mqm import ai_annotate as ai  # noqa: E402
from localizelarge.mqm import scoring  # noqa: E402
from localizelarge.quality.model import plain_text  # noqa: E402


def seg(id, source, target):
    return SimpleNamespace(id=id, source=source, target=target)


SEGMENT = seg(1, "Take <b>200 mg</b> twice a day.", "Prenez <b>20 mg</b> une fois par jour.")
GOOD = {"side": "target", "quote": "20 mg", "category": "accuracy/mistranslation", "severity": "critical",
        "explanation": "The dose is 200 mg in the source.", "suggestion": "200 mg"}


def reply(*items):
    return json.dumps(list(items), ensure_ascii=False)


# ── The prompt ────────────────────────────────────────────────────────

def test_prompt_has_the_texts_without_tags_the_categories_and_the_glossary():
    paths = ai.category_paths(["accuracy", "terminology/wrong-term"])
    assert "accuracy/omission" in paths and "terminology/wrong-term" in paths
    assert "style/awkward-style" not in paths and "accuracy" not in paths
    prompt = ai.build_prompt(SEGMENT.source, SEGMENT.target, "en", "fr", paths, [("dose", ["dose", "posologie"])])
    assert "Take 200 mg twice a day." in prompt and "<b>" not in prompt
    assert "Prenez 20 mg une fois par jour." in prompt
    assert "- accuracy/omission: Error where content present in the source is missing in the target." in prompt
    assert "- dose → dose / posologie" in prompt
    assert "JSON array only" in prompt and "Source language: en. Target language: fr." in prompt
    assert len(ai.category_paths()) == 38


# ── Reading the reply ─────────────────────────────────────────────────

def test_parse_reply_accepts_plain_fenced_and_wrapped_json():
    assert ai.parse_reply(reply(GOOD)) == [GOOD]
    assert ai.parse_reply("```json\n" + reply(GOOD) + "\n```") == [GOOD]
    assert ai.parse_reply("Here are the issues:\n" + reply(GOOD) + "\nDone.") == [GOOD]
    assert ai.parse_reply("[]") == []


def test_parse_reply_refuses_what_is_not_a_json_array():
    for bad in ("", "No issues found.", '{"side": "target"}', "[1, 2", "[{]"):
        with pytest.raises(ValueError):
            ai.parse_reply(bad)


def test_items_that_break_the_schema_are_marked_as_dropped():
    items = ai.parse_reply(reply(GOOD, {"side": "middle", "quote": "x", "category": "c", "severity": "minor",
                                        "explanation": "e"},
                                 {"quote": "20 mg"}, "text", {**GOOD, "severity": "huge"}))
    assert items == [GOOD, None, None, None, None]


# ── From items to issues ──────────────────────────────────────────────

def test_a_good_item_becomes_an_open_ai_issue_with_offsets_worked_out_here():
    issues, dropped = ai.to_issues(SEGMENT, [{**GOOD, "start": 999, "end": 1000}], "AI: ollama/llama3",
                                   ai.category_paths())
    (issue,) = issues
    assert dropped == 0
    assert (issue.origin, issue.status, issue.rule_id, issue.author) == ("ai", "open", "mqm", "AI: ollama/llama3")
    assert (issue.category, issue.severity, issue.side) == ("accuracy/mistranslation", "critical", "target")
    assert plain_text(SEGMENT.target)[issue.start:issue.end] == "20 mg"       # not the model's 999
    assert issue.message == "The dose is 200 mg in the source." and issue.suggestion == "200 mg"
    assert not issue.is_stale(SEGMENT.target)


def test_items_are_dropped_when_the_quote_is_not_in_the_text_or_the_category_is_unknown():
    items = [
        GOOD,
        {**GOOD, "quote": "20mg"},                                   # not in the text exactly
        {**GOOD, "quote": "<b>20 mg</b>"},                           # tags are not text
        {**GOOD, "quote": ""},
        {**GOOD, "category": "accuracy/invented"},
        {**GOOD, "category": "accuracy"},                            # a dimension, not a subtype
        {**GOOD, "side": "source", "quote": "20 mg"},                # the source says 200 mg … but has no "20 mg "
        GOOD,                                                        # said twice
        None,                                                        # broke the schema
        {**GOOD, "side": "source", "quote": "twice a day", "category": "accuracy/omission",
         "severity": "major", "suggestion": None},
    ]
    issues, dropped = ai.to_issues(SEGMENT, items, "AI: x/y", ai.category_paths())
    # "20 mg" is inside "200 mg"? No: "200 mg" does not contain "20 mg". So that one is dropped.
    assert [(i.side, i.quoted(SEGMENT.source if i.side == "source" else SEGMENT.target)) for i in issues] == \
        [("target", "20 mg"), ("source", "twice a day")]
    assert dropped == 8
    assert issues[1].suggestion is None


def test_only_offered_categories_are_kept():
    issues, dropped = ai.to_issues(SEGMENT, [GOOD], "AI: x/y", ai.category_paths(["style"]))
    assert issues == [] and dropped == 1


# ── A run ─────────────────────────────────────────────────────────────

def run(segments, replies, **options):
    prompts = []

    def ask(prompt):
        prompts.append(prompt)
        answer = replies[len(prompts) - 1]
        if isinstance(answer, Exception):
            raise answer
        return answer if isinstance(answer, tuple) else (answer, {"input_tokens": 100, "output_tokens": 20})

    options.setdefault("min_interval", 0)
    issues, summary = ai.annotate(segments, ask, provider="ollama", model="llama3", source_lang="en",
                                  target_lang="fr", **options)
    return issues, summary, prompts


def test_a_run_keeps_good_proposals_counts_dropped_ones_and_skips_untranslated_segments():
    segments = [SEGMENT, seg(2, "Close the valve.", ""), seg(3, "Wear gloves.", "Portez des gants.")]
    issues, summary, prompts = run(segments, [reply(GOOD, {**GOOD, "quote": "nowhere"}), "[]"])
    assert len(prompts) == 2                                           # the empty target is not sent
    assert [(i.segment_id, i.origin, i.status) for i in issues] == [(1, "ai", "open")]
    assert (summary.segments, summary.issues_kept, summary.issues_dropped, summary.failed_segments) == (2, 1, 1, 0)
    assert (summary.input_tokens, summary.output_tokens) == (200, 40)
    record = summary.to_report()
    assert record["provider"] == "ollama" and record["model"] == "llama3" and record["issuesDropped"] == 1
    assert record["estimatedCostUsd"] == 0.0 and record["inputTokens"] == 200      # a local model costs nothing
    assert "Issues proposed and kept: 1" in summary.text() and "200 in, 40 out" in summary.text()


def test_a_bad_reply_or_an_error_fails_that_segment_only():
    segments = [SEGMENT, seg(2, "Wear gloves.", "Portez des gants."), seg(3, "Stop.", "Arrêtez.")]
    issues, summary, _ = run(segments, [("I found no JSON for you.", {}), RuntimeError("connection refused"),
                                        (reply({**GOOD, "quote": "Arrêtez", "severity": "minor"}), {})])
    assert [i.segment_id for i in issues] == [3]
    assert summary.failed_segments == 2 and len(summary.errors) == 2
    assert "Segment 2: connection refused" in summary.errors[1]
    assert summary.tokens_known is False and summary.to_report()["inputTokens"] is None


def test_a_run_can_be_cancelled_and_reports_progress():
    segments = [seg(i, "Stop.", "Arrêtez.") for i in range(1, 6)]
    seen = []
    state = {"done": 0}

    def progress(done, total):
        seen.append((done, total))
        state["done"] = done

    issues, summary, prompts = run(segments, ["[]"] * 5, progress=progress,
                                   cancelled=lambda: state["done"] >= 2)
    assert len(prompts) == 2 and seen == [(1, 5), (2, 5)]
    assert summary.cancelled is True and "cancelled" in summary.text()


def test_requests_are_spaced_to_respect_the_rate_limit():
    segments = [seg(i, "Stop.", "Arrêtez.") for i in range(1, 4)]
    now = {"t": 0.0}
    slept = []

    def sleep(seconds):
        slept.append(round(seconds, 2))
        now["t"] += seconds

    def clock():
        now["t"] += 0.5            # each request takes half a second
        return now["t"]

    run(segments, ["[]"] * 3, min_interval=2.0, sleep=sleep, clock=clock)
    assert len(slept) == 2 and all(0 < s <= 2.0 for s in slept)
    assert ai.MIN_INTERVAL["ollama"] == 0.0 and ai.MIN_INTERVAL["gemini"] > ai.MIN_INTERVAL["claude"] > 0


def test_the_glossary_terms_of_a_segment_go_into_its_prompt():
    _, _, prompts = run([SEGMENT], ["[]"], glossary_for=lambda s: [("dose", ["posologie"])])
    assert "- dose → posologie" in prompts[0]


# ── Scoring ───────────────────────────────────────────────────────────

def test_ai_issues_count_only_after_a_person_accepts_them():
    issues, _, _ = run([SEGMENT], [reply(GOOD)])
    profile = scoring.ScoringProfile()
    assert scoring.calculate(issues, 1000, profile).absolute_penalty_total == 0
    assert scoring.calculate(issues, 1000, scoring.ScoringProfile(count_open_ai=True)).absolute_penalty_total == 25
    issues[0].status = "accepted"
    assert scoring.calculate(issues, 1000, profile).absolute_penalty_total == 25
