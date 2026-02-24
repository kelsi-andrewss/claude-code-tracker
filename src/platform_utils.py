#!/usr/bin/env python3
"""
Cross-platform utilities for claude-code-tracker.
All OS-dependent path and command logic lives here so that individual
scripts can simply ``from platform_utils import ...``.
"""
import os
import sys
import subprocess
import shutil


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

def is_windows():
    """Return True if running on native Windows (not WSL)."""
    return sys.platform == "win32"


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def get_home_dir():
    """Return the user's home directory, cross-platform."""
    return os.path.expanduser("~")


def get_claude_dir():
    """Return ~/.claude as an absolute path."""
    return os.path.join(get_home_dir(), ".claude")


def get_tracking_install_dir():
    """Return ~/.claude/tracking as an absolute path."""
    return os.path.join(get_claude_dir(), "tracking")


def slugify_path(abs_path):
    """Convert an absolute path to a Claude Code project slug.

    Claude Code slugifies project paths by replacing ``/`` with ``-``.
    On Windows paths use ``\\`` so we first normalise to forward slashes,
    then apply the same replacement.  The drive-letter colon (e.g. ``C:``)
    is also stripped because Claude Code removes it before slugifying.

    Examples::

        /Users/me/project       -> -Users-me-project
        C:\\Users\\me\\project  -> C--Users-me-project
    """
    normalised = abs_path.replace("\\", "/")
    # Claude Code replaces the colon from Windows drive letters with "-" (C: -> C-)
    normalised = normalised.replace(":", "-")
    return normalised.replace("/", "-")


def get_transcripts_dir(project_root):
    """Return the Claude Code transcripts directory for *project_root*.

    Transcripts live in ``~/.claude/projects/<slug>/`` where *slug* is
    the project's absolute path with path separators replaced by ``-``.
    """
    slug = slugify_path(os.path.abspath(project_root))
    return os.path.join(get_home_dir(), ".claude", "projects", slug)


def find_git_root(start_dir=None):
    """Walk up from *start_dir* to find the nearest ``.git`` directory.

    Returns the git-root path, or ``None`` if the filesystem root is
    reached without finding one.  Works on every OS because it checks
    ``parent == current`` instead of comparing to ``/``.
    """
    root = os.path.abspath(start_dir or os.getcwd())
    while True:
        if os.path.exists(os.path.join(root, ".git")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            return None
        root = parent


# ---------------------------------------------------------------------------
# Python command helpers
# ---------------------------------------------------------------------------

def get_python_cmd():
    """Return the correct Python executable name for this platform.

    Windows typically ships ``python``; macOS / Linux use ``python3``.
    """
    if is_windows():
        candidates = ["python", "python3"]
    else:
        candidates = ["python3", "python"]
    for cmd in candidates:
        if shutil.which(cmd):
            return cmd
    return "python" if is_windows() else "python3"


def run_python_script(script_path, args=None, suppress_errors=True):
    """Run a Python script cross-platform.

    Replaces patterns like::

        os.system('python3 "script.py" args 2>/dev/null')
    """
    cmd = [get_python_cmd(), script_path]
    if args:
        cmd.extend(args)

    stderr = subprocess.DEVNULL if suppress_errors else None
    try:
        subprocess.run(cmd, stderr=stderr, check=False)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# File / browser helpers
# ---------------------------------------------------------------------------

def open_file_in_browser(file_path):
    """Open *file_path* in the default browser, with a correct ``file:`` URL.

    On Windows the path needs three leading slashes and forward-slash
    separators so that ``file:///C:/Users/…`` is produced instead of
    ``file://C:\\Users\\…``.
    """
    import webbrowser

    abs_path = os.path.abspath(file_path)
    if is_windows():
        url = "file:///" + abs_path.replace("\\", "/")
    else:
        url = "file://" + abs_path
    webbrowser.open(url)


def open_file_native(file_path):
    """Open *file_path* with the OS's native "open" command."""
    abs_path = os.path.abspath(file_path)
    if sys.platform == "darwin":
        subprocess.run(["open", abs_path], check=False)
    elif is_windows():
        os.startfile(abs_path)  # noqa: S606  — Windows-only API
    else:
        subprocess.run(
            ["xdg-open", abs_path],
            check=False,
            stderr=subprocess.DEVNULL,
        )
