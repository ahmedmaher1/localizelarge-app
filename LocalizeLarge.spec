# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Localize Large (Windows, one folder, no console, no UPX).
# Build with scripts/build_release.ps1, which also adds the Java runtime.

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []

# Packages whose data files or lazily imported sub-modules PyInstaller's static
# analysis misses. collect_all brings the whole package.
for package in (
    "openai", "anthropic", "httpx", "httpcore", "anyio", "h11", "sniffio", "distro",
    "pydantic", "pydantic_core", "jiter", "certifi",
    "docx", "openpyxl", "lxml",
    "spellchecker", "spylls",
    "jsonschema", "jsonschema_specifications", "referencing", "rpds",
    "rapidfuzz", "markitdown", "magika",
):
    try:
        d, b, h = collect_all(package)
    except Exception:
        continue
    datas += d
    binaries += b
    hiddenimports += h

datas += [
    ("pyproject.toml", "."),
    ("LICENSE", "."),
    ("NOTICE", "."),
    ("THIRD_PARTY_LICENSES.md", "."),
    ("CHANGELOG.md", "."),
    ("assets", "assets"),
    ("translations", "translations"),
    ("modules/pricing.json", "modules"),
    ("localizelarge/data", "localizelarge/data"),
    ("okapi-sidecar/dist/okapi-sidecar.jar", "okapi-sidecar"),
]

a = Analysis(
    ["Supervertaler.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + ["PyQt6.QtSvg", "PyQt6.QtPrintSupport"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Not part of Localize Large v1. None of these may be in the build.
        "PyQt6.QtWebEngineWidgets", "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineQuick",
        "PyQt6.QtWebChannel", "PyQt6.QtWebSockets",
        "PyQt6.QtMultimedia", "PyQt6.QtMultimediaWidgets", "PyQt6.QtBluetooth", "PyQt6.QtNfc",
        "PyQt6.QtPositioning", "PyQt6.QtSensors", "PyQt6.QtSerialPort", "PyQt6.QtQuick",
        "PyQt6.QtQuick3D", "PyQt6.QtQuickWidgets", "PyQt6.QtQml", "PyQt6.Qt3DCore",
        "PyQt6.QtCharts", "PyQt6.QtDataVisualization", "PyQt6.QtDesigner", "PyQt6.QtHelp",
        "PyQt6.QtRemoteObjects", "PyQt6.QtSql", "PyQt6.QtTest", "PyQt6.QtTextToSpeech",
        "PyQt6.QtPdf", "PyQt6.QtPdfWidgets", "PyQt6.QtSpatialAudio", "PyQt6.QtStateMachine",
        "fitz", "pymupdf", "vosk", "sounddevice", "boto3", "botocore", "deepl", "pynput", "ahk",
        "google.generativeai",
        "PyQt5", "PySide2", "PySide6", "tkinter",
        "pytest", "pytestqt", "pyflakes",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LocalizeLarge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon="assets/icon.ico",
    version="scripts/version_info.txt",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="LocalizeLarge",
)
