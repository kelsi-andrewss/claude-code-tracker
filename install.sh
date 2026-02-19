#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.claude/tracking"
SETTINGS="$HOME/.claude/settings.json"

echo "Installing claude-code-tracker..."

# Copy scripts
mkdir -p "$INSTALL_DIR"
cp "$SCRIPT_DIR/src/"*.sh "$SCRIPT_DIR/src/"*.py "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/"*.sh

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

echo "claude-code-tracker installed. Restart Claude Code to activate."
