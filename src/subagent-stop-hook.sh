#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

INPUT="$(cat)"

# Extract fields from SubagentStop payload
CWD="$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null || true)"
TRANSCRIPT="$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('agent_transcript_path',''))" 2>/dev/null || true)"
SESSION_ID="$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null || true)"
AGENT_ID="$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('agent_id',''))" 2>/dev/null || true)"
AGENT_TYPE="$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('agent_type','unknown'))" 2>/dev/null || true)"

if [[ -z "$CWD" || -z "$TRANSCRIPT" || ! -f "$TRANSCRIPT" ]]; then exit 0; fi

# Find project root (walk up to .git)
PROJECT_ROOT="$CWD"
while [[ "$PROJECT_ROOT" != "/" ]]; do
  [[ -e "$PROJECT_ROOT/.git" ]] && break
  PROJECT_ROOT="$(dirname "$PROJECT_ROOT")"
done
if [[ "$PROJECT_ROOT" == "/" ]]; then exit 0; fi

TRACKING_DIR="$PROJECT_ROOT/.claude/tracking"
# Only run if tracking is already initialized — don't auto-init from subagent hook
if [[ ! -d "$TRACKING_DIR" ]]; then exit 0; fi

# Parse token usage from subagent JSONL — sum all turns
python3 - "$TRANSCRIPT" "$TRACKING_DIR/agents.json" "$SESSION_ID" "$AGENT_ID" "$AGENT_TYPE" <<'PYEOF'
import sys, json, os
from datetime import datetime, date

transcript_path = sys.argv[1]
agents_file     = sys.argv[2]
session_id      = sys.argv[3]
agent_id        = sys.argv[4]
agent_type      = sys.argv[5]

# Sum usage across ALL assistant messages in the transcript
total_inp = total_out = total_cache_create = total_cache_read = 0
model = "unknown"
turns = 0
first_ts = None

with open(transcript_path, encoding='utf-8') as f:
    for line in f:
        try:
            obj = json.loads(line)
            msg = obj.get('message', {})
            if not isinstance(msg, dict):
                continue
            if msg.get('role') == 'assistant':
                usage = msg.get('usage', {})
                if usage:
                    total_inp          += usage.get('input_tokens', 0)
                    total_out          += usage.get('output_tokens', 0)
                    total_cache_create += usage.get('cache_creation_input_tokens', 0)
                    total_cache_read   += usage.get('cache_read_input_tokens', 0)
                    turns += 1
                m = msg.get('model', '')
                if m:
                    model = m
            ts = obj.get('timestamp')
            if ts and first_ts is None:
                first_ts = ts
        except:
            pass

total = total_inp + total_out + total_cache_create + total_cache_read
if total == 0:
    sys.exit(0)

if 'opus' in model:
    cost = total_inp * 15/1e6 + total_cache_create * 18.75/1e6 + total_cache_read * 1.50/1e6 + total_out * 75/1e6
else:
    cost = total_inp * 3/1e6 + total_cache_create * 3.75/1e6 + total_cache_read * 0.30/1e6 + total_out * 15/1e6

try:
    ts_str = datetime.fromisoformat(first_ts.replace('Z', '+00:00')).strftime('%Y-%m-%dT%H:%M:%SZ')
except:
    ts_str = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

entry = {
    'timestamp':             ts_str,
    'session_id':            session_id,
    'agent_id':              agent_id,
    'agent_type':            agent_type,
    'input_tokens':          total_inp,
    'output_tokens':         total_out,
    'cache_creation_tokens': total_cache_create,
    'cache_read_tokens':     total_cache_read,
    'total_tokens':          total,
    'turns':                 turns,
    'estimated_cost_usd':    round(cost, 4),
    'model':                 model,
}

data = []
if os.path.exists(agents_file):
    try:
        with open(agents_file, encoding='utf-8') as f:
            data = json.load(f)
    except:
        data = []

data.append(entry)
with open(agents_file, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
PYEOF

# Parse friction events from subagent JSONL
python3 "$SCRIPT_DIR/parse_friction.py" "$TRANSCRIPT" "$TRACKING_DIR/friction.json" \
  "$SESSION_ID" "$(basename "$PROJECT_ROOT")" "subagent" \
  --agent-type "$AGENT_TYPE" --agent-id "$AGENT_ID" 2>/dev/null || true

# Regenerate charts
python3 "$SCRIPT_DIR/generate-charts.py" "$TRACKING_DIR/tokens.json" "$TRACKING_DIR/charts.html" 2>/dev/null || true
