#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.claude/tracking"
SETTINGS="$HOME/.claude/settings.json"

echo "Uninstalling claude-code-tracker..."

# Detect Homebrew install
if [[ "$SCRIPT_DIR" == */Cellar/* ]]; then
  FORMULA_NAME="$(echo "$SCRIPT_DIR" | sed -n 's|.*/Cellar/\([^/]*\)/.*|\1|p')"
  OPT_PREFIX="$(brew --prefix "$FORMULA_NAME" 2>/dev/null)" || OPT_PREFIX=""
  HOOK_CMD="${OPT_PREFIX:+$OPT_PREFIX/libexec/src/stop-hook.sh}"
  echo "Homebrew install detected — skipping script removal from $INSTALL_DIR"
else
  HOOK_CMD="$INSTALL_DIR/stop-hook.sh"
  # Remove scripts
  if [[ -d "$INSTALL_DIR" ]]; then
      rm -f "$INSTALL_DIR/"*.sh "$INSTALL_DIR/"*.py
      echo "Scripts removed from $INSTALL_DIR"
  else
      echo "Nothing to remove at $INSTALL_DIR"
  fi
fi

# Remove hook entry from settings.json
if [[ -f "$SETTINGS" ]] && [[ -n "$HOOK_CMD" ]]; then
    python3 - "$SETTINGS" "$HOOK_CMD" <<'PYEOF'
import sys, json, os

settings_file = sys.argv[1]
hook_cmd = sys.argv[2]

try:
    with open(settings_file) as f:
        data = json.load(f)
except Exception:
    sys.exit(0)

hooks = data.get("hooks", {})
stop_hooks = hooks.get("Stop", [])

new_stop_hooks = []
removed = False
for group in stop_hooks:
    new_group_hooks = [h for h in group.get("hooks", []) if h.get("command") != hook_cmd]
    if len(new_group_hooks) < len(group.get("hooks", [])):
        removed = True
    if new_group_hooks:
        new_stop_hooks.append({"hooks": new_group_hooks})
    elif not removed:
        new_stop_hooks.append(group)

if removed:
    hooks["Stop"] = new_stop_hooks
    if not hooks["Stop"]:
        del hooks["Stop"]
    if not hooks:
        del data["hooks"]
    with open(settings_file, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
    print("Hook removed from", settings_file)
else:
    print("Hook not found in", settings_file)
PYEOF
fi

echo "claude-code-tracker uninstalled."
