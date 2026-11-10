# Building and releasing the Windows ZIP

**Status:** a **preview** is published. Version 1.0.0 is not finished: Phases 6 to 8 of
the build plan are still to do.

| Preview | |
|---|---|
| Version on the website | `1.0.0-preview.1` |
| Built from | commit `b61388a`, GitHub Actions run 10 of "Build Windows ZIP", 2026-11-10 |
| File | `LocalizeLarge-1.0.0-preview-win-x64.zip`, 173,588,065 bytes |
| SHA-256 | `74d7778fc9544eeaff2349ae9a5b88671ae1a45d4971e3cb78495e994052554f` |
| Address | `https://localizelarge.com/downloads/windows/1.0.0-preview.1/LocalizeLarge-1.0.0-preview-win-x64.zip` |
| Source of that build | `https://localizelarge.com/downloads/windows/1.0.0-preview.1/LocalizeLarge-1.0.0-preview-source.zip` (`git archive` of the commit) |
| Signed | no |

The owner asked for the preview to be published on 2026-11-10. It was not tested by hand
on a clean Windows 11 machine first; the checks it passed are the automatic ones of the
build script (below) and the test suite on a Windows runner.

The app is licensed under the GPL (and includes PyQt6, which is GPL), so everyone who can
download the program must be able to download its source. That is why the source archive
is hosted beside the ZIP. Every published build needs its own source archive.

## Build

The build runs on a GitHub Actions Windows runner, because PyInstaller can only build a
Windows program on Windows.

1. On GitHub, open the repository's **Actions** tab and choose **Build Windows ZIP**.
2. Click **Run workflow**. Leave the label as `preview` for a test build; clear it for a
   release build.
3. When the run finishes, download the artifact **LocalizeLarge-windows-build** from the
   run's page. It holds the ZIP, its `.sha256` file and `release.json`.

The artifact is private to the repository and is kept for 14 days. The workflow publishes
nothing.

To build on your own Windows computer instead (Python 3.12, a JDK 17 with `JAVA_HOME` set,
Maven):

```powershell
python -m pip install -r requirements.txt pyinstaller
```

```powershell
.\scripts\build_release.ps1 -Label preview
```

## What the build script does

`scripts/build_release.ps1`:

1. Builds the Okapi sidecar JAR.
2. Builds a minimal Java runtime with `jlink`.
3. Runs PyInstaller with `LocalizeLarge.spec`: one folder, no console window, no UPX.
4. Adds the Java runtime, `LICENSE`, `NOTICE`, `THIRD_PARTY_LICENSES.md`, `CHANGELOG.md` and
   `docs/security/`.
5. Checks the build:
   - no file of a package removed from v1 is in it (WebEngine, PyMuPDF and the others);
   - the built app starts on an empty profile, creates only the two `LocalizeLarge` folders,
     starts its file-format service on `127.0.0.1` with the bundled Java, and exits with
     code 0 leaving no Java process.
6. Writes the ZIP, its SHA-256 file and `release.json` (the fields the website needs).

Not done by the script yet (Phase 8): the SBOM, code signing, and the test on a clean
Windows 11 machine, which a person has to do.

With **stage** ticked, the workflow also pushes the ZIP, cut into two parts under GitHub's
100 MB file limit, to the branch `build-artifact` of this repository. From there it can be
fetched with git, joined (`cat part00 part01 > file.zip`), checked against the `.sha256`
file and uploaded to the hosting. Delete the branch afterwards.

## Before a final (non-preview) build may be published

- All eight phases are done and their tests pass on Windows.
- The ZIP has been tested by hand on a clean Windows 11 machine with no Python and no Java:
  the smoke test in the build plan, the contents of `%APPDATA%` and `%LOCALAPPDATA%` against
  `docs/security/SECURITY_FACTS.md`, and `netstat -ano` during a session.
- `docs/security/network-connections.json` and `SECURITY_FACTS.md` have been checked against
  that build and their "not yet verified" marks removed.
- The website's own data (`src/data/network-connections.json`, `security-facts.json`,
  `features.json`) has been updated from these documents. At the time of writing the website
  still describes the base app in places (a plain-text key option, port 8090, LanguageTool's
  public server as the default). Those statements are not true of this app.

## Where the ZIP is hosted

The website does not need the file to be in one particular place: each release entry in the
site's `src/data/releases.json` carries its own download address (`--url` of the site's
`npm run release:add`).

Two options the owner has approved:

### Hostinger (the website's own hosting)

The ZIP is uploaded into the site's `public_html`, for example to
`downloads/windows/1.0.0/LocalizeLarge-1.0.0-win-x64.zip`, and the release entry uses
`https://localizelarge.com/downloads/windows/1.0.0/LocalizeLarge-1.0.0-win-x64.zip`.

Caution, from the website's `docs/HOSTINGER.md`: Hostinger's deploy button replaces
`public_html`. After every redeploy of the site, check that the ZIP is still there and
upload it again if it is not.

### GitHub Releases

The build workflow can attach the ZIP to a GitHub release of this repository. The download
address is then
`https://github.com/ahmedmaher1/localizelarge-app/releases/download/v1.0.0/LocalizeLarge-1.0.0-win-x64.zip`.
This works for website visitors only if this repository is public. It is private today. The
app is licensed under the GPL, which requires offering the source to anyone who receives the
program, so a public repository is also the simplest way to meet that.

## Adding the release to the website

In the website repository, after the ZIP is hosted:

```bash
npm run release:add -- --file ./LocalizeLarge-1.0.0-win-x64.zip --version 1.0.0 --based-on "Supervertaler Workbench 1.10.376 (f83e520)" --url <download address>
```

Then follow the website's `docs/RELEASING.md` (release notes, security facts, checks, deploy).
