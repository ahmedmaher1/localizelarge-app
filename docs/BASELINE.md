# Baseline — Supervertaler Workbench 1.10.376, untouched

Phase 0 of the Localize Large v1 build plan. Nothing in the base code was changed.

- **Base:** `Supervertaler/Supervertaler-Workbench`, commit
  `f83e5203298aa3c120a1f77cd3705dd65d28c44c` (upstream `HEAD` on 2026-11-10).
- **Recorded:** 2026-11-10.
- **Where:** a Linux cloud container (Ubuntu 24.04, x86-64), not Windows. Python 3.12.3,
  PyQt 6.12.0 / Qt 6.12.0, OpenJDK 21.0.12, Maven 3.9.11. Qt ran headless
  (`QT_QPA_PLATFORM=offscreen`). Every Windows-only figure below is marked **not measured**.

## Size of the base

| Item | Figure |
|---|---|
| `Supervertaler.py` | 72,485 lines |
| `modules/` | 136 files, 81,717 lines of Python |
| Sidecar Java source | 9 files, 1,739 lines |
| Test files | 63 |
| Tracked files | 965 |
| Python packages installed from `requirements.txt` (plus pytest, pytest-qt, pytest-timeout) | 105 |

## Sidecar build

`mvn -B -q package -DskipTests` in `okapi-sidecar/` succeeds (compiler target 17, built with
JDK 21). Output: `okapi-sidecar-0.1.9.jar`, 27.6 MB (27,636,473 bytes). Okapi 1.47.0,
Javalin 6.4.0, Jackson 2.18.2, commons-fileupload 1.5.

Started by hand on port 18090:

- `/health` answers; it reports `okapi_version: "unknown"`.
- `/extract` on a small DOCX returns 3 segments through `okf_openxml`, with inline bold as
  `<b>…</b>`.
- **It listens on `0.0.0.0`** (all network interfaces), as the plan says. Seen in
  `/proc/net/tcp` as `00000000:46AA` in the listening state.
- `/shutdown` stops it; no Java process was left.

## Tests

`pytest tests/ --continue-on-collection-errors` with a temporary `HOME`: **22.9 s**.

| Result | Count |
|---|---|
| Passed | 591 |
| Failed | 8 |
| Skipped | 56 |
| Collection errors | 1 |

Failures and errors:

- **8 failed, all in `tests/test_voice_commands_only.py`.** `pynput` cannot load without an
  X display (`failed to acquire X connection`). This comes from the headless Linux
  container, not the code. Voice is removed in Phase 2.
- **1 collection error, `tests/test_api_key_settings_page.py`.** It imports
  `lock_with_entropy` from `tests/test_api_key_store.py`, which does not define that name.
  This is a real fault in the upstream tests at this commit, on any platform. Its tests
  never run.

Skipped:

- 48: "DPAPI and the locked file are Windows'" (Windows only).
- 4: no Supervertaler-Help checkout beside the repo.
- 4: the sidecar JAR or Java was not found where the tests look.

`pip check` (`uv pip check`): clean.

## App launch

Launched `main()` headless on an empty profile, held it open for 4 s, then quit.

- The main window opens: title "Supervertaler Workbench v1.10.376", 1400×800.
- **Time to the event loop: 8.7 s.** This is a first run that creates the database and the
  default prompts, on a shared cloud container with software rendering. It is not the
  plan's "normal laptop" figure. Windows cold start: **not measured**.
- First run shows a message box and a "Setup Wizard" dialog (both skipped by the probe).
- The status bar says "Okapi sidecar not installed yet – will offer to download on first
  DOCX import" (the lazy download the plan removes).
- On Linux it wrote to `~/Supervertaler/` (database, settings, prompt library, logs, a
  `web_cache` folder) and `~/.config/Supervertaler/config.json`.
- **The first attempt died without an error** while creating the embedded browser
  (QtWebEngine). It starts only with `QTWEBENGINE_DISABLE_SANDBOX=1` and
  `QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox --disable-gpu"`, because the container runs as
  root with no GPU.
- **On exit the process crashed with a segmentation fault** (exit code 139) after "Release
  of profile requested but WebEnginePage still not deleted". This is QtWebEngine teardown.
  WebEngine is removed in Phase 2.
- No Python or Java process was left running.

## Smoke test (§6) on the untouched code

| Step | Result |
|---|---|
| 1. Start on a clean profile | **Pass** (old name, as expected) |
| 2. New EN→AR project with DOCX, TMX and TBX | **Not run.** TBX import does not exist yet; the sample files are made in Phase 4 |
| 3. Translate, confirm, TM and glossary matches | **Not run** (needs a person at the UI, or the scripted smoke test that later phases add) |
| 4. Run QA, add an MQM issue, scorecard | **Cannot pass.** No QA engine, MQM or scorecard in the base |
| 5. Export DOCX and HTML quality report | **Not run.** The quality report does not exist |
| 6. Save, close, reopen | **Not run** |
| 7. Exit leaves no process | **Partly.** No process left, but the exit crashed (see above) |

Only steps 1 and 7 were exercised. Steps 2, 3 and 6 use features the base has; they were
not driven through the UI in this headless container.

## Plan's "known problems", checked against the source

All seven are present at this commit:

| Problem | Where |
|---|---|
| Sidecar binds all interfaces | `okapi-sidecar/.../App.java:142`, `app.start(port)` |
| Sidecar enables CORS | `App.java:78` |
| Plain-text API key copy | `modules/api_key_store.py` (`settings/api-keys.json`) |
| Usage ping | `modules/usage_statistics.py:31` |
| GitHub update check | `Supervertaler.py:61479` and `:61937` |
| LanguageTool public API default | `modules/languagetool_client.py:20` |
| `upx=True` | `Supervertaler.spec:116` and `:130` |

Also confirmed: `Ctrl+Shift+E` is not used by any shortcut (`Ctrl+Shift+Enter` is).

## Not measured, and why

- **Windows build size.** PyInstaller builds only for the system it runs on; this
  container is Linux.
- **Windows cold-start time, DPAPI key tests, `netstat` on Windows.** Need a Windows
  machine.
- **Network traffic at startup.** Not captured in this phase.

## Other things seen

- `user_data/supervertaler.db` and `codesign.env` are tracked in the upstream repo. The
  second holds the upstream author's macOS signing identity and Apple Team ID (upstream
  calls them public). Neither should ship in Localize Large.
- A fresh clone is about 395 MB on disk, git history included. It carries old versions
  in `legacy_versions/`, `.dev/previous_versions/` and `dist_pypi/`.
