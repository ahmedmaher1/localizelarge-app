# Third-party licenses

Localize Large is licensed under GPL-3.0-or-later (see `LICENSE`). It is based on
Supervertaler Workbench by Michael Beijer (MIT License); that notice is in `NOTICE`.

This file lists the software Localize Large depends on. Versions are the ones installed in
the development environment on 2026-11-10; the release build pins its own versions and the
SBOM shipped with each release is the exact list for that build.

**Status: work in progress.** The dependency set is being reduced to the v1 scope. Packages
that are still to be removed are listed at the end.

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
| google-generativeai | 0.8.6 | Apache-2.0 |
| requests | 2.34.2 | Apache-2.0 |
| chardet | 7.7.0 | 0BSD |
| psutil | 7.2.2 | BSD-3-Clause |
| markitdown | 0.1.9 | MIT |
| sacrebleu | 2.6.0 | Apache-2.0 |
| pyperclip | 1.11.0 | BSD |
| PyYAML | 6.0.3 | MIT |
| Markdown | 3.11.3 | BSD-3-Clause |
| pyspellchecker | 0.9.1 | MIT |
| spylls | 0.1.7 | Not stated in the package's license field; its classifier says MIT. **To confirm against the project's repository before release.** |
| numpy | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| keyring (not used on Windows) | 25.7.0 | MIT |

Packages these depend on are not listed here yet. The release SBOM lists all of them.

## Java libraries (Okapi sidecar)

Versions from `okapi-sidecar/pom.xml` at the base commit. They are upgraded in Phase 3, and
this table is updated in the same commit.

| Library | Version | License |
|---|---|---|
| Okapi Framework | 1.47.0 | Apache-2.0 |
| Javalin | 6.4.0 | Apache-2.0 |
| Jackson Databind | 2.18.2 | Apache-2.0 |
| SLF4J Simple | 2.0.16 | MIT |
| Apache Commons FileUpload | 1.5 | Apache-2.0 |

## Other

| Item | License |
|---|---|
| Supervertaler Workbench 1.10.376 (the base of this app) | MIT, © 2025 Michael Beijer |

## Still installed, to be removed in Phase 2

`PyQt6-WebEngine`, `PyMuPDF` (AGPL; must not ship), `vosk`, `sounddevice`, `boto3`, `deepl`,
`pynput`, `ahk`, `pyobjc-framework-Cocoa`. None of these may be in a release build.
