"""The About dialog and the facts it shows."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Optional

APP_NAME = "Localize Large"
WEBSITE = "localizelarge.com"
WEBSITE_URL = "https://localizelarge.com"
DOWNLOAD_URL = "https://localizelarge.com/download"
SUPPORT_EMAIL = "contact@localizelarge.com"
UPSTREAM_NAME = "Supervertaler Workbench"
UPSTREAM_VERSION = "1.10.376"
UPSTREAM_AUTHOR = "Michael Beijer"
ATTRIBUTION = (
    f"Based on {UPSTREAM_NAME} {UPSTREAM_VERSION} by {UPSTREAM_AUTHOR} (MIT License)"
)
LICENSE_NAME = "GPL-3.0-or-later"
LICENSES_FILE_NAME = "THIRD_PARTY_LICENSES.md"
ACCENT = "#0F766E"


def licenses_file() -> Path:
    """``THIRD_PARTY_LICENSES.md`` beside the app, in a build or in the source tree."""
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        for candidate in (exe_dir / LICENSES_FILE_NAME, exe_dir / "_internal" / LICENSES_FILE_NAME):
            if candidate.exists():
                return candidate
        return exe_dir / LICENSES_FILE_NAME
    return Path(__file__).resolve().parent.parent / LICENSES_FILE_NAME


# Credit asked for by the licence of the MQM typology (CC BY 4.0).
MQM_ATTRIBUTION = ("Quality categories and scoring: MQM Core typology and MQM scoring models "
                   "© The MQM Council (themqm.org), licensed under CC BY 4.0. "
                   "The MQM Council does not endorse this app.")


def about_html(version: str) -> str:
    link = f'style="color: {ACCENT}; text-decoration: none;"'
    return (
        f'<h2 style="text-align: center;">{APP_NAME} {version}</h2>'
        '<p style="text-align: center;">A translation tool for in-house localization teams, '
        "with built-in quality checks.</p>"
        f'<p style="text-align: center;">{ATTRIBUTION}</p>'
        f'<p style="text-align: center;">{MQM_ATTRIBUTION}</p>'
        '<p style="text-align: center;">'
        f'<b>Website:</b> <a href="{WEBSITE_URL}" {link}>{WEBSITE}</a><br>'
        f'<b>Support:</b> <a href="mailto:{SUPPORT_EMAIL}" {link}>{SUPPORT_EMAIL}</a><br>'
        f"<b>License:</b> {LICENSE_NAME}"
        "</p>"
    )


def show_licenses_dialog(parent=None) -> None:
    """Show ``THIRD_PARTY_LICENSES.md`` in a read-only window."""
    from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout

    dialog = QDialog(parent)
    dialog.setWindowTitle("Licenses")
    dialog.resize(760, 560)
    layout = QVBoxLayout(dialog)
    browser = QTextBrowser(dialog)
    browser.setOpenExternalLinks(False)
    path = licenses_file()
    try:
        browser.setMarkdown(path.read_text(encoding="utf-8"))
    except OSError:
        browser.setPlainText(f"The licenses file was not found:\n{path}")
    layout.addWidget(browser)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
    buttons.rejected.connect(dialog.reject)
    buttons.accepted.connect(dialog.accept)
    layout.addWidget(buttons)
    dialog.exec()


def open_download_page() -> None:
    """Open the download page in the default browser. The app makes no request."""
    from PyQt6.QtCore import QUrl
    from PyQt6.QtGui import QDesktopServices

    QDesktopServices.openUrl(QUrl(DOWNLOAD_URL))


def show_about_dialog(parent, version: str, copy_version_info: Optional[Callable[[], None]] = None) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

    dialog = QDialog(parent)
    dialog.setWindowTitle(f"About {APP_NAME}")
    dialog.setMinimumWidth(440)
    layout = QVBoxLayout(dialog)
    layout.setSpacing(10)
    layout.setContentsMargins(20, 20, 20, 20)

    text = QLabel(about_html(version))
    text.setObjectName("aboutText")
    text.setTextFormat(Qt.TextFormat.RichText)
    text.setOpenExternalLinks(True)
    text.setWordWrap(True)
    layout.addWidget(text)

    row = QHBoxLayout()
    licenses_btn = QPushButton("Licenses…")
    licenses_btn.setObjectName("aboutLicensesButton")
    licenses_btn.setToolTip(f"Show {LICENSES_FILE_NAME}")
    licenses_btn.clicked.connect(lambda: show_licenses_dialog(dialog))
    row.addWidget(licenses_btn)

    if copy_version_info is not None:
        copy_btn = QPushButton("Copy version info")
        copy_btn.setToolTip("Copy version and system information to the clipboard")
        copy_btn.clicked.connect(copy_version_info)
        row.addWidget(copy_btn)

    update_btn = QPushButton("Check for updates…")
    update_btn.setToolTip(f"Open {DOWNLOAD_URL} in your browser. The app itself sends nothing.")
    update_btn.clicked.connect(open_download_page)
    row.addWidget(update_btn)

    row.addStretch(1)
    close_btn = QPushButton("Close")
    close_btn.clicked.connect(dialog.accept)
    row.addWidget(close_btn)
    layout.addLayout(row)

    dialog.exec()
