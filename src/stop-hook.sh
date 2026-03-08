#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --backfill-only: run backfill for current project and exit (used by SessionStart hook)
if [[ "${1:-}" == "--backfill-only" ]]; then
  INPUT="$(cat)"
  CWD="$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null || true)"
  if [[ -z "$CWD" ]]; then exit 0; fi
  PROJECT_ROOT="$CWD"
  while [[ "$PROJECT_ROOT" != "/" ]]; do
    [[ -e "$PROJECT_ROOT/.git" ]] && break
    PROJECT_ROOT="$(dirname "$PROJECT_ROOT")"
  done
  if [[ "$PROJECT_ROOT" == "/" ]]; then exit 0; fi
  TRACKING_DIR="$PROJECT_ROOT/.claude/tracking"
  if [[ -d "$TRACKING_DIR" ]]; then
    python3 "$SCRIPT_DIR/backfill.py" "$PROJECT_ROOT" 2>/dev/null || true
  fi
  exit 0
fi

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
  [[ -e "$PROJECT_ROOT/.git" ]] && break
  PROJECT_ROOT="$(dirname "$PROJECT_ROOT")"
done
if [[ "$PROJECT_ROOT" == "/" ]]; then exit 0; fi

TRACKING_DIR="$PROJECT_ROOT/.claude/tracking"

# Auto-initialize if missing, then backfill
if [[ ! -d "$TRACKING_DIR" ]]; then
  bash "$SCRIPT_DIR/init-templates.sh" "$TRACKING_DIR"
  python3 "$SCRIPT_DIR/backfill.py" "$PROJECT_ROOT" 2>/dev/null || true
fi

# Parse token usage from JSONL and write to SQLite
python3 "$SCRIPT_DIR/write-turns.py" "$TRANSCRIPT" "$TRACKING_DIR" "$SESSION_ID" "$(basename "$PROJECT_ROOT")"

# Parse friction events from JSONL
python3 "$SCRIPT_DIR/parse_friction.py" "$TRANSCRIPT" "$TRACKING_DIR/friction.json" \
  "$SESSION_ID" "$(basename "$PROJECT_ROOT")" "main" 2>/dev/null || true

# Regenerate charts
python3 "$SCRIPT_DIR/generate-charts.py" "$TRACKING_DIR" "$TRACKING_DIR/charts.html" 2>/dev/null || true

# Regenerate key-prompts index + shadow to OpenMemory
OM_DB="$HOME/.claude/.claude/openmemory.sqlite"
LEARNINGS="$HOME/.claude/tool-learnings.md"
OM_ARGS=""
if [[ -f "$OM_DB" ]]; then
  OM_ARGS="--om-db $OM_DB"
  if [[ -f "$LEARNINGS" ]]; then
    OM_ARGS="$OM_ARGS --learnings $LEARNINGS"
  fi
fi
python3 "$SCRIPT_DIR/update-prompts-index.py" "$TRACKING_DIR" $OM_ARGS 2>/dev/null || true
