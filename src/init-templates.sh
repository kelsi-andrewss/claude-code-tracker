#!/usr/bin/env bash
set -euo pipefail
TRACKING_DIR="$1"
mkdir -p "$TRACKING_DIR"
mkdir -p "$TRACKING_DIR/key-prompts"

cat > "$TRACKING_DIR/tokens.json" <<'EOF'
[]
EOF

cat > "$TRACKING_DIR/key-prompts.md" <<'EOF'
# Prompt Journal

High-signal prompts organized by day.

| File | Entries | Highlights |
|------|---------|------------|

**Total**: 0 entries

---

New entries go in `key-prompts/YYYY-MM-DD.md` for today's date. Create the file if it doesn't exist — use the same header format as existing files.
EOF

cat > "$TRACKING_DIR/sessions.md" <<'EOF'
# Session Log

---
EOF

cat > "$TRACKING_DIR/cost-analysis.md" <<'EOF'
# AI Cost Analysis

## Development Costs

| Date | Session Summary | Input | Cache Write | Cache Read | Output | Cost (USD) |
|------|----------------|-------|-------------|------------|--------|------------|
| | **Total** | | | | | **$0.00** |

*Token counts include prompt caching. Pricing: Sonnet 4.5 -- input $3/M, cache write $3.75/M, cache read $0.30/M, output $15/M. Opus 4.6 -- input $15/M, cache write $18.75/M, cache read $1.50/M, output $75/M.*

---

## Anthropic Pricing Reference

| Model | Input (per M) | Output (per M) | Cache Write | Cache Read |
|-------|--------------|----------------|-------------|------------|
| Claude Opus 4.6 | $15.00 | $75.00 | $18.75 | $1.50 |
| Claude Sonnet 4.5 | $3.00 | $15.00 | $3.75 | $0.30 |
| Claude Haiku 4.5 | $0.80 | $4.00 | $1.00 | $0.08 |
EOF

cat > "$TRACKING_DIR/ai-dev-log.md" <<'EOF'
# AI Development Log

**Period**: Started $(date +%Y-%m-%d)
**Primary AI Tool**: Claude Code

---

## Tools & Workflow

*Document your AI workflow here.*

---

## Effective Prompts

See `key-prompts.md` for the full journal with context and analysis.

---

## Code Analysis

*Document AI contribution estimates here.*

---

## Key Learnings

*Document key learnings as you go.*
EOF
