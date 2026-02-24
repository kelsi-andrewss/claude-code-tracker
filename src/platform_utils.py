"""Cross-platform utility helpers for claude-tracker."""
import os
import sys
import subprocess

def get_transcripts_dir():
    """Return the Claude transcripts directory for the current platform."""
    if sys.platform == 'win32':
        appdata = os.environ.get('APPDATA', '')
        return os.path.join(appdata, 'Claude', 'claude_code', 'transcripts')
    elif sys.platform == 'darwin':
        home = os.path.expanduser('~')
        return os.path.join(home, 'Library', 'Application Support', 'Claude', 'claude_code', 'transcripts')
    else:
        home = os.path.expanduser('~')
        return os.path.join(home, '.config', 'Claude', 'claude_code', 'transcripts')

def slugify_path(path):
    """Convert an absolute path to a slug suitable for use as a directory name.
    Handles Windows drive letters and backslashes."""
    # Normalize separators
    slug = path.replace('\\', '/').replace('/', '-')
    # Remove drive letter colon on Windows (e.g. C: -> C)
    slug = slug.replace(':', '')
    # Strip leading/trailing dashes
    slug = slug.strip('-')
    return slug

def open_file(path):
    """Open a file with the default system application."""
    if sys.platform == 'win32':
        os.startfile(path)
    elif sys.platform == 'darwin':
        subprocess.run(['open', path])
    else:
        subprocess.run(['xdg-open', path])
