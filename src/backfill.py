#!/usr/bin/env python3
"""
Backfill historical Claude Code sessions into tokens.json.

Usage:
  python3 backfill.py <project_root>

Scans ~/.claude/projects/<slug>/*.jsonl for transcripts belonging to the
given project, parses token usage from each, and appends entries to
<project_root>/.claude/tracking/tokens.json. Sessions already present
are skipped.
"""
import sys, json, os, glob
from datetime import datetime

project_root = os.path.abspath(sys.argv[1])
project_name = os.path.basename(project_root)
tracking_dir = os.path.join(project_root, ".claude", "tracking")
tokens_file = os.path.join(tracking_dir, "tokens.json")

# Claude Code slugifies project paths: replace "/" with "-"
slug = project_root.replace("/", "-")
transcripts_dir = os.path.expanduser("~/.claude/projects/" + slug)

if not os.path.isdir(transcripts_dir):
    print("No transcript directory found, nothing to backfill.")
    sys.exit(0)

# Load existing data and build set of known session IDs
data = []
if os.path.exists(tokens_file):
    try:
        with open(tokens_file) as f:
            data = json.load(f)
    except Exception:
        data = []

known_ids = {e.get("session_id") for e in data}

# Find all JSONL transcripts
jsonl_files = sorted(glob.glob(os.path.join(transcripts_dir, "*.jsonl")))
backfilled = 0

for jf in jsonl_files:
    session_id = os.path.splitext(os.path.basename(jf))[0]
    if session_id in known_ids:
        continue

    # Parse token usage — same logic as stop-hook.sh
    inp = out = cache_create = cache_read = 0
    model = "unknown"
    first_ts = None
    msgs = []

    try:
        with open(jf) as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    ts = obj.get("timestamp")
                    if ts and first_ts is None:
                        first_ts = ts
                    t = obj.get("type")
                    if t == "user" and not obj.get("isSidechain") and ts:
                        msgs.append(("user", ts))
                    elif t == "assistant" and ts:
                        msgs.append(("assistant", ts))
                    msg = obj.get("message", {})
                    if isinstance(msg, dict) and msg.get("role") == "assistant":
                        usage = msg.get("usage", {})
                        if usage:
                            inp += usage.get("input_tokens", 0)
                            out += usage.get("output_tokens", 0)
                            cache_create += usage.get("cache_creation_input_tokens", 0)
                            cache_read += usage.get("cache_read_input_tokens", 0)
                        m = msg.get("model", "")
                        if m:
                            model = m
                except Exception:
                    pass
    except Exception:
        continue

    total = inp + cache_create + cache_read + out
    if total == 0:
        continue

    # Date from first timestamp in the transcript
    session_date = None
    if first_ts:
        try:
            session_date = datetime.fromisoformat(
                first_ts.replace("Z", "+00:00")
            ).strftime("%Y-%m-%d")
        except Exception:
            pass
    if not session_date:
        session_date = datetime.fromtimestamp(os.path.getmtime(jf)).strftime("%Y-%m-%d")

    # Duration: sum of per-turn active thinking time (user -> first assistant reply)
    duration = 0
    i = 0
    while i < len(msgs):
        if msgs[i][0] == "user":
            j = i + 1
            while j < len(msgs) and msgs[j][0] != "assistant":
                j += 1
            if j < len(msgs):
                try:
                    t0 = datetime.fromisoformat(msgs[i][1].replace("Z", "+00:00"))
                    t1 = datetime.fromisoformat(msgs[j][1].replace("Z", "+00:00"))
                    duration += max(0, int((t1 - t0).total_seconds()))
                except Exception:
                    pass
        i += 1

    # Cost
    if "opus" in model:
        cost = inp * 15 / 1e6 + cache_create * 18.75 / 1e6 + cache_read * 1.50 / 1e6 + out * 75 / 1e6
    else:
        cost = inp * 3 / 1e6 + cache_create * 3.75 / 1e6 + cache_read * 0.30 / 1e6 + out * 15 / 1e6

    entry = {
        "date": session_date,
        "project": project_name,
        "session_id": session_id,
        "input_tokens": inp,
        "cache_creation_tokens": cache_create,
        "cache_read_tokens": cache_read,
        "output_tokens": out,
        "total_tokens": total,
        "estimated_cost_usd": round(cost, 4),
        "model": model,
        "duration_seconds": duration,
    }

    data.append(entry)
    backfilled += 1

# Write updated tokens.json
if backfilled > 0:
    os.makedirs(os.path.dirname(tokens_file), exist_ok=True)
    with open(tokens_file, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

print(f"{backfilled} session{'s' if backfilled != 1 else ''} backfilled.")

# Regenerate charts if we added anything
if backfilled > 0:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    charts_html = os.path.join(tracking_dir, "charts.html")
    os.system(f'python3 "{script_dir}/generate-charts.py" "{tokens_file}" "{charts_html}" 2>/dev/null')
