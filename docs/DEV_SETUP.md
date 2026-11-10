# Developer setup

Two setups are described. The Linux one is what Phase 0 actually ran. The Windows one is
what the plan asks for; **its steps have not been run yet** and are marked so.

## Linux (run on 2026-11-10, Ubuntu 24.04)

Tools: Python 3.12.3, `uv` 0.11, OpenJDK 21.0.12, Maven 3.9.11, git.

```bash
git clone https://github.com/Supervertaler/Supervertaler-Workbench.git localizelarge-app
```

```bash
cd localizelarge-app && git checkout f83e5203298aa3c120a1f77cd3705dd65d28c44c && git checkout -B main
```

```bash
git remote rename origin upstream && git remote set-url --push upstream DISABLED
```

The last command makes `upstream` read-only: a push to it fails.

Python environment:

```bash
uv venv -p 3.12 .venv
```

```bash
uv pip install -p .venv/bin/python -r requirements.txt pytest pytest-qt pytest-timeout
```

Qt needs `libEGL` even when it runs headless:

```bash
sudo apt-get install -y --no-install-recommends libegl1
```

Sidecar (the plan's `build.ps1` is the Windows wrapper around the same Maven call):

```bash
cd okapi-sidecar && mvn -B -q package -DskipTests
```

Tests, with a throwaway home folder so no real data is touched:

```bash
HOME=$(mktemp -d) QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -q --timeout=120 --continue-on-collection-errors
```

Running the app headless as root, at the base commit, also needs
`QTWEBENGINE_DISABLE_SANDBOX=1` and
`QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox --disable-gpu"`. This goes away when WebEngine is
removed in Phase 2.

Differences from the plan: JDK 21 instead of Temurin 17 (the sidecar still compiles for
Java 17), and `uv` instead of `pip`.

## Windows 10/11 x64 (the plan's target; not run yet)

1. Install Python 3.12 (64-bit), Temurin JDK 17, Maven and Git.
2. Clone and check out the commit as above.
3. Create the environment:

   ```powershell
   py -3.12 -m venv .venv
   ```

   ```powershell
   .venv\Scripts\python -m pip install -r requirements.txt pytest pytest-qt
   ```

4. Build the sidecar:

   ```powershell
   cd okapi-sidecar; .\build.ps1
   ```

5. Run the tests:

   ```powershell
   $env:QT_QPA_PLATFORM="offscreen"; .venv\Scripts\python -m pytest tests/
   ```

6. Start the app:

   ```powershell
   .venv\Scripts\python Supervertaler.py
   ```

Run every test with temporary `APPDATA` and `LOCALAPPDATA` values. Never point them at a
real Supervertaler folder.
