# claude-code-tracker

Automatic token usage, cost estimation, and prompt quality tracking for [Claude Code](https://claude.ai/claude-code) sessions.

After every session, it parses the transcript, updates a `tokens.json` ledger, regenerates a Chart.js dashboard (`charts.html`), and rebuilds the key-prompts index. Zero external dependencies — pure bash and Python stdlib.

---

## What it tracks

- **Token usage** per session: input, cache write, cache read, output
- **Estimated API cost** (list-price equivalent — not a subscription charge)
- **Per-model breakdown**: Opus vs Sonnet cost split
- **Key prompts**: high-signal prompts you log manually, with category and context
- **Prompt efficiency**: ratio of key prompts to total human messages

All data lives in `<project>/.claude/tracking/` alongside your code.

---

## Install

### Option 1 — npm (global)

```bash
npm install -g claude-code-tracker
```

The `postinstall` script copies the tracking scripts to `~/.claude/tracking/` and registers the Stop hook in `~/.claude/settings.json`.

### Option 2 — Homebrew

```bash
brew tap kelsiandrews/claude-code-tracker
brew install claude-code-tracker
```

### Option 3 — git clone

```bash
git clone https://github.com/kelsiandrews/claude-code-tracker.git
cd claude-code-tracker
./install.sh
```

Restart Claude Code after any install method.

---

## What gets created

On first use in a project, the Stop hook auto-initializes `<project>/.claude/tracking/`:

```
.claude/tracking/
  tokens.json          # session data (auto-updated)
  charts.html          # Chart.js dashboard (auto-updated)
  key-prompts.md       # index of logged prompts
  key-prompts/         # one .md per day
    2026-02-18.md
  cost-analysis.md     # template for manual notes
  ai-dev-log.md        # template for dev log
  sessions.md          # session log template
```

---

## View the dashboard

Open `charts.html` in a browser:

```bash
open .claude/tracking/charts.html       # macOS
xdg-open .claude/tracking/charts.html  # Linux
```

The dashboard shows cumulative cost, cost per day, sessions, output tokens, model breakdown, and prompt analytics — all updated automatically after each session.

---

## Cost CLI

```bash
claude-tracker-cost
# or
python3 ~/.claude/tracking/cost-summary.py
```

Prints a cost summary table for the current project.

---

## Logging key prompts

Add entries to `<project>/.claude/tracking/key-prompts/YYYY-MM-DD.md` (today's date). The index and charts update automatically on the next session end.

Entry format:

```markdown
## 2026-02-18 — Short title

**Category**: breakthrough | bug-resolution | architecture | feature
**Context**: What problem was being solved?
**The Prompt**: (exact or close paraphrase)
**Why It Worked**: (what made the phrasing/framing effective)
**Prior Attempts That Failed**: (for bugs: what didn't work; otherwise: N/A)
```

### Auto-logging with CLAUDE.md

Add the following to your project's `CLAUDE.md` to have Claude log prompts automatically:

```markdown
## Tracking
After completing significant work (bug fix, feature, refactor, plan approval), append a prompt
assessment entry to `<project>/.claude/tracking/key-prompts/YYYY-MM-DD.md` (today's date).
Create the file if it doesn't exist, using the same header format as existing files.

Use this format:
  ## [date] — [short title]
  **Category**: breakthrough | bug-resolution | architecture | feature
  **Context**: What problem was being solved?
  **The Prompt**: (exact or close paraphrase)
  **Why It Worked**: (what made the phrasing/framing effective)
  **Prior Attempts That Failed**: (for bugs: what didn't work; otherwise: N/A)

Only write entries for genuinely high-signal prompts. Skip routine exchanges.
Do not ask permission — just append after significant work.
```

---

## Uninstall

### npm
```bash
npm uninstall -g claude-code-tracker
~/.claude/tracking/uninstall.sh
```

### Homebrew
```bash
brew uninstall claude-code-tracker
```

### Manual
```bash
./uninstall.sh
```

The uninstaller removes the scripts from `~/.claude/tracking/` and removes the Stop hook from `~/.claude/settings.json`. Your project tracking data (tokens.json, charts.html, key-prompts/) is left intact.

---

## Cost note

Figures shown are **API list-price equivalents** — what pay-as-you-go API customers would be charged at current Anthropic pricing. If you are on a Max subscription, these are not amounts billed to you.

Current rates used:
| Model | Input | Cache write | Cache read | Output |
|-------|-------|-------------|------------|--------|
| Sonnet | $3/M | $3.75/M | $0.30/M | $15/M |
| Opus | $15/M | $18.75/M | $1.50/M | $75/M |

---

## License

MIT
