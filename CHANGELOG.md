# Changelog

## [1.2.5] - 2026-02-23

### Added
- **Auto key-prompts extraction** — new `extract_key_prompts.py` module automatically extracts non-trivial human messages from JSONL transcripts and writes them to `key-prompts/YYYY-MM-DD.md` with `**Category**:` tags. Replaces the manual-only workflow — prompts are now captured during both live sessions and backfill.
- **Auto-categorization** — prompts are classified into the 4 original categories (`bug-resolution`, `architecture`, `feature`, `breakthrough`) using content heuristics. Long prompts (500+ chars) are tagged as breakthroughs.
- **Duplicate detection** — re-running backfill won't re-add prompts that already exist in a key-prompts file (matched by first 80 chars).
- **Cross-platform Windows support** — full Windows compatibility added across the entire codebase:
  - `install.js` / `uninstall.js` — Node.js entry points replacing `bash ./install.sh` as npm postinstall hook
  - `stop-hook.js` — Node.js stop hook for Windows (macOS/Linux continue using `stop-hook.sh`)
  - `parse-session.py` — extracted from `stop-hook.sh` inline heredoc for cross-platform use
  - `init-templates.py` — Python replacement for `init-templates.sh`
  - `platform_utils.py` — shared module for OS detection, path slugification, Python command resolution, and file opening
  - `bin/claude-tracker-cost.js` — npm bin wrapper (Windows can't execute `.py` shebangs)
- **`/view-tracking` skill** — added Windows `start` command branch alongside existing `open` (macOS) and `xdg-open` (Linux)

### Fixed
- **Path slugification on Windows** — `C:\Users\...` now correctly produces `C--Users-...` slug (colon replaced with dash) matching Claude Code's on-disk format
- **UTF-8 encoding** — all `open()` calls across 6 Python scripts (13+ call sites) now specify `encoding="utf-8"`, fixing `UnicodeDecodeError` on Windows where the default encoding is cp1252
- **`find_git_root()` infinite loop on Windows** — replaced `while root != "/"` with `while parent != root` which works on all OSes
- **`stop-hook.sh` heredoc encoding** — added `encoding='utf-8'` to 3 `open()` calls in the inline Python that were missing it

### Changed
- **Key-prompts pipeline** — `backfill.py`, `parse-session.py`, and `stop-hook.sh` all now extract key prompts as part of their normal processing flow
- **`package.json`** — postinstall uses `node install.js`, added `bin` entry, updated `files` list and repository URL

## [1.2.4] - 2026-02-22

### Added
- **Skills install/uninstall** — `install.sh` now copies bundled skills from `skills/*/SKILL.md` into `~/.claude/skills/` on install. `uninstall.sh` removes them on uninstall. Windows detection (Git Bash, MSYS, Cygwin) added to `uninstall.sh` to match the existing guard in `install.sh`.
- **`/view-tracking` skill** — Claude Code skill that opens `charts.html` and today's key-prompts file for the current project. Installed automatically to `~/.claude/skills/view-tracking/`. Cross-platform: uses `open` on macOS, `xdg-open` on Linux/WSL with a fallback message if the command is unavailable.

## [1.2.3] - 2026-02-21

### Fixed
- **Git worktree support** — `.git` detection in `stop-hook.sh` and `cost-summary.py` now uses existence checks (`-e` / `os.path.exists`) instead of directory checks (`-d` / `os.path.isdir`). Worktrees outside the repo tree no longer silently discard sessions.

### Changed
- **Prompt length distribution** — chart now has a dropdown to switch between four time ranges (0–30s, 0–60s, 0–30m, 0–60m) with finer-grained buckets and an overflow bar for each range.

## [1.2.2] - 2026-02-21

### Fixed
- **Stale hook path on upgrade** — `install.sh` now replaces any existing `stop-hook.sh` hook entry instead of skipping if an entry from a different install method (npm vs brew) is already present. Prevents the old path from running stale code after switching install methods.

## [1.2.1] - 2026-02-21

### Fixed
- **`package-lock.json` excluded** — added to `.gitignore` to prevent it from blocking the deploy script's clean-tree check.

## [1.2.0] - 2026-02-21

### Changed
- **Per-turn token tracking** — `tokens.json` now stores one entry per prompt turn (with `turn_index` and `turn_timestamp`) instead of one entry per session. Scatter plots, duration histograms, and time-vs-cost charts now have meaningful per-prompt granularity.
- **Duration histogram buckets** — rebucketed from session-length ranges (0-2m, 2-5m, ...) to per-turn ranges (<5s, 5-15s, 15-30s, 30s-2m, 2m+).
- **Dashboard labels** — "Sessions per day" is now "Prompts per day", "Session time" is now "Active time", and summary stats show both session and prompt counts.
- **Cost summary** — `cost-summary.py` reports prompts and sessions separately; "Session time" renamed to "Active time".

### Added
- **Windows OS guard** — `install.sh` detects native Windows shells (Git Bash, MSYS, Cygwin) and exits with a WSL install link instead of failing silently on Unix path assumptions.
- **SessionStart hook** — `install.sh` registers a `SessionStart` hook that runs `backfill.py --backfill-only` to catch any missed sessions on startup.
- **Permissions allow entry** — `install.sh` adds a `Bash()` allow pattern to `settings.json` so the stop-hook runs without prompting.
- **Old-format migration** — `backfill.py` and `patch-durations.py` detect old single-entry-per-session records (no `turn_index`) and re-process them into per-turn entries.

## [1.1.7] - 2026-02-19

### Fixed
- **Backfill duration accuracy** — `backfill.py` was computing `duration_seconds` as wall-clock session time (`last_ts - first_ts`), which included idle time between prompts. Now uses per-turn active thinking time (sum of user-to-assistant gaps), matching the stop-hook and `patch-durations.py`.

## [1.1.6] - 2026-02-19

### Fixed
- **Homebrew install** — `post_install` ran inside Homebrew's `sandbox-exec` jail which blocks all writes to `~/.claude/`. Removed `post_install` entirely. Users now run `claude-tracker-setup` after `brew install` to register the hook. The hook points at the stable `/opt/homebrew/opt/` libexec path, which survives `brew upgrade` without any writes to user directories.

### Added
- **`claude-tracker-setup`** — new setup command installed to Homebrew's `bin/`. Runs `install.sh` outside the sandbox to patch `settings.json` and `CLAUDE.md`.

## [1.1.4] - 2026-02-19

### Fixed
- **Homebrew upgrade** — `brew upgrade` no longer fails with a provenance xattr error. macOS Ventura+ attaches a SIP-protected `com.apple.provenance` attribute to Homebrew-installed files, which blocked `rm`/`cp`/`ln -sf` on upgrade. `install.sh` now detects a Cellar path and uses an atomic `ln` + `mv -f` pattern (the `rename` syscall bypasses SIP) to replace files with symlinks. Symlinks carry no xattrs and auto-resolve to the updated cellar version after each upgrade. Non-Homebrew installs (npm, git clone) are unaffected.

## [1.1.0] - 2026-02-19

### Added
- **Session duration tracking** — active thinking time per session (sum of Claude response time per turn, matching the "Pondering… Xm Ys" metric shown in the UI). Stored as `duration_seconds` in `tokens.json`.
- **`patch-durations.py`** — backfill script to recompute `duration_seconds` for existing sessions from JSONL transcripts.
- **`backfill.py`** — backfill token usage for all pre-existing sessions in a project.
- **New charts**: Duration per day, Avg duration per day, Tokens per minute (scatter), Session length distribution (histogram), Cumulative time, Time vs cost (scatter).
- **Trivial prompt detection** — prompts under 40 characters with no `?` are classified as trivial (confirmations, short commands). Excluded from the efficiency denominator.
- **Trivial prompts bar** on the Prompts per day chart (between Total and Key).
- **Dashboard sections** — charts grouped into labeled sections: Cost & Usage, Key Prompts, Time.

### Changed
- **Prompt efficiency** now computed as `key / (total − trivial)` instead of `key / total`.
- Chart titles shortened for readability.
- Canvas height increased (240px regular, 200px wide).
- `project_dir` resolution in `generate-charts.py` uses `abspath()` to fix path computation when invoked with a relative tokens path.
- Duration x-axis on Time vs Cost chart starts at 0.
- `formatDuration` shows seconds for sub-minute values.

## [1.0.0] - 2026-02-18

Initial release.
