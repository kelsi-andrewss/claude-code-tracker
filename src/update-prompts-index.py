#!/usr/bin/env python3
"""
Regenerates <tracking_dir>/key-prompts.md index from files in key-prompts/ folder.
Called by stop-hook.sh after each session.

Usage: python3 update-prompts-index.py <tracking_dir>
"""
import sys
import os
import re
import glob

tracking_dir = sys.argv[1]
prompts_dir = os.path.join(tracking_dir, "key-prompts")
index_file = os.path.join(tracking_dir, "key-prompts.md")

if not os.path.isdir(prompts_dir):
    sys.exit(0)

files = sorted(glob.glob(os.path.join(prompts_dir, "????-??-??.md")))
if not files:
    sys.exit(0)

rows = []
total_entries = 0

for f in files:
    date = os.path.splitext(os.path.basename(f))[0]
    with open(f) as fh:
        content = fh.read()

    # Count entries (## headings that are not the title line)
    entries = len(re.findall(r'^## (?!Key Prompts)', content, re.MULTILINE))

    # Extract first 3 entry titles for highlights
    titles = re.findall(r'^## (.+)', content, re.MULTILINE)
    # Skip the file title (first line if it matches "Key Prompts — ...")
    titles = [t for t in titles if not t.startswith("Key Prompts")]
    highlights = ", ".join(titles[:3])
    if len(titles) > 3:
        highlights += "..."

    rows.append((date, entries, highlights))
    total_entries += entries

lines = ["# Prompt Journal\n",
         "\nHigh-signal prompts organized by day.\n",
         "\n| File | Entries | Highlights |\n",
         "|------|---------|------------|\n"]

for date, entries, highlights in rows:
    lines.append(f"| [{date}](key-prompts/{date}.md) | {entries} | {highlights} |\n")

lines.append(f"\n**Total**: {total_entries} entries across {len(rows)} day{'s' if len(rows) != 1 else ''}\n")
lines.append("\n---\n")
lines.append("\nNew entries go in `key-prompts/YYYY-MM-DD.md` for today's date. "
             "Create the file if it doesn't exist — use the same header format as existing files.\n")

with open(index_file, "w") as f:
    f.writelines(lines)
