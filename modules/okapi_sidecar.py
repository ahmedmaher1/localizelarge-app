"""
Localize Large Okapi Sidecar Client
===================================

Manages the lifecycle of the local Okapi sidecar process and provides
a clean Python API for document extraction, merge, TMX handling, and
SRX segmentation.

The sidecar is a small Java-based REST service (okapi-sidecar.jar) that
wraps Okapi Framework filters.  It runs on localhost and communicates
via HTTP – no files ever leave the user's machine.

Usage:
    sidecar = OkapiSidecar()
    sidecar.start()                         # starts Java process
    result = sidecar.extract_docx(path)     # extract segments
    sidecar.stop()                          # kill Java process

    # Or use as a context manager:
    with OkapiSidecar() as sidecar:
        result = sidecar.extract_docx(path)
"""

import atexit
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import requests
except ImportError:
    requests = None  # Will fail gracefully at runtime

logger = logging.getLogger(__name__)


class OkapiSidecarError(Exception):
    """Raised when the sidecar returns an error or is unreachable."""
    pass


class OkapiSidecar:
    """
    Client for the Localize Large Okapi Sidecar REST service.

    The sidecar runs as a local subprocess on 127.0.0.1 (never exposed
    to the network).  All document processing happens on the user's
    machine – nothing is sent over the internet.
    """

    STARTUP_TIMEOUT = 20  # seconds
    SHUTDOWN_TIMEOUT = 5  # seconds

    # Sidecar version this client expects to talk to (keep it in sync with
    # pom.xml and App.java).
    EXPECTED_VERSION = "0.2.0"

    # The sidecar answers only on the loopback address, on a free port chosen
    # for each session, and only to requests that carry this session's token.
    HOST = "127.0.0.1"
    TOKEN_HEADER = "X-LL-Token"
    TOKEN_ENV = "LL_SIDECAR_TOKEN"

    def __init__(self, port: Optional[int] = None,
                 sidecar_dir: Optional[str] = None):
        """
        Args:
            port:        TCP port for the sidecar. None (the default) picks a
                         free port each time the sidecar starts.
            sidecar_dir: Path to the directory containing the sidecar JAR
                         and bundled JRE.  If None, auto-detected relative
                         to the Localize Large installation.
        """
        self._fixed_port = port
        self.port = port or 0
        self.base_url = f"http://{self.HOST}:{self.port}"
        self._token = ""
        self._process: Optional[subprocess.Popen] = None
        self._started_by_us = False
        # Set by start(): True when the JAR that came up reports a version other
        # than EXPECTED_VERSION (the JAR needs rebuilding).
        self.version_mismatch = False
        self._http = self._new_session("")

        # Locate the sidecar directory
        if sidecar_dir:
            self.sidecar_dir = Path(sidecar_dir)
        else:
            self.sidecar_dir = self._find_sidecar_dir()

    @classmethod
    def _new_session(cls, token: str):
        """An HTTP session that sends the token and never uses a proxy: the
        sidecar is on this computer, so a system proxy must not see the files."""
        if requests is None:
            return None
        session = requests.Session()
        session.trust_env = False
        if token:
            session.headers[cls.TOKEN_HEADER] = token
        return session

    @classmethod
    def _free_port(cls) -> int:
        """A TCP port that is free on the loopback address right now."""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((cls.HOST, 0))
            return sock.getsockname()[1]

    # ═══════════════════════════════════════════════════════════════
    #  Lifecycle
    # ═══════════════════════════════════════════════════════════════

    def start(self) -> bool:
        """Start the sidecar process.  Returns True if started (or
        already running), False if the sidecar is not available.

        Each start uses a new free port and a new random token. A sidecar
        started by another program or another session is never reused and
        never stopped.
        """

        if requests is None:
            logger.error("'requests' package not installed – "
                         "cannot communicate with Okapi sidecar")
            return False

        if self.is_running():
            return True
        if self._process is not None:
            self.stop()

        # Find the JAR
        jar_path = self.sidecar_dir / "okapi-sidecar.jar"
        if not jar_path.exists():
            logger.warning("Okapi sidecar JAR not found at %s", jar_path)
            return False

        # Find Java
        java_path = self._find_java()
        if java_path is None:
            logger.warning("Java runtime not found – Okapi sidecar unavailable")
            return False

        import secrets
        self.port = self._fixed_port or self._free_port()
        self.base_url = f"http://{self.HOST}:{self.port}"
        self._token = secrets.token_urlsafe(32)
        self._http = self._new_session(self._token)

        # Launch the process. The token travels in the environment of the
        # child only; it is never written to a file, a log or the command line.
        cmd = [
            str(java_path),
            "-jar", str(jar_path),
            f"--port={self.port}"
        ]
        logger.info("Starting Okapi sidecar: %s", " ".join(cmd))
        child_env = dict(os.environ)
        child_env[self.TOKEN_ENV] = self._token

        try:
            self._process = subprocess.Popen(
                cmd,
                # The sidecar exits when this pipe closes, so it cannot
                # outlive the app even if the app is killed.
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(self.sidecar_dir),
                env=child_env,
                # Don't let the child inherit our console on Windows
                creationflags=(subprocess.CREATE_NO_WINDOW
                               if platform.system() == "Windows" else 0),
            )
            self._started_by_us = True
            # Drain the merged stdout/stderr pipe in a daemon thread.
            # Without this the OS pipe buffer (~64 KB on Windows) eventually
            # fills and the sidecar blocks on its next write – a latent
            # hang that's hard to diagnose without a console.
            if self._process.stdout is not None:
                threading.Thread(
                    target=self._drain_pipe,
                    args=(self._process.stdout,),
                    name="okapi-stdout-drain",
                    daemon=True,
                ).start()
            atexit.register(self.stop)
        except Exception as e:
            logger.error("Failed to start Okapi sidecar: %s", e)
            return False

        # Wait for the service to become ready
        if not self._wait_for_ready():
            logger.error("Okapi sidecar failed to start within %ds",
                         self.STARTUP_TIMEOUT)
            self.stop()
            return False

        logger.info("Okapi sidecar started on %s:%d (PID %d)",
                     self.HOST, self.port, self._process.pid)

        # Sanity check: confirm the freshly spawned sidecar matches the
        # version this Python client expects. If not, the JAR on disk is
        # out of date and the developer needs to rebuild it.
        actual_version = self.get_version()
        self.version_mismatch = bool(actual_version and actual_version != self.EXPECTED_VERSION)
        if self.version_mismatch:
            logger.warning(
                "Sidecar JAR reports v%s but client expects v%s – rebuild"
                " required (run okapi-sidecar/build.sh or build.ps1)",
                actual_version, self.EXPECTED_VERSION,
            )
        return True

    def stop(self):
        """Stop the sidecar process if we started it."""
        if self._process and self._started_by_us:
            logger.info("Stopping Okapi sidecar (PID %d)", self._process.pid)
            try:
                if self._process.stdin is not None:
                    self._process.stdin.close()
            except Exception:
                pass
            self._process.terminate()
            try:
                self._process.wait(timeout=self.SHUTDOWN_TIMEOUT)
            except subprocess.TimeoutExpired:
                logger.warning("Sidecar didn't stop gracefully – killing")
                self._process.kill()
                self._process.wait(timeout=2)
            self._process = None
            self._started_by_us = False
            self._token = ""
            self._http = self._new_session("")

    @staticmethod
    def _drain_pipe(pipe):
        """Read the sidecar's stdout/stderr line-by-line into the log.

        Runs on a daemon thread for the lifetime of the subprocess.
        Each line is forwarded through the stdlib ``logging`` module so
        it lands in the diagnostic log.
        """
        try:
            for raw in iter(pipe.readline, b""):
                if not raw:
                    break
                try:
                    text = raw.decode("utf-8", errors="replace").rstrip()
                except Exception:
                    text = repr(raw)
                if text:
                    logger.info("[sidecar] %s", text)
        except Exception:
            pass
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    def is_running(self) -> bool:
        """True when the sidecar this client started is alive and answering."""
        if requests is None or self._process is None:
            return False
        if self._process.poll() is not None:
            return False
        try:
            resp = self._http.get(f"{self.base_url}/health", timeout=2)
            return resp.status_code == 200
        except (requests.ConnectionError, requests.Timeout):
            return False

    def get_version(self) -> Optional[str]:
        """Return the sidecar version string, or None if not running."""
        if self._process is None:
            return None
        try:
            resp = self._http.get(f"{self.base_url}/health", timeout=2)
            if resp.status_code == 200:
                return resp.json().get("version")
        except Exception:
            pass
        return None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    # ═══════════════════════════════════════════════════════════════
    #  Document extraction
    # ═══════════════════════════════════════════════════════════════

    def extract(self, file_path: str,
                source_lang: str = "en",
                target_lang: str = "fr",
                segment: bool = True,
                options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Extract segments from a document file.

        Args:
            file_path:   Path to the document (DOCX, XLSX, HTML, etc.)
            source_lang: Source language code (e.g., "nl", "en")
            target_lang: Target language code (e.g., "en", "fr")
            segment:     Apply SRX segmentation (default True)
            options:     Optional per-file-type import toggles (dict of
                         booleans, e.g. {"word_comments": False,
                         "word_hidden": False}). Absent keys fall back to
                         the sidecar's Localize Large defaults. See
                         FilterService.applyFilterParameters for the keys.

        Returns:
            Dict with keys: filename, sourceLang, targetLang, filterUsed,
            textUnitCount, segmentCount, segments (list of dicts with
            id, segmentIndex, source, type, isReferent, subDocument).
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        data = {
            'source_lang': source_lang,
            'target_lang': target_lang,
            'segment': str(segment).lower(),
        }
        if options:
            data['options'] = json.dumps(options)

        with open(file_path, 'rb') as f:
            resp = self._http.post(
                f"{self.base_url}/extract",
                files={'file': (file_path.name, f)},
                data=data,
                timeout=120,
            )

        return self._handle_response(resp)

    def extract_docx(self, file_path: str,
                     source_lang: str = "en",
                     target_lang: str = "fr",
                     segment: bool = True,
                     options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Convenience alias for extract() with DOCX files."""
        return self.extract(file_path, source_lang, target_lang, segment, options)

    # ═══════════════════════════════════════════════════════════════
    #  Document merge (create translated document)
    # ═══════════════════════════════════════════════════════════════

    def merge(self, original_path: str,
              translations: List[Dict[str, Any]],
              source_lang: str = "en",
              target_lang: str = "fr",
              output_path: Optional[str] = None,
              options: Optional[Dict[str, Any]] = None) -> str:
        """
        Create a translated version of the original document.

        Args:
            original_path: Path to the original (untranslated) document.
            translations:  List of dicts with keys: id, segmentIndex,
                           translation.
            source_lang:   Source language code.
            target_lang:   Target language code.
            output_path:   Where to save the translated file.  If None,
                           auto-generates a path.
            options:       Optional per-file-type import toggles. MUST match
                           the options used at extract time so the text-unit
                           set lines up for the round-trip.

        Returns:
            Path to the saved translated document.
        """
        original = Path(original_path)
        if not original.exists():
            raise FileNotFoundError(f"Original file not found: {original}")

        if output_path is None:
            stem = original.stem
            suffix = original.suffix
            output_path = str(original.parent / f"{stem}_{target_lang}{suffix}")

        data = {
            'translations': json.dumps(translations),
            'source_lang': source_lang,
            'target_lang': target_lang,
        }
        if options:
            data['options'] = json.dumps(options)

        with open(original, 'rb') as f:
            resp = self._http.post(
                f"{self.base_url}/merge",
                files={'original': (original.name, f)},
                data=data,
                timeout=120,
            )

        if resp.status_code != 200:
            self._handle_response(resp)  # will raise

        # Save the binary response
        with open(output_path, 'wb') as out:
            out.write(resp.content)

        logger.info("Merged document saved to %s", output_path)
        return output_path

    # ═══════════════════════════════════════════════════════════════
    #  TMX handling
    # ═══════════════════════════════════════════════════════════════

    def read_tmx(self, tmx_path: str) -> Dict[str, Any]:
        """
        Parse a TMX file and return all translation units.

        Returns:
            Dict with keys: filename, tuCount, translationUnits (list of
            dicts with id, source, targets {lang: text}, properties).
        """
        tmx_path = Path(tmx_path)
        if not tmx_path.exists():
            raise FileNotFoundError(f"TMX file not found: {tmx_path}")

        with open(tmx_path, 'rb') as f:
            resp = self._http.post(
                f"{self.base_url}/tmx/read",
                files={'file': (tmx_path.name, f)},
                timeout=120,
            )

        return self._handle_response(resp)

    def validate_tmx(self, tmx_path: str) -> Dict[str, Any]:
        """
        Validate a TMX file and return a report of any issues.

        Returns:
            Dict with keys: filename, valid (bool), tuCount, languages,
            emptySourceCount, emptyTargetCount, issues (list of dicts
            with level, message, tuIndex).
        """
        tmx_path = Path(tmx_path)
        if not tmx_path.exists():
            raise FileNotFoundError(f"TMX file not found: {tmx_path}")

        with open(tmx_path, 'rb') as f:
            resp = self._http.post(
                f"{self.base_url}/tmx/validate",
                files={'file': (tmx_path.name, f)},
                timeout=60,
            )

        return self._handle_response(resp)

    # ═══════════════════════════════════════════════════════════════
    #  SRX Segmentation
    # ═══════════════════════════════════════════════════════════════

    def segment(self, text: str, language: str = "en") -> List[str]:
        """
        Segment text using Okapi's SRX engine.

        Args:
            text:     The text to segment.
            language: Language code for segmentation rules.

        Returns:
            List of sentence-level segments.
        """
        resp = self._http.post(
            f"{self.base_url}/segment",
            json={'text': text, 'language': language},
            timeout=30,
        )
        data = self._handle_response(resp)
        return data.get("segments", [])

    # ═══════════════════════════════════════════════════════════════
    #  Supported formats
    # ═══════════════════════════════════════════════════════════════

    def get_supported_filters(self) -> List[Dict[str, str]]:
        """Return list of supported file format dicts."""
        resp = self._http.get(f"{self.base_url}/filters", timeout=5)
        return self._handle_response(resp)

    # ═══════════════════════════════════════════════════════════════
    #  Internal helpers
    # ═══════════════════════════════════════════════════════════════

    def _handle_response(self, resp) -> Any:
        """Parse JSON response and raise on errors."""
        if resp.status_code != 200:
            try:
                data = resp.json()
                msg = data.get("message", f"HTTP {resp.status_code}")
            except Exception:
                msg = f"HTTP {resp.status_code}: {resp.text[:500]}"
            raise OkapiSidecarError(msg)

        data = resp.json()
        if isinstance(data, dict) and data.get("error"):
            raise OkapiSidecarError(data.get("message", "Unknown error"))
        return data

    def _wait_for_ready(self) -> bool:
        """Poll the health endpoint until the sidecar is ready."""
        deadline = time.time() + self.STARTUP_TIMEOUT
        while time.time() < deadline:
            # Check if the process died
            if self._process and self._process.poll() is not None:
                logger.error("Sidecar process exited with code %d",
                             self._process.returncode)
                return False
            try:
                resp = self._http.get(f"{self.base_url}/health", timeout=1)
                if resp.status_code == 200:
                    return True
            except (requests.ConnectionError, requests.Timeout):
                pass
            time.sleep(0.2)
        return False

    def _find_sidecar_dir(self) -> Path:
        """Locate the sidecar directory relative to the installation."""
        # Check several locations in order of priority:
        candidates = []

        # 1. Next to the main script / frozen exe
        if getattr(sys, 'frozen', False):
            # Running as compiled exe (PyInstaller)
            app_dir = Path(sys.executable).parent

            # PyInstaller --onedir places bundled data files under
            # _internal/ next to the exe (or inside sys._MEIPASS for
            # --onefile). Both candidates need checking before falling
            # back to the EXE-adjacent layout that source builds use.
            meipass = getattr(sys, '_MEIPASS', None)
            if meipass:
                candidates.append(Path(meipass) / "okapi-sidecar")
            candidates.append(app_dir / "_internal" / "okapi-sidecar")
        else:
            # Running from source
            app_dir = Path(__file__).parent.parent

        candidates.append(app_dir / "okapi-sidecar")
        candidates.append(app_dir / "okapi-sidecar" / "dist")
        candidates.append(app_dir / "okapi-sidecar" / "target")

        for candidate in candidates:
            jar = candidate / "okapi-sidecar.jar"
            if jar.exists():
                return candidate

        # Fallback: return first existing directory even without JAR
        for candidate in candidates:
            if candidate.exists():
                return candidate

        # Default to the source-tree location even if it doesn't exist yet
        return app_dir / "okapi-sidecar"

    def is_installed(self) -> bool:
        """True when the sidecar JAR can be found on disk.

        Distinct from ``is_running()`` – the JAR may exist but the JVM
        not yet be launched. ``start()`` returns False if not installed.
        """
        return (self.sidecar_dir / "okapi-sidecar.jar").exists()

    def _find_java(self) -> Optional[Path]:
        """Locate a Java runtime.  Prefers the bundled JRE."""
        # 1. Bundled JRE in the sidecar directory
        if platform.system() == "Windows":
            bundled = self.sidecar_dir / "jre" / "bin" / "java.exe"
        else:
            bundled = self.sidecar_dir / "jre" / "bin" / "java"

        if bundled.exists():
            return bundled

        # 2. JAVA_HOME environment variable
        java_home = os.environ.get("JAVA_HOME")
        if java_home:
            java_bin = Path(java_home) / "bin" / (
                "java.exe" if platform.system() == "Windows" else "java")
            if java_bin.exists():
                return java_bin

        # 3. java on PATH
        java_on_path = shutil.which("java")
        if java_on_path:
            return Path(java_on_path)

        return None

    @property
    def is_available(self) -> bool:
        """Check if the sidecar infrastructure is present (JAR + Java)."""
        jar = self.sidecar_dir / "okapi-sidecar.jar"
        return jar.exists() and self._find_java() is not None

    def needs_system_java_install(self) -> bool:
        """True on a development machine (not Windows) where no Java is found.

        The Windows build ships its own Java runtime, so this is always False
        there.
        """
        if platform.system() == "Windows":
            return False
        return self._find_java() is None
