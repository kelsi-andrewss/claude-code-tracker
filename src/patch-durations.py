#!/usr/bin/env python3
"""
Patch duration_seconds for existing tokens.json entries that have duration 0.

Usage:
  python3 patch-durations.py <project_root>
"""
import sys, json, os, glob
from datetime import datetime

project_root = os.path.abspath(sys.argv[1])
tracking_dir = os.path.join(project_root, ".claude", "tracking")
tokens_file = os.path.join(tracking_dir, "tokens.json")

slug = project_root.replace("/", "-")
transcripts_dir = os.path.expanduser("~/.claude/projects/" + slug)

with open(tokens_file) as f:
    data = json.load(f)

patched = 0
for entry in data:
    sid = entry.get("session_id")
    if not sid:
        continue
    jf = os.path.join(transcripts_dir, sid + ".jsonl")
    if not os.path.exists(jf):
        continue

    msgs = []
    try:
        with open(jf) as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    t = obj.get("type")
                    ts = obj.get("timestamp")
                    if t == "user" and not obj.get("isSidechain") and ts:
                        msgs.append(("user", ts))
                    elif t == "assistant" and ts:
                        msgs.append(("assistant", ts))
                except Exception:
                    pass
    except Exception:
        continue

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

    if duration > 0:
        entry["duration_seconds"] = duration
        patched += 1
        print(f"  {sid[:8]}  {duration}s")

if patched > 0:
    with open(tokens_file, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    charts_html = os.path.join(tracking_dir, "charts.html")
    os.system(f'python3 "{script_dir}/generate-charts.py" "{tokens_file}" "{charts_html}" 2>/dev/null')

print(f"{patched} session{'s' if patched != 1 else ''} patched.")
