"""
Platform Helpers for Localize Large
===================================
Cross-platform utilities for file operations, window management,
subprocess flags, global hotkeys, and keystroke automation.

Replaces scattered platform-specific code with a single, consistent API.
"""

import sys
import os
import subprocess
import shutil
import contextlib
import time
from pathlib import Path
from typing import Optional, Callable, Dict, List


# ---------------------------------------------------------------------------
# Platform detection constants
# ---------------------------------------------------------------------------
IS_WINDOWS = sys.platform == 'win32'
IS_MACOS = sys.platform == 'darwin'
IS_LINUX = sys.platform.startswith('linux')


# ---------------------------------------------------------------------------
# Cross-platform file/folder opening
# ---------------------------------------------------------------------------
def open_file(path: str) -> bool:
    """Open a file with the system's default application.

    Cross-platform replacement for os.startfile().
    Returns True on success, False on failure.
    """
    try:
        path_str = str(path)
        if IS_WINDOWS:
            os.startfile(path_str)
        elif IS_MACOS:
            subprocess.run(['open', path_str], check=True)
        else:
            subprocess.run(['xdg-open', path_str], check=True)
        return True
    except Exception as e:
        print(f"[platform_helpers] Failed to open file {path}: {e}")
        return False


def open_folder(path: str) -> bool:
    """Open a folder in the system file manager.

    If *path* is a file, opens its containing folder.
    """
    path_obj = Path(path)
    folder = path_obj.parent if path_obj.is_file() else path_obj
    return open_file(str(folder))


def open_folder_and_select(path: str) -> bool:
    """Open a folder in the file manager and highlight/select the given file.

    Falls back to open_folder() on unsupported platforms.
    """
    try:
        path_str = str(path)
        if IS_WINDOWS:
            subprocess.run(['explorer', '/select,', path_str])
            return True
        elif IS_MACOS:
            subprocess.run(['open', '-R', path_str])
            return True
        else:
            # xdg-open on the parent folder (no select support)
            return open_folder(path_str)
    except Exception as e:
        print(f"[platform_helpers] Failed to open folder for {path}: {e}")
        return False


# ---------------------------------------------------------------------------
# Cross-platform subprocess creation flags
# ---------------------------------------------------------------------------
def get_hidden_subprocess_flags() -> dict:
    """Return subprocess kwargs to hide the console window on Windows.

    Usage::

        subprocess.Popen([...], **get_hidden_subprocess_flags())
    """
    if IS_WINDOWS and hasattr(subprocess, 'CREATE_NO_WINDOW'):
        return {'creationflags': subprocess.CREATE_NO_WINDOW}
    return {}


@contextlib.contextmanager
def hide_subprocess_console_windows():
    """Context manager that suppresses console flashes from any subprocess
    spawned by code running inside the ``with`` block on Windows.

    Wraps ``subprocess.Popen`` so any process started while the manager is
    active gets ``CREATE_NO_WINDOW`` added to its creationflags. Restored
    on exit. No-op on non-Windows platforms.

    Use this when calling third-party libraries that internally spawn
    helpers via ``subprocess.run([...])`` without giving us a way to pass
    creationflags ourselves – e.g. OpenAI's whisper library shelling out
    to ffmpeg for audio decoding. With Localize Large running console-less
    (Supervertaler.exe / pythonw.exe), every such helper would otherwise
    flash a black cmd window for ~100 ms.

    Usage::

        with hide_subprocess_console_windows():
            result = whisper_model.transcribe(audio_path)
    """
    if not (IS_WINDOWS and hasattr(subprocess, "CREATE_NO_WINDOW")):
        yield
        return

    _orig_popen = subprocess.Popen
    _no_window = subprocess.CREATE_NO_WINDOW

    class _NoFlashPopen(_orig_popen):
        def __init__(self, *args, **kwargs):
            kwargs["creationflags"] = (kwargs.get("creationflags", 0) or 0) | _no_window
            super().__init__(*args, **kwargs)

    subprocess.Popen = _NoFlashPopen
    try:
        yield
    finally:
        subprocess.Popen = _orig_popen


# ---------------------------------------------------------------------------
# Cross-platform window activation
# ---------------------------------------------------------------------------
def activate_window_by_title(title: str) -> bool:
    """Best-effort attempt to bring a window with *title* to the foreground.

    Returns True if the operation was attempted (not guaranteed to succeed).
    On Windows we fall back to Qt's own raise/activate methods via the caller.
    """
    try:
        if IS_WINDOWS:
            # Use ctypes to find and activate the window.
            # Plain SetForegroundWindow fails when our app is in the background
            # (Windows prevents background apps from stealing focus).  The
            # workaround is AttachThreadInput: temporarily attach our thread to
            # the foreground window's thread so the OS treats our call as coming
            # from the foreground process.
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            EnumWindows = user32.EnumWindows
            GetWindowTextW = user32.GetWindowTextW
            GetWindowTextLengthW = user32.GetWindowTextLengthW
            IsWindowVisible = user32.IsWindowVisible
            SetForegroundWindow = user32.SetForegroundWindow
            ShowWindow = user32.ShowWindow
            GetForegroundWindow = user32.GetForegroundWindow
            GetWindowThreadProcessId = user32.GetWindowThreadProcessId
            GetCurrentThreadId = kernel32.GetCurrentThreadId
            AttachThreadInput = user32.AttachThreadInput
            BringWindowToTop = user32.BringWindowToTop
            SW_RESTORE = 9
            SW_SHOW = 5

            WNDENUMPROC = ctypes.WINFUNCTYPE(
                ctypes.c_bool, wintypes.HWND, wintypes.LPARAM
            )
            target_hwnd = None

            def _enum_cb(hwnd, _lparam):
                nonlocal target_hwnd
                if IsWindowVisible(hwnd):
                    length = GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        GetWindowTextW(hwnd, buf, length + 1)
                        if title.lower() in buf.value.lower():
                            target_hwnd = hwnd
                            return False  # stop enumeration
                return True

            EnumWindows(WNDENUMPROC(_enum_cb), 0)
            if target_hwnd:
                # Attach to the foreground thread so SetForegroundWindow succeeds
                fg_hwnd = GetForegroundWindow()
                fg_thread = GetWindowThreadProcessId(fg_hwnd, None)
                our_thread = GetCurrentThreadId()
                attached = False
                if fg_thread != our_thread:
                    attached = AttachThreadInput(fg_thread, our_thread, True)

                ShowWindow(target_hwnd, SW_RESTORE)
                BringWindowToTop(target_hwnd)
                SetForegroundWindow(target_hwnd)

                if attached:
                    AttachThreadInput(fg_thread, our_thread, False)
                return True
            return False

        elif IS_MACOS:
            subprocess.run(
                ['osascript', '-e',
                 f'tell application "System Events" to set frontmost of '
                 f'(first process whose name contains "{title}") to true'],
                capture_output=True
            )
            return True

        else:
            # Linux – try wmctrl, then xdotool
            wmctrl = shutil.which('wmctrl')
            if wmctrl:
                subprocess.run([wmctrl, '-a', title], capture_output=True)
                return True
            xdotool = shutil.which('xdotool')
            if xdotool:
                subprocess.run(
                    [xdotool, 'search', '--name', title, 'windowactivate'],
                    capture_output=True
                )
                return True
            return False

    except Exception as e:
        print(f"[platform_helpers] Window activation failed: {e}")
        return False


def get_foreground_window():
    """Return an opaque handle for the current foreground window.

    On Windows returns HWND (int), on macOS/Linux returns the window title
    (str) or None if detection fails.  Pass the result to
    ``activate_foreground_window()`` to restore focus later.
    """
    try:
        if IS_WINDOWS:
            import ctypes
            return ctypes.windll.user32.GetForegroundWindow()
        elif IS_MACOS:
            result = subprocess.run(
                ['osascript', '-e',
                 'tell application "System Events" to get name of '
                 'first process whose frontmost is true'],
                capture_output=True, text=True
            )
            name = result.stdout.strip()
            return name if name else None
        else:
            xdotool = shutil.which('xdotool')
            if xdotool:
                result = subprocess.run(
                    [xdotool, 'getactivewindow'], capture_output=True, text=True
                )
                wid = result.stdout.strip()
                return wid if wid else None
            return None
    except Exception:
        return None


def activate_foreground_window(handle):
    """Re-activate a window previously captured by ``get_foreground_window()``.

    Uses the same AttachThreadInput trick on Windows for reliable activation.
    Does NOT call ShowWindow(SW_RESTORE) – that would un-maximize a maximized
    window.  The target window is already visible; we just need to give it focus.
    """
    if handle is None:
        return False
    try:
        if IS_WINDOWS:
            import ctypes
            import time
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            SW_RESTORE = 9
            VK_MENU = 0x12          # ALT
            KEYEVENTF_KEYUP = 0x0002

            def _is_foreground():
                # Both values come from GetForegroundWindow with ctypes' default
                # (signed 32-bit) marshalling, so they compare consistently.
                return user32.GetForegroundWindow() == handle

            # Already focused? Nothing to do.
            if _is_foreground():
                return True

            # Un-minimize ONLY if the target is minimized – never SW_RESTORE an
            # already-visible window, which would un-maximize a maximized editor.
            try:
                if user32.IsIconic(handle):
                    user32.ShowWindow(handle, SW_RESTORE)
            except Exception:
                pass

            our_thread = kernel32.GetCurrentThreadId()

            # Windows silently refuses SetForegroundWindow from a background
            # process under the foreground-lock timeout / a failed attach /
            # timing. So attempt it, VERIFY the switch actually took, and retry
            # with escalating nudges. This replaces the old fire-once-and-always-
            # return-True behaviour that made intermittent paste-into-nowhere
            # failures invisible to the caller.
            for attempt in range(3):
                fg_hwnd = user32.GetForegroundWindow()
                fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)
                attached = False
                if fg_thread and fg_thread != our_thread:
                    attached = user32.AttachThreadInput(fg_thread, our_thread, True)

                # On retries, a stray ALT tap releases the foreground lock so the
                # OS honours SetForegroundWindow from the background. (Benign for
                # the target app; the key is pressed and released immediately.)
                if attempt > 0:
                    try:
                        user32.keybd_event(VK_MENU, 0, 0, 0)
                        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
                    except Exception:
                        pass

                user32.BringWindowToTop(handle)
                user32.SetForegroundWindow(handle)

                if attached:
                    user32.AttachThreadInput(fg_thread, our_thread, False)

                if _is_foreground():
                    return True
                time.sleep(0.03)  # let the async switch settle, then re-check

            # Honestly report failure so the caller can react (e.g. retry the
            # whole paste) instead of firing Ctrl+V into nowhere.
            return _is_foreground()

        elif IS_MACOS:
            # handle is the process name
            subprocess.run(
                ['osascript', '-e',
                 f'tell application "System Events" to set frontmost of '
                 f'(first process whose name is "{handle}") to true'],
                capture_output=True
            )
            return True

        else:
            # handle is xdotool window ID
            xdotool = shutil.which('xdotool')
            if xdotool:
                subprocess.run(
                    [xdotool, 'windowactivate', str(handle)],
                    capture_output=True
                )
                return True
            return False

    except Exception as e:
        print(f"[platform_helpers] activate_foreground_window failed: {e}")
        return False
