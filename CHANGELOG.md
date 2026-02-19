# Changelog

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
