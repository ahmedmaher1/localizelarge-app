# Where Localize Large keeps data

For developers. The user-facing version, with what each file contains, is in
`docs/security/SECURITY_FACTS.md`.

## The rule

`localizelarge/paths.py` is the only code that builds a data path. Nothing else joins
`APPDATA`, `LOCALAPPDATA` or a home folder by hand. The locations are fixed: there is no
setting, pointer file or first-run choice that moves them. The app never reads or writes a
Supervertaler folder.

## The two roots

| Root | Windows | Other systems (development only) | Function |
|---|---|---|---|
| Settings root | `%APPDATA%\LocalizeLarge\` | `$XDG_CONFIG_HOME/LocalizeLarge` (default `~/.config/LocalizeLarge`) | `paths.settings_root()` |
| Local root | `%LOCALAPPDATA%\LocalizeLarge\` | `$XDG_DATA_HOME/LocalizeLarge` (default `~/.local/share/LocalizeLarge`) | `paths.local_root()` |

## Paths

| What | Path under its root | Function |
|---|---|---|
| Locked API keys | settings: `api-keys.locked.json` | `paths.api_keys_file()` |
| Settings file | settings: `workbench/settings/settings.json` | `paths.settings_file()` |
| Other settings files | settings: `workbench/settings/` | `paths.settings_dir()` |
| Prompt library | settings: `prompt_library/` | `paths.prompt_library_dir()` |
| Quality packs | settings: `packs/<id>/<version>/` | `paths.packs_dir()` |
| Pricing override | settings: `pricing.json` | `paths.pricing_override_file()` |
| TM and glossary database | local: `resources/localizelarge.db` | `paths.database_file()` |
| Logs | local: `logs/` | `paths.logs_dir()` |
| Crash log (macOS frozen builds only) | local: `logs/crash.log` | `paths.crash_log_file()` |
| Cache | local: `cache/` | `paths.cache_dir()` |

## Paths the base code still derives from the settings root

The main window keeps `self.user_data_path`, which is the settings root, and base modules
still build these sub-paths from it. They stay inside the settings root, so the rule above
holds for the roots; moving these into `paths.py` is clean-up for a later phase.

| What | Path under the settings root |
|---|---|
| Spelling dictionaries and custom words | `workbench/dictionaries/` |
| AI Assistant attachments | `workbench/ai_assistant/` |
| Timestamped project backups | `workbench/backups/` |
| AI usage ledger | `workbench/usage/usage-YYYY-MM.jsonl` |
| Recent projects, themes, shortcuts | `workbench/settings/` |

## Tests

- `tests/test_ll_identity.py`: the roots and paths on Windows and under XDG.
- `tests/test_ll_clean_profile_launch.py`: starts the real app on an empty profile and
  checks that it creates only the two `LocalizeLarge` folders, puts the database and logs in
  the local root, and writes nothing named after Supervertaler.

Always run tests with a throwaway profile (temporary `APPDATA` and `LOCALAPPDATA`, or a
temporary `HOME` on other systems).
