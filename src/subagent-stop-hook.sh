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

# Parse token usage from subagent JSONL and write to SQLite
python3 "$SCRIPT_DIR/write-agent.py" "$TRANSCRIPT" "$TRACKING_DIR" "$SESSION_ID" "$AGENT_ID" "$AGENT_TYPE"

# Parse friction events from subagent JSONL
python3 "$SCRIPT_DIR/parse_friction.py" "$TRANSCRIPT" "$TRACKING_DIR/friction.json" \
  "$SESSION_ID" "$(basename "$PROJECT_ROOT")" "subagent" \
  --agent-type "$AGENT_TYPE" --agent-id "$AGENT_ID" 2>/dev/null || true

# Regenerate charts
python3 "$SCRIPT_DIR/generate-charts.py" "$TRACKING_DIR" "$TRACKING_DIR/charts.html" 2>/dev/null || true
