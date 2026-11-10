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
