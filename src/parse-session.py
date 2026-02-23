#!/usr/bin/env python3
"""
Parse token usage from a Claude Code JSONL transcript and upsert into tokens.json.

Extracted from the inline Python heredoc in stop-hook.sh so that it can be
called cross-platform by both stop-hook.sh (macOS/Linux) and stop-hook.js
(Windows).

Usage:
    python parse-session.py <transcript_path> <tokens_file> <session_id> <project_name>
"""
import sys
import json
import os
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_key_prompts import extract_prompts_from_jsonl, write_key_prompts


def main():
    transcript_path = sys.argv[1]
    tokens_file = sys.argv[2]
    session_id = sys.argv[3]
    project_name = sys.argv[4]

    # ------------------------------------------------------------------
    # Parse the JSONL transcript
    # ------------------------------------------------------------------
    msgs = []       # (role, timestamp)
    usages = []     # usage dicts from assistant messages, in order
    model = "unknown"

    with open(transcript_path, encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
                t = obj.get("type")
                ts = obj.get("timestamp")
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

    # ------------------------------------------------------------------
    # Build per-turn entries
    # ------------------------------------------------------------------
    turn_entries = []
    turn_index = 0
    usage_index = 0
    i = 0

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
                        cost = (inp * 15 / 1e6
                                + cache_create * 18.75 / 1e6
                                + cache_read * 1.50 / 1e6
                                + out * 75 / 1e6)
                    else:
                        cost = (inp * 3 / 1e6
                                + cache_create * 3.75 / 1e6
                                + cache_read * 0.30 / 1e6
                                + out * 15 / 1e6)

                    try:
                        turn_ts = datetime.fromisoformat(
                            user_ts.replace("Z", "+00:00")
                        ).strftime("%Y-%m-%dT%H:%M:%SZ")
                        turn_date = datetime.fromisoformat(
                            user_ts.replace("Z", "+00:00")
                        ).strftime("%Y-%m-%d")
                    except Exception:
                        turn_ts = user_ts
                        turn_date = date.today().isoformat()

                    turn_entries.append({
                        "date": turn_date,
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

    if not turn_entries:
        sys.exit(0)

    # ------------------------------------------------------------------
    # Load existing tokens.json and upsert
    # ------------------------------------------------------------------
    data = []
    if os.path.exists(tokens_file):
        try:
            with open(tokens_file, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = []

    # Build index of existing (session_id, turn_index) -> position
    existing_idx = {}
    for pos, e in enumerate(data):
        key = (e.get("session_id"), e.get("turn_index"))
        existing_idx[key] = pos

    # Check if anything actually changed
    changed = False
    for entry in turn_entries:
        key = (entry["session_id"], entry["turn_index"])
        if key not in existing_idx:
            changed = True
            break
        existing = data[existing_idx[key]]
        if (existing.get("total_tokens") != entry["total_tokens"]
                or existing.get("output_tokens") != entry["output_tokens"]):
            changed = True
            break

    if not changed:
        sys.exit(0)

    # Upsert: update existing entries or append new ones
    for entry in turn_entries:
        key = (entry["session_id"], entry["turn_index"])
        if key in existing_idx:
            data[existing_idx[key]] = entry
        else:
            data.append(entry)
            existing_idx[key] = len(data) - 1

    # Sort by (date, session_id, turn_index)
    data.sort(key=lambda x: (
        x.get("date", ""),
        x.get("session_id", ""),
        x.get("turn_index", 0),
    ))

    with open(tokens_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    # --- Extract key prompts from this session ---
    tracking_dir = os.path.dirname(tokens_file)
    prompts = extract_prompts_from_jsonl(transcript_path, session_id)
    if prompts:
        write_key_prompts(tracking_dir, prompts)


if __name__ == "__main__":
    main()
