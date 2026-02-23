---
name: view-tracking
description: Open the charts dashboard and today's key-prompts file for the current project. Use when the user says "open charts", "view tracking", "show dashboard", or "/view-tracking".
---

Open the tracking dashboard for the current project.

Steps:

1. Set the tracking directory: `$CLAUDE_PROJECT_DIR/.claude/tracking/`

2. Open the charts dashboard:
   ```bash
   if [[ "$OSTYPE" == darwin* ]]; then
     open "$CLAUDE_PROJECT_DIR/.claude/tracking/charts.html"
   elif [[ "$OSTYPE" == msys* || "$OSTYPE" == cygwin* || -n "${WINDIR:-}" ]]; then
     start "" "$CLAUDE_PROJECT_DIR/.claude/tracking/charts.html"
   else
     xdg-open "$CLAUDE_PROJECT_DIR/.claude/tracking/charts.html" 2>/dev/null || echo "Could not open charts.html automatically. Path: $CLAUDE_PROJECT_DIR/.claude/tracking/charts.html"
   fi
   ```
   If the file doesn't exist, report: "No charts.html found at $CLAUDE_PROJECT_DIR/.claude/tracking/charts.html"

3. Find and open today's key-prompts file. Today's date is available from the system. The file path is:
   `$CLAUDE_PROJECT_DIR/.claude/tracking/key-prompts/YYYY-MM-DD.md` (using today's date)

   - If it exists:
     ```bash
     if [[ "$OSTYPE" == darwin* ]]; then
       open "$CLAUDE_PROJECT_DIR/.claude/tracking/key-prompts/YYYY-MM-DD.md"
     elif [[ "$OSTYPE" == msys* || "$OSTYPE" == cygwin* || -n "${WINDIR:-}" ]]; then
       start "" "$CLAUDE_PROJECT_DIR/.claude/tracking/key-prompts/YYYY-MM-DD.md"
     else
       xdg-open "$CLAUDE_PROJECT_DIR/.claude/tracking/key-prompts/YYYY-MM-DD.md" 2>/dev/null || echo "Could not open key-prompts file automatically. Path: $CLAUDE_PROJECT_DIR/.claude/tracking/key-prompts/YYYY-MM-DD.md"
     fi
     ```
   - If it doesn't exist: report "No key-prompts file for today yet." then list the most recent file in that directory:
     ```bash
     ls -t "$CLAUDE_PROJECT_DIR/.claude/tracking/key-prompts/"*.md 2>/dev/null | head -1
     ```
     If a recent file exists, offer: "Most recent: <filename>" and ask if the user wants to open it. If they say yes:
     ```bash
     if [[ "$OSTYPE" == darwin* ]]; then
       open "$CLAUDE_PROJECT_DIR/.claude/tracking/key-prompts/YYYY-MM-DD.md"
     elif [[ "$OSTYPE" == msys* || "$OSTYPE" == cygwin* || -n "${WINDIR:-}" ]]; then
       start "" "$CLAUDE_PROJECT_DIR/.claude/tracking/key-prompts/YYYY-MM-DD.md"
     else
       xdg-open "$CLAUDE_PROJECT_DIR/.claude/tracking/key-prompts/YYYY-MM-DD.md" 2>/dev/null || echo "Could not open key-prompts file automatically. Path: $CLAUDE_PROJECT_DIR/.claude/tracking/key-prompts/YYYY-MM-DD.md"
     fi
     ```

4. If the entire `.claude/tracking/` directory doesn't exist, report: "No tracking directory found for this project. Expected: $CLAUDE_PROJECT_DIR/.claude/tracking/"

Run the bash commands using the Bash tool. Do not ask for confirmation before opening files.
