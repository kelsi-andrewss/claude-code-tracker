#!/usr/bin/env python3
"""
Patch duration_seconds for per-turn entries that have duration 0,
and migrate old single-entry-per-session entries to per-turn format.

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
project_name = os.path.basename(project_root)

with open(tokens_file) as f:
    data = json.load(f)

def parse_transcript(jf):
    msgs = []
    usages = []
    model = "unknown"
    first_ts = None
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
                            usages.append(usage)
                        m = msg.get("model", "")
                        if m:
                            model = m
                except Exception:
                    pass
    except Exception:
        pass
    return msgs, usages, model, first_ts

# Separate old-format (no turn_index) from new-format entries
old_entries = [e for e in data if "turn_index" not in e]
new_entries = [e for e in data if "turn_index" in e]

# For new-format entries with duration 0, patch from transcript
existing_keys = {(e.get("session_id"), e.get("turn_index")): i for i, e in enumerate(new_entries)}
patched = 0

for entry in new_entries:
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
                        entry["duration_seconds"] = duration
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

# Migrate old-format entries to per-turn
migrated_sessions = 0
new_turn_entries = []
for old_entry in old_entries:
    sid = old_entry.get("session_id")
    if not sid:
        continue
    jf = os.path.join(transcripts_dir, sid + ".jsonl")
    if not os.path.exists(jf):
        # Keep old entry as-is if we can't reprocess
        new_entries.append(old_entry)
        continue

    msgs, usages, model, first_ts = parse_transcript(jf)

    turn_index = 0
    usage_index = 0
    i = 0
    session_date = old_entry.get("date")

    while i < len(msgs):
        if msgs[i][0] == "user":
            user_ts = msgs[i][1]
            j = i + 1
            while j < len(msgs) and msgs[j][0] != "assistant":
                j += 1
            if j < len(msgs):
                asst_ts = msgs[j][1]
                usage = {}
                if usage_index < len(usages):
                    usage = usages[usage_index]
                    usage_index += 1

                inp = usage.get("input_tokens", 0)
                out = usage.get("output_tokens", 0)
                cache_create = usage.get("cache_creation_input_tokens", 0)
                cache_read = usage.get("cache_read_input_tokens", 0)
                total = inp + cache_create + cache_read + out

                if total > 0:
                    duration = 0
                    try:
                        t0 = datetime.fromisoformat(user_ts.replace("Z", "+00:00"))
                        t1 = datetime.fromisoformat(asst_ts.replace("Z", "+00:00"))
                        duration = max(0, int((t1 - t0).total_seconds()))
                    except Exception:
                        pass

                    if "opus" in model:
                        cost = inp * 15 / 1e6 + cache_create * 18.75 / 1e6 + cache_read * 1.50 / 1e6 + out * 75 / 1e6
                    else:
                        cost = inp * 3 / 1e6 + cache_create * 3.75 / 1e6 + cache_read * 0.30 / 1e6 + out * 15 / 1e6

                    try:
                        turn_ts = datetime.fromisoformat(user_ts.replace("Z", "+00:00")).strftime("%Y-%m-%dT%H:%M:%SZ")
                        turn_date = datetime.fromisoformat(user_ts.replace("Z", "+00:00")).strftime("%Y-%m-%d")
                    except Exception:
                        turn_ts = user_ts
                        turn_date = session_date

                    new_turn_entries.append({
                        "date": turn_date,
                        "project": project_name,
                        "session_id": sid,
                        "turn_index": turn_index,
                        "turn_timestamp": turn_ts,
                        "input_tokens": inp,
                        "cache_creation_tokens": cache_create,
                        "cache_read_tokens": cache_read,
                        "output_tokens": out,
                        "total_tokens": total,
                        "estimated_cost_usd": round(cost, 4),
                        "model": model,
                        "duration_seconds": duration,
                    })
                turn_index += 1
                i = j + 1
            else:
                i += 1
        else:
            i += 1

    if turn_index > 0:
        migrated_sessions += 1
        print(f"  migrated {sid[:8]}  {turn_index} turn(s)")
    else:
        new_entries.append(old_entry)

new_entries.extend(new_turn_entries)
new_entries.sort(key=lambda x: (x.get("date", ""), x.get("session_id", ""), x.get("turn_index", 0)))

if patched > 0 or migrated_sessions > 0:
    with open(tokens_file, "w") as f:
        json.dump(new_entries, f, indent=2)
        f.write("\n")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    charts_html = os.path.join(tracking_dir, "charts.html")
    os.system(f'python3 "{script_dir}/generate-charts.py" "{tokens_file}" "{charts_html}" 2>/dev/null')

print(f"{patched} turn(s) patched, {migrated_sessions} session(s) migrated to per-turn format.")
