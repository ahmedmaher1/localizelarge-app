# Third-party licenses

Localize Large is licensed under GPL-3.0-or-later (see `LICENSE`). It is based on
Supervertaler Workbench by Michael Beijer (MIT License); that notice is in `NOTICE`.

This file lists the software Localize Large depends on. Versions are the ones installed in
the development environment on 2026-11-10; the release build pins its own versions and the
SBOM shipped with each release is the exact list for that build.

**Status: work in progress.** The lists below match `requirements.txt` and
`okapi-sidecar/pom.xml`.

## Python packages

Licenses are taken from each package's own metadata.

| Package | Version | License |
|---|---|---|
| PyQt6 | 6.12.0 | GPL-3.0-only |
| PyQt6-Qt6 (Qt libraries) | 6.12.0 | LGPL-3.0 |
| PyQt6-sip | 13.13.0 | BSD-2-Clause |
| python-docx | 1.2.0 | MIT |
| openpyxl | 3.1.5 | MIT |
| Pillow | 13.0.0 | MIT-CMU |
| lxml | 6.1.3 | BSD-3-Clause |
| openai | 3.48.0 | Apache-2.0 |
| anthropic | 2.7.0 | Apache-2.0 |
| requests | 2.34.2 | Apache-2.0 |
| httpx | 0.28.1 | BSD-3-Clause |
| rapidfuzz | 3.14.6 | MIT |
| jsonschema | 4.26.0 | MIT |
| psutil | 7.2.2 | BSD-3-Clause |
| markitdown | 0.1.9 | MIT |
| pyperclip | 1.11.0 | BSD |
| pyspellchecker | 0.9.1 | MIT |
| spylls | 0.1.7 | Not stated in the package's license field; its classifier says MIT. **To confirm against the project's repository before release.** |
| keyring (not used on Windows) | 25.7.0 | MIT |

Packages these depend on are not all listed here; the release SBOM lists every one. The
largest are brought in by `markitdown`:

| Package | Version | License |
|---|---|---|
| onnxruntime | 1.31.1 | MIT |
| numpy | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| magika | 1.0.3 | Apache-2.0 |

## Java libraries (Okapi sidecar)

Versions from `okapi-sidecar/pom.xml`.

| Library | Version | License |
|---|---|---|
| Okapi Framework (core, segmentation, and the filters openxml, openoffice, html, xliff, xliff2, po, idml, markdown, json, yaml, properties, table, plaintext, its/xml, subtitles, regex, tmx) | 1.48.0 | Apache-2.0 |
| Javalin | 6.7.0 | Apache-2.0 |
| Jackson Databind | 2.22.4 | Apache-2.0 |
| SLF4J Simple | 2.0.17 | MIT |

Brought in by the Okapi filters added in Phase 4 (licences read from each library's POM):

| Library | Version | License |
|---|---|---|
| flexmark-java (Markdown filter) | 0.64.8 | BSD-2-Clause |
| SnakeYAML Engine (YAML filter) | 2.8 | Apache-2.0 |
| Woodstox | 7.0.0 | Apache-2.0 |
| StAX2 API | 4.2.2 | BSD-2-Clause |
| TwelveMonkeys common | 3.12.0 | BSD-3-Clause |
| Jericho HTML Parser | 3.4 | Apache-2.0 (one of the three licences it offers; the others are LGPL and EPL) |
| Validator.nu HTML Parser | 1.4 | MIT |
| ICU4J | 75.1 | Unicode-3.0 |

Used only to test the sidecar, not shipped: JUnit Jupiter 5.11.4 (EPL-2.0).

Apache Commons FileUpload was listed by the base but never used; it is removed. Libraries
these depend on (Jetty and others) are in the release SBOM.

## Other

| Item | License |
|---|---|
| MQM Core typology (`localizelarge/data/mqm_core.json`), © The MQM Council, themqm.org | CC BY 4.0 |
| Supervertaler Workbench 1.10.376 (the base of this app) | MIT, © 2025 Michael Beijer |

## Removed in Phase 2

`PyQt6-WebEngine`, `PyMuPDF` (AGPL), `vosk`, `sounddevice`, `boto3`, `deepl`, `pynput`,
`ahk`, `pyobjc-framework-Cocoa`, and four packages nothing imported (`chardet`,
`sacrebleu`, `PyYAML`, `Markdown`). `tests/test_ll_clean_profile_launch.py` checks that none
of the first group is imported when the app runs.
