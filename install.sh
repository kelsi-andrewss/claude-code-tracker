#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.claude/tracking"
SETTINGS="$HOME/.claude/settings.json"

echo "Installing claude-code-tracker..."

# Install scripts
mkdir -p "$INSTALL_DIR"

# Detect Homebrew install (SCRIPT_DIR is inside a Cellar path)
if [[ "$SCRIPT_DIR" == */Cellar/* ]]; then
  # Symlink scripts — avoids macOS provenance xattr issues on upgrade.
  # ln -sf fails if the target has com.apple.provenance (SIP-protected),
  # so create a temp symlink and mv -f (rename syscall bypasses SIP).
  for f in "$SCRIPT_DIR/src/"*.sh "$SCRIPT_DIR/src/"*.py; do
    dest="$INSTALL_DIR/$(basename "$f")"
    tmplink=$(mktemp -u "$INSTALL_DIR/.tmp.XXXXXX")
    ln -s "$f" "$tmplink"
    mv -f "$tmplink" "$dest"
  done
else
  # Direct copy for npm / git-clone installs
  rm -f "$INSTALL_DIR/"*.sh "$INSTALL_DIR/"*.py 2>/dev/null || true
  cp "$SCRIPT_DIR/src/"*.sh "$SCRIPT_DIR/src/"*.py "$INSTALL_DIR/"
  chmod +x "$INSTALL_DIR/"*.sh "$INSTALL_DIR/"*.py
fi

echo "Scripts installed to $INSTALL_DIR"

# Patch settings.json — add Stop hook if not already present
python3 - "$SETTINGS" "$INSTALL_DIR/stop-hook.sh" <<'PYEOF'
import sys, json, os

settings_file = sys.argv[1]
hook_cmd = sys.argv[2]

data = {}
if os.path.exists(settings_file):
    try:
        with open(settings_file) as f:
            data = json.load(f)
    except Exception:
        data = {}

hook_entry = {"type": "command", "command": hook_cmd, "timeout": 30, "async": True}
hooks = data.setdefault("hooks", {})
stop_hooks = hooks.setdefault("Stop", [])

# Check if already registered
for group in stop_hooks:
    for h in group.get("hooks", []):
        if h.get("command") == hook_cmd:
            print("Hook already registered.")
            sys.exit(0)

stop_hooks.append({"hooks": [hook_entry]})

os.makedirs(os.path.dirname(os.path.abspath(settings_file)), exist_ok=True)
with open(settings_file, 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
print("Hook registered in", settings_file)
PYEOF

# Patch ~/.claude/CLAUDE.md — add tracking instruction if not present
CLAUDE_MD="$HOME/.claude/CLAUDE.md"
MARKER="planning session ends without implementation"
if [ -f "$CLAUDE_MD" ] && grep -qF "$MARKER" "$CLAUDE_MD"; then
  echo "CLAUDE.md tracking instruction already present."
else
  cat >> "$CLAUDE_MD" <<'MDEOF'
- When a planning session ends without implementation (plan rejected, approach changed, or pure research), still write a tracking entry — mark it as architecture category and note what was decided against and why.
MDEOF
  echo "Tracking instruction added to $CLAUDE_MD"
fi

# Backfill historical sessions for the current project
PROJECT_ROOT="$PWD"
while [[ "$PROJECT_ROOT" != "/" ]]; do
  [[ -d "$PROJECT_ROOT/.git" ]] && break
  PROJECT_ROOT="$(dirname "$PROJECT_ROOT")"
done
if [[ "$PROJECT_ROOT" != "/" ]]; then
  echo "Backfilling historical sessions..."
  python3 "$INSTALL_DIR/backfill.py" "$PROJECT_ROOT"
fi

echo "claude-code-tracker installed. Restart Claude Code to activate."
