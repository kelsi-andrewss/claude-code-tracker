#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INPUT="$(cat)"

# Prevent loops
STOP_ACTIVE="$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('stop_hook_active', False))" 2>/dev/null || echo "False")"
if [[ "$STOP_ACTIVE" == "True" ]]; then exit 0; fi

# Extract fields
CWD="$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null || true)"
TRANSCRIPT="$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('transcript_path',''))" 2>/dev/null || true)"
SESSION_ID="$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null || true)"

if [[ -z "$CWD" || -z "$TRANSCRIPT" || ! -f "$TRANSCRIPT" ]]; then exit 0; fi

# Find project root (walk up to .git)
PROJECT_ROOT="$CWD"
while [[ "$PROJECT_ROOT" != "/" ]]; do
  [[ -d "$PROJECT_ROOT/.git" ]] && break
  PROJECT_ROOT="$(dirname "$PROJECT_ROOT")"
done
if [[ "$PROJECT_ROOT" == "/" ]]; then exit 0; fi

TRACKING_DIR="$PROJECT_ROOT/.claude/tracking"

# Auto-initialize if missing
if [[ ! -d "$TRACKING_DIR" ]]; then
  bash "$SCRIPT_DIR/init-templates.sh" "$TRACKING_DIR"
fi

# Parse token usage from JSONL and update tokens.json
python3 - "$TRANSCRIPT" "$TRACKING_DIR/tokens.json" "$SESSION_ID" "$(basename "$PROJECT_ROOT")" <<'PYEOF'
import sys, json, os
from datetime import date

transcript_path = sys.argv[1]
tokens_file = sys.argv[2]
session_id = sys.argv[3]
project_name = sys.argv[4]
today = date.today().isoformat()

# Sum all token usage from assistant messages in this session
inp = out = cache_create = cache_read = 0
model = "unknown"
with open(transcript_path) as f:
    for line in f:
        try:
            obj = json.loads(line)
            msg = obj.get('message', {})
            if isinstance(msg, dict) and msg.get('role') == 'assistant':
                usage = msg.get('usage', {})
                if usage:
                    inp += usage.get('input_tokens', 0)
                    out += usage.get('output_tokens', 0)
                    cache_create += usage.get('cache_creation_input_tokens', 0)
                    cache_read += usage.get('cache_read_input_tokens', 0)
                m = msg.get('model', '')
                if m:
                    model = m
        except:
            pass

total = inp + cache_create + cache_read + out
if 'opus' in model:
    cost = inp * 15 / 1e6 + cache_create * 18.75 / 1e6 + cache_read * 1.50 / 1e6 + out * 75 / 1e6
else:
    cost = inp * 3 / 1e6 + cache_create * 3.75 / 1e6 + cache_read * 0.30 / 1e6 + out * 15 / 1e6

# Load or create tokens.json
data = []
if os.path.exists(tokens_file):
    try:
        with open(tokens_file) as f:
            data = json.load(f)
    except:
        data = []

# Build entry
entry = {
    "date": today,
    "project": project_name,
    "session_id": session_id,
    "input_tokens": inp,
    "cache_creation_tokens": cache_create,
    "cache_read_tokens": cache_read,
    "output_tokens": out,
    "total_tokens": total,
    "estimated_cost_usd": round(cost, 4),
    "model": model
}

# Update existing or append new
found = False
for i, e in enumerate(data):
    if e.get('session_id') == session_id:
        data[i] = entry
        found = True
        break
if not found:
    data.append(entry)

with open(tokens_file, 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
PYEOF

# Regenerate charts
python3 "$SCRIPT_DIR/generate-charts.py" "$TRACKING_DIR/tokens.json" "$TRACKING_DIR/charts.html" 2>/dev/null || true

# Regenerate key-prompts index
python3 "$SCRIPT_DIR/update-prompts-index.py" "$TRACKING_DIR" 2>/dev/null || true
