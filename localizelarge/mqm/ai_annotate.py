"""AI pre-annotation (beta): an AI proposes MQM issues; a person decides.

For each segment the model gets the source, the target, the glossary terms found in the
source, and the list of categories. It must answer with a JSON array:

    [{"side", "quote", "category", "severity", "explanation", "suggestion"}]

What the model says is not trusted:

* the reply is validated against a JSON schema;
* an issue is kept only when its ``quote`` is found exactly in that side's text, and the
  offsets are worked out here, never taken from the model;
* its category must be one of the offered categories and its severity a known one;
* everything else is dropped and counted in the run summary.

A kept issue has origin "ai" and status "open". It does not count towards the score
until a person accepts it, unless the profile says otherwise.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from localizelarge.quality.model import Issue, make_issue, now_utc, plain_text

from . import typology

SEVERITIES = ("neutral", "minor", "major", "critical")

REPLY_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "required": ["side", "quote", "category", "severity", "explanation"],
        "properties": {
            "side": {"enum": ["source", "target"]},
            "quote": {"type": "string"},
            "category": {"type": "string"},
            "severity": {"enum": list(SEVERITIES)},
            "explanation": {"type": "string"},
            "suggestion": {"type": ["string", "null"]},
        },
    },
}

# Seconds to wait between two requests to one provider, so that a batch run stays
# inside the provider's rate limit. A local model needs no pause.
MIN_INTERVAL = {"claude": 1.2, "openai": 1.2, "gemini": 4.0, "ollama": 0.0}


def category_paths(allowed: Optional[Sequence[str]] = None) -> List[str]:
    """The subtype paths offered to the model: all of MQM Core, or the profile's list."""
    paths = [c.path for c in typology.categories() if "/" in c.path]
    if not allowed:
        return paths
    wanted = set(allowed)
    return [p for p in paths if p in wanted or p.split("/")[0] in wanted]


def build_prompt(source: str, target: str, source_lang: str, target_lang: str,
                 categories: Sequence[str], glossary: Sequence[Tuple[str, Sequence[str]]] = ()) -> str:
    """The instruction for one segment."""
    lines = [
        "You are reviewing a translation for errors, using the MQM error typology.",
        f"Source language: {source_lang}. Target language: {target_lang}.",
        "",
        "Report only real errors in the target (or text of the source that the target leaves out).",
        "If the translation is correct, answer with an empty array: []",
        "",
        "Answer with a JSON array only, no other text. Each item:",
        '{"side": "target" or "source", "quote": the exact words the error is in, copied character',
        ' for character from that side, "category": one of the categories below, "severity":',
        ' "neutral", "minor", "major" or "critical", "explanation": one sentence in English,',
        ' "suggestion": a corrected wording or null}',
        "",
        "Severity: minor = noticeable but does not change the meaning; major = changes the meaning or",
        "makes the text hard to understand; critical = could cause harm, legal or financial damage.",
        "",
        "Categories:",
    ]
    for path in categories:
        category = typology.get(path)
        lines.append(f"- {path}: {category.definition}" if category else f"- {path}")
    if glossary:
        lines += ["", "Glossary terms found in the source (the approved translation must be used):"]
        for source_term, targets in glossary:
            lines.append(f"- {source_term} → {' / '.join(targets)}")
    lines += ["", "Source:", plain_text(source), "", "Target:", plain_text(target)]
    return "\n".join(lines)


def parse_reply(reply: str) -> List[Dict[str, Any]]:
    """The JSON array in a model's reply. Raises ``ValueError`` when there is none or it
    does not fit the schema."""
    import jsonschema
    text = (reply or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    if not text.startswith("["):
        start, end = text.find("["), text.rfind("]")
        if start < 0 or end <= start:
            raise ValueError("the reply has no JSON array")
        text = text[start:end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"the reply is not valid JSON: {error}") from error
    if not isinstance(data, list):
        raise ValueError("the reply is not a JSON array")
    kept = []
    for item in data:
        try:
            jsonschema.validate([item], REPLY_SCHEMA)
        except jsonschema.ValidationError:
            kept.append(None)        # counted as dropped by the caller
            continue
        kept.append(item)
    return kept


def to_issues(segment, items: Iterable[Optional[Dict[str, Any]]], author: str,
              categories: Sequence[str]) -> Tuple[List[Issue], int]:
    """Issues from a model's items for one segment. Returns (issues kept, items dropped)."""
    allowed = set(categories)
    issues: List[Issue] = []
    dropped = 0
    seen = set()
    for item in items:
        if item is None:
            dropped += 1
            continue
        side = item["side"]
        text = plain_text(segment.source if side == "source" else segment.target)
        quote = item["quote"]
        start = text.find(quote) if quote else -1
        if start < 0 or item["category"] not in allowed or item["severity"] not in SEVERITIES:
            dropped += 1
            continue
        key = (side, start, len(quote), item["category"])
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        suggestion = item.get("suggestion")
        issues.append(make_issue(
            segment, origin="ai", rule_id="mqm", category=item["category"], severity=item["severity"],
            message=item["explanation"].strip(), side=side, start=start, end=start + len(quote),
            suggestion=suggestion.strip() if isinstance(suggestion, str) and suggestion.strip() else None,
            author=author, status="open"))
    return issues, dropped


@dataclass
class RunSummary:
    provider: str
    model: str
    date: str = field(default_factory=now_utc)
    segments: int = 0
    issues_kept: int = 0
    issues_dropped: int = 0
    failed_segments: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tokens_known: bool = False
    cancelled: bool = False
    errors: List[str] = field(default_factory=list)

    def estimated_cost_usd(self) -> Optional[float]:
        if self.provider == "ollama":
            return 0.0
        if not self.tokens_known:
            return None
        try:
            from modules.llm_pricing import estimate_cost
            return estimate_cost(self.provider, self.model, self.input_tokens, self.output_tokens)
        except Exception:
            return None

    def to_report(self) -> Dict[str, Any]:
        """The record of this run for the quality report."""
        return {"provider": self.provider, "model": self.model, "date": self.date,
                "segments": self.segments, "issuesKept": self.issues_kept,
                "issuesDropped": self.issues_dropped,
                "inputTokens": self.input_tokens if self.tokens_known else None,
                "outputTokens": self.output_tokens if self.tokens_known else None,
                "estimatedCostUsd": self.estimated_cost_usd()}

    def text(self) -> str:
        lines = [f"Segments sent: {self.segments}", f"Issues proposed and kept: {self.issues_kept}",
                 f"Proposals dropped (quote not found in the text, unknown category, or bad format): "
                 f"{self.issues_dropped}"]
        if self.failed_segments:
            lines.append(f"Segments with no usable reply: {self.failed_segments}")
        if self.tokens_known:
            lines.append(f"Tokens: {self.input_tokens} in, {self.output_tokens} out")
        cost = self.estimated_cost_usd()
        if cost is not None:
            lines.append(f"Estimated cost: {cost:.4f} USD")
        if self.cancelled:
            lines.append("The run was cancelled.")
        return "\n".join(lines)


def annotate(segments: Sequence[Any], ask: Callable[[str], Tuple[str, Dict[str, Any]]], *,
             provider: str, model: str, source_lang: str, target_lang: str,
             categories: Optional[Sequence[str]] = None,
             glossary_for: Optional[Callable[[Any], Sequence[Tuple[str, Sequence[str]]]]] = None,
             progress: Optional[Callable[[int, int], None]] = None,
             cancelled: Optional[Callable[[], bool]] = None,
             min_interval: Optional[float] = None,
             sleep: Callable[[float], None] = time.sleep,
             clock: Callable[[], float] = time.monotonic) -> Tuple[List[Issue], RunSummary]:
    """Ask the model about each segment. ``ask(prompt)`` returns (reply text, usage);
    usage may hold "input_tokens" and "output_tokens".

    Untranslated segments are skipped. Requests to one provider are spaced by
    ``min_interval`` seconds. The run stops between segments when ``cancelled()`` is true.
    """
    paths = category_paths(categories)
    author = f"AI: {provider}/{model}"
    summary = RunSummary(provider=provider, model=model)
    interval = MIN_INTERVAL.get(provider, 1.0) if min_interval is None else min_interval
    todo = [s for s in segments if (getattr(s, "target", "") or "").strip()]
    found: List[Issue] = []
    last_request: Optional[float] = None
    for number, segment in enumerate(todo, 1):
        if cancelled and cancelled():
            summary.cancelled = True
            break
        if last_request is not None and interval > 0:
            wait = interval - (clock() - last_request)
            if wait > 0:
                sleep(wait)
        prompt = build_prompt(segment.source, segment.target, source_lang, target_lang, paths,
                              glossary_for(segment) if glossary_for else ())
        last_request = clock()
        summary.segments += 1
        try:
            reply, usage = ask(prompt)
            if usage and ("input_tokens" in usage or "output_tokens" in usage):
                summary.tokens_known = True
                summary.input_tokens += int(usage.get("input_tokens") or 0)
                summary.output_tokens += int(usage.get("output_tokens") or 0)
            issues, dropped = to_issues(segment, parse_reply(reply), author, paths)
            found.extend(issues)
            summary.issues_kept += len(issues)
            summary.issues_dropped += dropped
        except Exception as error:
            summary.failed_segments += 1
            if len(summary.errors) < 5:
                summary.errors.append(f"Segment {getattr(segment, 'id', '?')}: {error}")
        if progress:
            progress(number, len(todo))
    return found, summary
