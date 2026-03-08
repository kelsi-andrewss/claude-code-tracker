#!/usr/bin/env python3
"""
Patch duration_seconds for per-turn entries that have duration 0.

Usage:
  python3 patch-durations.py <project_root>
"""
import sys, json, os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import storage

from datetime import datetime

project_root = os.path.abspath(sys.argv[1])
tracking_dir = os.path.join(project_root, ".claude", "tracking")

slug = project_root.replace("/", "-")
transcripts_dir = os.path.expanduser("~/.claude/projects/" + slug)

data = storage.get_all_turns(tracking_dir)

def parse_transcript(jf):
    msgs = []
    usages = []
    model = "unknown"
    first_ts = None
    try:
        with open(jf, encoding='utf-8') as f:
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
                            usages.append(usage)
                        m = msg.get("model", "")
                        if m:
                            model = m
                except Exception:
                    pass
    except Exception:
        pass
    return msgs, usages, model, first_ts

patched = 0

for entry in data:
    if entry.get("duration_seconds", 0) > 0:
        continue
    sid = entry.get("session_id")
    turn_index = entry.get("turn_index", 0)
    jf = os.path.join(transcripts_dir, sid + ".jsonl")
    if not os.path.exists(jf):
        continue

    msgs, usages, model, first_ts = parse_transcript(jf)

    # Walk to the target turn
    ti = 0
    i = 0
    while i < len(msgs):
        if msgs[i][0] == "user":
            j = i + 1
            while j < len(msgs) and msgs[j][0] != "assistant":
                j += 1
            if j < len(msgs) and ti == turn_index:
                try:
                    t0 = datetime.fromisoformat(msgs[i][1].replace("Z", "+00:00"))
                    t1 = datetime.fromisoformat(msgs[j][1].replace("Z", "+00:00"))
                    duration = max(0, int((t1 - t0).total_seconds()))
                    if duration > 0:
                        storage.patch_turn_duration(tracking_dir, sid, turn_index, duration)
                        patched += 1
                        print(f"  patched {sid[:8]}#{turn_index}  {duration}s")
                except Exception:
                    pass
                break
            if j < len(msgs):
                ti += 1
                i = j + 1
            else:
                i += 1
        else:
            i += 1

if patched > 0:
    charts_html = os.path.join(tracking_dir, "charts.html")
    os.system(f'python3 "{SCRIPT_DIR}/generate-charts.py" "{tracking_dir}" "{charts_html}" 2>/dev/null')

print(f"{patched} turn(s) patched.")
