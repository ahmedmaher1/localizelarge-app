# Removed from the Supervertaler base

Everything below was in Supervertaler Workbench 1.10.376 (commit `f83e520`) and is not in
Localize Large. It all remains in the git history and in the `upstream` remote.

## Repository material (Phase 1)

Not part of the app. Removed so the repo holds only what Localize Large builds and ships.

| Removed | What it was |
|---|---|
| `.dev/` | Upstream development notes, old builds and 150 files of earlier versions |
| `legacy_versions/`, `dist_pypi/` | Old releases and PyPI packaging output |
| `docs/` (upstream content) | The Supervertaler website, screenshots, specifications and archive |
| `.github/`, `.vscode/` | Upstream funding file, issue templates, CI workflow and editor settings |
| `binaries/ffmpeg.exe` | Audio decoder for voice features. Voice is out of v1 scope |
| `user_data/` | Upstream sample database and API-key example file |
| `codesign.env`, `codesign.env.example` | Upstream author's macOS signing identity and Apple Team ID |
| `release-body-*.md`, `release-notes-*.md`, `RELEASE_DESCRIPTION.md` | Upstream release notes |
| `CLAUDE_SESSION_HANDOFF.md`, `FAQ.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `WINDOWS_BUILDS.md`, `BUILD_MACOS.md` | Upstream project documents |
| `_create_release.py`, `create_release_zip.py` | Upstream release scripts (one posts to the Supervertaler GitHub repo) |
| `clear_icon_cache.cmd`, Start-menu shortcut scripts in `scripts/` | Upstream developer helpers |
| Four files in `assets/` | Icon notes, an icon preview page and an unused image |

`Supervertaler.spec` still lists `docs` and `FAQ.md` as bundled data. That file is replaced
by `LocalizeLarge.spec` in Phase 8; until then the upstream spec does not build.

## Features

Phase 2, in the order of the build plan. Still in progress.

### 1. Global hotkeys and background running

| Removed | Why |
|---|---|
| OS-level (global) hotkeys: the AutoHotkey script `supervertaler_hotkeys.ahk`, the `ahk` library route, the `pynput` route, the signal-file watcher, the AutoHotkey setup dialog and settings field | v1 registers nothing outside its own window. In-app shortcuts are unchanged (`Ctrl+Alt+L` still opens SuperLookup while the app has focus) |
| Capturing the selected text from another application | It worked only through the global hotkey |
| `start-admin.ps1` | It started the app with administrator rights. v1 needs none |
| `modules/autostart.py` and "Start with computer" | v1 never adds itself to the Windows start-up list |
| System tray icon, "Close to tray", "Start minimized to tray", Esc-to-tray | Closing the window always quits. No process is left running |

Old settings keys for these (`close_to_tray`, `start_minimized_to_tray`, `autohotkey_path`)
are ignored if present.

"Sidekick", the floating system-wide assistant, was already retired upstream; only the name
remained. The in-app assistant tab is now called "AI Assistant".

### 2. Voice

| Removed | Why |
|---|---|
| Voice commands and the Always-On listener: `modules/voice_commands.py`, `voice_command_dialog.py`, `voice_tab.py`, `vosk_model_manager.py`, `mic_devices.py`, the Voice tab, the Always-On toolbar button and status-bar indicator, the `Ctrl+Alt+O` shortcut | Out of v1 scope. The app never opens the microphone and never downloads a speech model |
| Their tests (`test_alwayson_listener.py`, `test_voice_*.py`) | The code they tested is gone |

The packages `vosk`, `sounddevice` and `pynput` leave `requirements.txt` at the end of
Phase 2, with the other removed packages.

### 3. Embedded browser and web lookups

| Removed | Why |
|---|---|
| Superbrowser (`modules/superbrowser.py`): ChatGPT, Claude and Gemini web pages side by side | It loaded third-party websites inside the app |
| SuperLookup's "Web Resources" tab, its settings sub-tab and custom web resources (`modules/custom_web_resources.py`) | Same. Every lookup sent the search text to outside websites |
| SuperLookup's machine-translation lookup, including the built-in MyMemory call | MT services are out of v1 scope |
| All use of QtWebEngine (the embedded Chromium) | No remaining use. The app no longer starts Chromium processes or keeps a web cache |

Kept: SuperLookup's translation-memory and termbase search.

Also removed because nothing imported them: `modules/feature_manager.py`,
`modules/pdf_rescue_tkinter.py`, `modules/translation_services.py`, `modules/superdocs.py`,
`modules/superdocs_viewer_qt.py`, `modules/setup_wizard.py`.

Effect measured in the Linux test container: the app now exits cleanly (the base crashed on
exit in QtWebEngine), and time to the first window fell from 8.7 s to about 5.5 s.

### 4. PDF tools and image tools

| Removed | Why |
|---|---|
| PDF Rescue (`modules/pdf_rescue_Qt.py`) and the PyMuPDF dependency | PyMuPDF is AGPL and must not ship. PDF is not a v1 format |
| Image Extractor / "Superimage" (`modules/image_extractor.py`) and the Image Context viewer it lived in | Out of v1 scope |

**Disabled, not deleted:** `modules/figure_context_manager.py` and the code that attaches
images to an AI request when a segment mentions a figure. With the viewer gone there is no
way to load images, so that code never runs. The "4. Image Context" section of the Prompt
Manager is hidden. It should be deleted or brought back as a whole in a later version.

### 6. Trados and memoQ live bridges

| Removed | Why |
|---|---|
| The bridge server (`modules/supervertaler_bridge_server.py`): a local HTTP service the Trados plugin called | v1 runs one local service only, the Okapi sidecar |
| The Trados bridge client (`modules/trados_bridge_client.py`), the "Trados" context chip in the AI Assistant and the Trados context added to prompts | The app does not talk to other CAT tools |
| Headless batch-offload mode (`--batch`, `--translate-sdlxliff`; `modules/batch_offload.py`) | It existed for the Trados plugin |

**Disabled, not deleted:** the "Bridge" column of the Translation Memories table and its two
bulk buttons are hidden. The database column behind them (`bridged_to_trados`) is left in
place so existing databases need no migration.

Kept: the file-based bilingual formats (memoQ, Trados, Phrase, CafeTran, Déjà Vu).

### 7. Telemetry, update check and outside links

| Removed | Why |
|---|---|
| The opt-in usage ping (`modules/usage_statistics.py`) and its Privacy setting | The app sends no usage data, opted in or not |
| The update check that called the GitHub API for the Supervertaler repository | "Check for updates" now opens `https://localizelarge.com/download` in the default browser. The app itself makes no request |
| Help-menu links to the Supervertaler changelog, discussions and GitHub repository; "generated by" links to supervertaler.com in exports | Not this product |
| The setup wizard and "Change data folder" | The two data folders are fixed. Settings → General shows both, read-only, with an Open button |

F1 and Help open `https://localizelarge.com/docs` in the browser. Per-panel help topics are
kept on the widgets but all open that one address until the site has a page for each.

### 5. Machine-translation services and extra AI providers

| Removed | Why |
|---|---|
| Machine-translation engines: Google Translate, DeepL, Microsoft Translator, Amazon Translate, ModernMT, MyMemory, and custom MT endpoints. Their call code, the "MT Settings" tab, the MT option in the batch-translate dialog and the MT provider group in QuickTrans settings | v1 has no MT engines. Translation is by hand, from the translation memory, or by one of the four AI providers |
| AI providers Mistral, DeepSeek, OpenRouter and custom OpenAI-compatible endpoints: their model tables, service addresses, API-key rows, and entries in the AI Assistant and QuickTrans | v1 talks to Claude, OpenAI, Gemini and Ollama only |
| `tests/test_openrouter_models.py` | The code it tested is gone |

The AI client (`modules/llm_clients.py`) now refuses any provider outside the four
(`LLMClient.SUPPORTED_PROVIDERS`); tests cover this. A provider saved in old settings that
is not one of the four is ignored and the default is used.

**Disabled, not deleted** (to be deleted in Phase 7, which reworks the provider code):

- In Settings → AI Settings, the radio buttons, model lists and custom-endpoint fields of
  the removed providers are still built but hidden, and can never be selected.
- The code that saves and loads custom endpoint profiles, and the settings keys
  `custom_openai_*`, `custom_mt_*`, `mt_*` and `llm_mistral`/`llm_openrouter`.
- Two unreachable branches in `llm_clients.py` for OpenRouter prompt caching.
- The "MT" box of the compare panel and the MT colour table in `modules/quicktrans.py`.

QuickTrans is kept, with AI providers only.
