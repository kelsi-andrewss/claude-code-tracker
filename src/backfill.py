#!/usr/bin/env python3
"""
Backfill historical Claude Code sessions into tracking.db.

Usage:
  python3 backfill.py <project_root>

Scans ~/.claude/projects/<slug>/*.jsonl for transcripts belonging to the
given project, parses token usage from each turn, and upserts entries to
<project_root>/.claude/tracking/tracking.db. Sessions where all turns are
already present are skipped.
"""
import sys, json, os, glob
from datetime import datetime
from platform_utils import get_transcripts_dir, slugify_path
from cost import compute_cost
import storage

project_root = os.path.abspath(sys.argv[1])
project_name = os.path.basename(project_root)
tracking_dir = os.path.join(project_root, ".claude", "tracking")

# Claude Code slugifies project paths: replace "/" with "-"
slug = slugify_path(project_root)
transcripts_dir = os.path.join(get_transcripts_dir(), slug)

if not os.path.isdir(transcripts_dir):
    print("No transcript directory found, nothing to backfill.")
    sys.exit(0)

def parse_turns(jf):
    """Parse a JSONL transcript into per-turn entries. Returns list of dicts."""
    msgs = []       # (role, timestamp)
    usages = []     # usage dicts from assistant messages, in order
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
        return [], None, "unknown"

    return msgs, first_ts, model, usages

def compute_turns(msgs, usages, first_ts, model, session_id, project_name):
    """Convert message list + usages into per-turn entry dicts."""
    entries = []
    turn_index = 0
    usage_index = 0
    i = 0

    # Date from first timestamp
    session_date = None
    if first_ts:
        try:
            session_date = datetime.fromisoformat(
                first_ts.replace("Z", "+00:00")
            ).strftime("%Y-%m-%d")
        except Exception:
            pass

    while i < len(msgs):
        if msgs[i][0] == "user":
            user_ts = msgs[i][1]
            j = i + 1
            while j < len(msgs) and msgs[j][0] != "assistant":
                j += 1
            if j < len(msgs):
                asst_ts = msgs[j][1]
                # Consume next usage block for this turn
                usage = {}
                if usage_index < len(usages):
                    usage = usages[usage_index]
                    usage_index += 1

                inp = usage.get("input_tokens", 0)
                out = usage.get("output_tokens", 0)
                cache_create = usage.get("cache_creation_input_tokens", 0)
                cache_read = usage.get("cache_read_input_tokens", 0)
                total = inp + cache_create + cache_read + out

                if total == 0:
                    # Skip turns with no token data
                    i = j + 1
                    turn_index += 1
                    continue

                duration = 0
                try:
                    t0 = datetime.fromisoformat(user_ts.replace("Z", "+00:00"))
                    t1 = datetime.fromisoformat(asst_ts.replace("Z", "+00:00"))
                    duration = max(0, int((t1 - t0).total_seconds()))
                except Exception:
                    pass

                cost = compute_cost(inp, out, cache_create, cache_read, model)

                # Turn timestamp = user message timestamp
                turn_ts = user_ts
                # Normalize to Z format
                try:
                    turn_ts = datetime.fromisoformat(user_ts.replace("Z", "+00:00")).strftime("%Y-%m-%dT%H:%M:%SZ")
                except Exception:
                    pass

                # Use date from this turn's timestamp if possible
                turn_date = session_date
                try:
                    turn_date = datetime.fromisoformat(user_ts.replace("Z", "+00:00")).strftime("%Y-%m-%d")
                except Exception:
                    pass

                entries.append({
                    "date": turn_date or session_date,
                    "project": project_name,
                    "session_id": session_id,
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

    return entries

# Find all JSONL transcripts
jsonl_files = sorted(glob.glob(os.path.join(transcripts_dir, "*.jsonl")))
new_entries = []
sessions_processed = 0

for jf in jsonl_files:
    session_id = os.path.splitext(os.path.basename(jf))[0]

    result = parse_turns(jf)
    if len(result) == 4:
        msgs, first_ts, model, usages = result
    else:
        continue

    turn_entries = compute_turns(msgs, usages, first_ts, model, session_id, project_name)

    if not turn_entries:
        continue

    expected_count = len(turn_entries)
    existing_count = storage.count_turns_for_session(tracking_dir, session_id)

    if existing_count >= expected_count:
        continue

    # Replace all turns for this session with fresh data
    storage.replace_session_turns(tracking_dir, session_id, turn_entries)
    new_entries.extend(turn_entries)
    sessions_processed += 1

total_turns = len(new_entries)
print(f"{sessions_processed} session{'s' if sessions_processed != 1 else ''} processed, {total_turns} turn{'s' if total_turns != 1 else ''} written.")

# Backfill friction events from the same transcripts
from parse_friction import parse_friction, upsert_friction

friction_file = os.path.join(tracking_dir, "friction.json")
friction_count = 0
for jf in jsonl_files:
    session_id = os.path.splitext(os.path.basename(jf))[0]
    try:
        events = parse_friction(jf, session_id, project_name, "main")
        upsert_friction(friction_file, session_id, events)
        friction_count += len(events)
    except Exception:
        pass

if friction_count:
    print(f"{friction_count} friction event{'s' if friction_count != 1 else ''} backfilled.")

# Regenerate charts if we added anything
if new_entries or friction_count:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    charts_html = os.path.join(tracking_dir, "charts.html")
    os.system(f'python3 "{script_dir}/generate-charts.py" "{tracking_dir}" "{charts_html}" 2>/dev/null')
