#!/usr/bin/env bash
set -euo pipefail

# Windows detection — native Windows shells (Git Bash, MSYS, Cygwin) won't work correctly
if [[ "$OSTYPE" == msys* || "$OSTYPE" == cygwin* || -n "${WINDIR:-}" ]]; then
  echo "Error: claude-code-tracker requires a Unix shell (macOS, Linux, or WSL)." >&2
  echo "On Windows, install WSL and run this from a WSL terminal:" >&2
  echo "  https://learn.microsoft.com/windows/wsl/install" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.claude/tracking"
SETTINGS="$HOME/.claude/settings.json"

echo "Installing claude-code-tracker..."

# Detect Homebrew install (SCRIPT_DIR is inside a Cellar path)
if [[ "$SCRIPT_DIR" == */Cellar/* ]]; then
  # Resolve stable opt path — survives brew upgrade (Homebrew maintains the symlink)
  FORMULA_NAME="$(echo "$SCRIPT_DIR" | sed -n 's|.*/Cellar/\([^/]*\)/.*|\1|p')"
  OPT_PREFIX="$(brew --prefix "$FORMULA_NAME" 2>/dev/null)" || OPT_PREFIX=""
  if [[ -z "$OPT_PREFIX" ]]; then
    echo "Error: could not resolve brew --prefix for $FORMULA_NAME" >&2
    exit 1
  fi
  HOOK_CMD="$OPT_PREFIX/libexec/src/stop-hook.sh"
  echo "Homebrew install detected — hook will point to $HOOK_CMD"
else
  # Direct copy for npm / git-clone installs
  mkdir -p "$INSTALL_DIR"
  rm -f "$INSTALL_DIR/"*.sh "$INSTALL_DIR/"*.py 2>/dev/null || true
  cp "$SCRIPT_DIR/src/"*.sh "$SCRIPT_DIR/src/"*.py "$INSTALL_DIR/"
  chmod +x "$INSTALL_DIR/"*.sh "$INSTALL_DIR/"*.py
  HOOK_CMD="$INSTALL_DIR/stop-hook.sh"
  echo "Scripts installed to $INSTALL_DIR"
fi

# Patch settings.json — add Stop hook if not already present
python3 - "$SETTINGS" "$HOOK_CMD" <<'PYEOF'
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

# Remove any existing stop-hook.sh entries (from npm or brew) and replace with current path
stop_hooks[:] = [
    g for g in stop_hooks
    if not any("stop-hook.sh" in h.get("command", "") for h in g.get("hooks", []))
]
stop_hooks.append({"hooks": [hook_entry]})

# SessionStart hook — same: remove old entries and replace
backfill_cmd = hook_cmd + " --backfill-only"
session_hooks = hooks.setdefault("SessionStart", [])
session_hooks[:] = [
    g for g in session_hooks
    if not any("stop-hook.sh" in h.get("command", "") for h in g.get("hooks", []))
]
session_hooks.append({"hooks": [{"type": "command", "command": backfill_cmd, "timeout": 60, "async": True}]})

# permissions.allow — clean old entries and add current
allow_entry = f"Bash({hook_cmd}*)"
perms = data.setdefault("permissions", {})
allow_list = perms.setdefault("allow", [])
allow_list[:] = [e for e in allow_list if "stop-hook.sh" not in e]
allow_list.append(allow_entry)

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

# Backfill historical sessions for the current project (skip for Homebrew installs)
if [[ "$SCRIPT_DIR" != */Cellar/* ]]; then
  PROJECT_ROOT="$PWD"
  while [[ "$PROJECT_ROOT" != "/" ]]; do
    [[ -d "$PROJECT_ROOT/.git" ]] && break
    PROJECT_ROOT="$(dirname "$PROJECT_ROOT")"
  done
  if [[ "$PROJECT_ROOT" != "/" ]]; then
    echo "Backfilling historical sessions..."
    python3 "$INSTALL_DIR/backfill.py" "$PROJECT_ROOT"
  fi
fi

echo "claude-code-tracker installed. Restart Claude Code to activate."
