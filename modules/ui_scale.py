"""
ui_scale.py – global UI font-scale helper for modules with hardcoded stylesheet sizes.

The main app exposes a `global_ui_font_scale` percent (Settings → AI Settings) that
ThemeManager uses to scale most of the UI. Some modules – notably the floating Sidekick
and the clipboard history – build their UI from hand-written stylesheets with hardcoded
`font-size: Xpt` values, which bypass ThemeManager and Qt's app-level QFont and so stay
small even when the slider is increased.

This helper gives those modules a way to participate in the global scale:

    from modules.ui_scale import scaled_pt
    label.setStyleSheet(f"font-size: {scaled_pt(9):.1f}pt; color: #555;")

The scale is read from the user's settings.json once and cached, so calls are cheap.
After the user changes the slider, the main app calls `refresh_ui_font_scale()` to
invalidate the cache; widgets constructed after that read the new value. (Already-
constructed Sidekick / clipboard widgets need to be re-opened to pick up the change –
acceptable trade-off for not having to wire a Qt signal through these modules.)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

_DEFAULT_SCALE = 100
_cached_scale: Optional[int] = None


def get_ui_font_scale() -> int:
    """Return the current global UI font scale as a percent (e.g. 100, 125, 150)."""
    global _cached_scale
    if _cached_scale is None:
        _cached_scale = _read_scale_from_disk()
    return _cached_scale


def refresh_ui_font_scale() -> int:
    """Force a re-read of the scale from disk. Call after Settings has changed it."""
    global _cached_scale
    _cached_scale = _read_scale_from_disk()
    return _cached_scale


def scaled_pt(base_pt: float) -> float:
    """Return base_pt multiplied by the current scale percent.

    Example: at 125% scale, scaled_pt(8) -> 10.0. Use in f-strings:
        f"font-size: {scaled_pt(8):.1f}pt"
    """
    return base_pt * get_ui_font_scale() / 100.0


# ── Internals ──────────────────────────────────────────────────────────────


def _user_data_path() -> Path:
    """The settings root (localizelarge.paths owns it)."""
    from localizelarge import paths
    return paths.settings_root()


def _read_scale_from_disk() -> int:
    # Unified settings file lives at <user_data>/workbench/settings/settings.json
    # (matches Supervertaler._get_unified_settings_path). Older installs may
    # also have a top-level settings.json from the pre-unified layout, so fall
    # back to that if the unified file isn't there.
    candidates = [
        _user_data_path() / "workbench" / "settings" / "settings.json",
        _user_data_path() / "settings.json",
    ]
    for settings_path in candidates:
        try:
            if not settings_path.exists():
                continue
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            general = data.get("general", {})
            scale = general.get("global_ui_font_scale",
                                general.get("settings_ui_font_scale", _DEFAULT_SCALE))
            scale_int = int(scale)
            if scale_int < 50 or scale_int > 300:
                return _DEFAULT_SCALE
            return scale_int
        except Exception:
            continue
    return _DEFAULT_SCALE
