# Performance

Measured figures only. A target with no figure has not been measured yet.

| Target (build plan §7) | Figure | Where and when |
|---|---|---|
| Cold start under 6 s | 4.7 to 5.4 s over several runs, from process start to the main window's event loop | From source, Linux development container (4 cores, Xeon 2.1 GHz), no display, 2026-11-10. Not yet measured for the built app on Windows. |
| Import a 5,000-segment DOCX in under 30 s | not measured yet | |
| All QA checks on 5,000 segments in under 10 s | not measured yet (Phase 5) | |
| TM lookup in a 100,000-unit TM in under 300 ms | median 121 ms, slowest 270 ms, over 50 lookups; each lookup found its near match | `python tools/bench_tm.py 100000`, same container, 2026-11-10 |
| Glossary checks: 50,000 entries, under 1 s per 1,000 segments (plan 5b) | 0.18 s for 1,000 segments; building the index once takes 0.36 s | `tests/test_ll_glossary_check.py`, same container, 2026-11-10 |
| Grid scrolling smooth with 20,000 segments | not measured yet | |

## TM lookup

`tools/bench_tm.py` builds a throwaway memory of made-up English→French units and looks up
50 segments that each differ by one word from a unit in the memory.

| Version of the lookup | Median | Slowest | Near match found |
|---|---|---|---|
| Base code (candidates sorted worst-first, `SequenceMatcher`) | 288 ms | 443 ms | 0 of 50 |
| Candidate order fixed, new scorer | 299 ms | 450 ms | 50 of 50 |
| One query for both directions, candidates pre-screened | 229 ms | 310 ms | 50 of 50 |
| 10 search terms instead of 20 (current) | 121 ms | 270 ms | 50 of 50 |

The made-up units share most of their words, which is harder for the full-text index than
a real memory.

## Windows build

Preview build of 2026-11-10 (GitHub Actions run 7, commit `1afa0c6`), before the Phase 4
file formats were added to the sidecar:

- ZIP: `LocalizeLarge-1.0.0-preview-win-x64.zip`, 173,412,397 bytes (165.4 MB).
- Build time on the runner: 5 min 30 s.
- Largest folders inside `_internal`:

| MB | Folder |
|---|---|
| 73.6 | okapi-sidecar (JAR and the bundled Java runtime) |
| 69.9 | PyQt6 |
| 37.5 | onnxruntime |
| 20.2 | numpy.libs |
| 10.7 | PIL |
| 9.0 | openai |
| 8.5 | lxml |
| 7.3 | anthropic |
| 7.0 | spellchecker |
| 6.1 | numpy |

`onnxruntime` and `numpy` (64 MB together) come in through `markitdown`; whether they can
be left out is an open issue.
