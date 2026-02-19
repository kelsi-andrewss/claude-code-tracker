#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="$HOME/.claude/tracking"
SETTINGS="$HOME/.claude/settings.json"
HOOK_CMD="$INSTALL_DIR/stop-hook.sh"

echo "Uninstalling claude-code-tracker..."

# Remove scripts
if [[ -d "$INSTALL_DIR" ]]; then
    rm -f "$INSTALL_DIR/"*.sh "$INSTALL_DIR/"*.py
    echo "Scripts removed from $INSTALL_DIR"
else
    echo "Nothing to remove at $INSTALL_DIR"
fi

# Remove hook entry from settings.json
if [[ -f "$SETTINGS" ]]; then
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
