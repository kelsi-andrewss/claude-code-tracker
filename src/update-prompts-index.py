#!/usr/bin/env python3
"""
Regenerates <tracking_dir>/key-prompts.md index from files in key-prompts/ folder.
Optionally shadows new entries to OpenMemory for semantic search.
Called by stop-hook.sh after each session.

Usage: python3 update-prompts-index.py <tracking_dir> [--om-db <path>] [--learnings <path>]
"""
import hashlib
import json
import os
import re
import glob
import sqlite3
import struct
import sys
import time
import uuid
from urllib.request import urlopen, Request
from urllib.error import URLError

# --- Parse args ---
tracking_dir = sys.argv[1]
om_db_path = None
learnings_path = None

i = 2
while i < len(sys.argv):
    if sys.argv[i] == "--om-db" and i + 1 < len(sys.argv):
        om_db_path = sys.argv[i + 1]
        i += 2
    elif sys.argv[i] == "--learnings" and i + 1 < len(sys.argv):
        learnings_path = sys.argv[i + 1]
        i += 2
    else:
        i += 1

prompts_dir = os.path.join(tracking_dir, "key-prompts")
index_file = os.path.join(tracking_dir, "key-prompts.md")

# --- OpenMemory helpers ---
OLLAMA_URL = "http://localhost:11434/api/embeddings"
OLLAMA_MODEL = "nomic-embed-text"


def get_embedding(text):
    """Get embedding vector from Ollama. Returns list of floats or None."""
    payload = json.dumps({"model": OLLAMA_MODEL, "prompt": text}).encode()
    req = Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()).get("embedding")
    except (URLError, OSError, json.JSONDecodeError, KeyError):
        return None


def om_store(conn, content, tags, user_id, sector="procedural", salience=0.5, decay_lambda=0.02):
    """Store a memory with embedding. Returns True if stored, False if skipped/failed."""
    simhash = hashlib.md5(content.encode()).hexdigest()[:16]

    # Dedup check
    row = conn.execute("SELECT 1 FROM memories WHERE simhash = ?", (simhash,)).fetchone()
    if row:
        return False

    vec = get_embedding(content)
    if vec is None:
        return False

    blob = struct.pack(f"<{len(vec)}f", *vec)
    now_ts = int(time.time())
    mem_id = str(uuid.uuid4())
    tags_json = json.dumps(tags)

    conn.execute(
        "INSERT OR IGNORE INTO memories "
        "(id, user_id, content, simhash, primary_sector, tags, meta, "
        "mean_dim, mean_vec, created_at, updated_at, last_seen_at, "
        "salience, decay_lambda, feedback_score) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            mem_id, user_id, content[:4000], simhash,
            sector, tags_json, "{}",
            len(vec), blob,
            now_ts, now_ts, now_ts,
            salience, decay_lambda, 0,
        ),
    )
    return True


def parse_prompt_entries(content):
    """Parse ## entries from a key-prompts markdown file. Returns list of dicts."""
    entries = []
    for match in re.finditer(
        r'^## \d{4}-\d{2}-\d{2} — (.+?)$(.+?)(?=^## |\Z)',
        content, re.MULTILINE | re.DOTALL
    ):
        title = match.group(1).strip()
        body = match.group(2).strip()

        category = ""
        why = ""
        for line in body.splitlines():
            if line.startswith("**Category**:"):
                category = line.split(":", 1)[1].strip()
            elif line.startswith("**Why It Worked**:"):
                why = line.split(":", 1)[1].strip()

        if title and why:
            entries.append({"title": title, "category": category, "why": why})
    return entries


def parse_learning_entries(content):
    """Parse - [date] entries from tool-learnings.md. Returns list of strings."""
    entries = []
    for match in re.finditer(r'^- \[\d{4}-\d{2}-\d{2}\] (.+)', content, re.MULTILINE):
        entry = match.group(1).strip()
        if entry:
            entries.append(entry)
    return entries


# --- Build index (original functionality) ---
if not os.path.isdir(prompts_dir):
    # Still try learnings even if no prompts dir
    if not (om_db_path and learnings_path):
        sys.exit(0)
    files = []
else:
    files = sorted(glob.glob(os.path.join(prompts_dir, "????-??-??.md")))

rows = []
total_entries = 0
all_prompt_entries = []

for f in files:
    date = os.path.splitext(os.path.basename(f))[0]
    with open(f, encoding='utf-8') as fh:
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

    # Collect entries for OpenMemory shadowing
    all_prompt_entries.extend(parse_prompt_entries(content))

if files:
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

    with open(index_file, "w", encoding='utf-8') as f:
        f.writelines(lines)

# --- Shadow to OpenMemory ---
if not om_db_path or not os.path.isfile(om_db_path):
    sys.exit(0)

# Quick Ollama health check
if get_embedding("test") is None:
    sys.exit(0)

prompt_stored = 0
prompt_skipped = 0
learning_stored = 0
learning_skipped = 0

try:
    conn = sqlite3.connect(om_db_path, timeout=10)

    # Shadow key prompt entries
    for entry in all_prompt_entries:
        content = f"{entry['title']}: {entry['why']}"
        tags = ["prompt-pattern"]
        if entry["category"]:
            tags.append(entry["category"])
        if om_store(conn, content, tags, user_id="global"):
            prompt_stored += 1
        else:
            prompt_skipped += 1

    # Shadow tool learnings
    if learnings_path and os.path.isfile(learnings_path):
        with open(learnings_path, encoding='utf-8') as f:
            learnings_content = f.read()
        for entry in parse_learning_entries(learnings_content):
            if om_store(conn, entry, ["tool-learning"], user_id="global"):
                learning_stored += 1
            else:
                learning_skipped += 1

    conn.commit()
    conn.close()
except Exception:
    pass
