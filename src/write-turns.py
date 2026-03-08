#!/usr/bin/env python3
"""Parse transcript JSONL and write per-turn token usage to SQLite."""
import sys, json, os
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cost import compute_cost


def parse_transcript(transcript_path):
    """Read JSONL transcript and return (msgs, usages, model).

    msgs: list of (role, timestamp) tuples
    usages: list of usage dicts from assistant messages, in order
    model: last model string seen, or 'unknown'
    """
    msgs = []
    usages = []
    model = "unknown"

    with open(transcript_path, encoding='utf-8') as f:
        for line in f:
            try:
                obj = json.loads(line)
                t = obj.get('type')
                ts = obj.get('timestamp')
                if t == 'user' and not obj.get('isSidechain') and ts:
                    msgs.append(('user', ts))
                elif t == 'assistant' and ts:
                    msgs.append(('assistant', ts))
                msg = obj.get('message', {})
                if isinstance(msg, dict) and msg.get('role') == 'assistant':
                    usage = msg.get('usage', {})
                    if usage:
                        usages.append(usage)
                    m = msg.get('model', '')
                    if m:
                        model = m
            except:
                pass

    return msgs, usages, model


def build_turn_entries(msgs, usages, model, session_id, project_name):
    """Pair user/assistant messages and compute per-turn token usage entries.

    Returns a list of dicts ready for storage.upsert_turns().
    """
    turn_entries = []
    turn_index = 0
    usage_index = 0
    i = 0
    while i < len(msgs):
        if msgs[i][0] == 'user':
            user_ts = msgs[i][1]
            j = i + 1
            while j < len(msgs) and msgs[j][0] != 'assistant':
                j += 1
            if j < len(msgs):
                asst_ts = msgs[j][1]
                usage = {}
                if usage_index < len(usages):
                    usage = usages[usage_index]
                    usage_index += 1

                inp = usage.get('input_tokens', 0)
                out = usage.get('output_tokens', 0)
                cache_create = usage.get('cache_creation_input_tokens', 0)
                cache_read = usage.get('cache_read_input_tokens', 0)
                total = inp + cache_create + cache_read + out

                if total > 0:
                    duration = 0
                    try:
                        t0 = datetime.fromisoformat(user_ts.replace('Z', '+00:00'))
                        t1 = datetime.fromisoformat(asst_ts.replace('Z', '+00:00'))
                        duration = max(0, int((t1 - t0).total_seconds()))
                    except:
                        pass

                    cost = compute_cost(inp, out, cache_create, cache_read, model)

                    try:
                        turn_ts = datetime.fromisoformat(user_ts.replace('Z', '+00:00')).strftime('%Y-%m-%dT%H:%M:%SZ')
                        turn_date = datetime.fromisoformat(user_ts.replace('Z', '+00:00')).strftime('%Y-%m-%d')
                    except:
                        turn_ts = user_ts
                        turn_date = date.today().isoformat()

                    turn_entries.append({
                        'date': turn_date,
                        'project': project_name,
                        'session_id': session_id,
                        'turn_index': turn_index,
                        'turn_timestamp': turn_ts,
                        'input_tokens': inp,
                        'cache_creation_tokens': cache_create,
                        'cache_read_tokens': cache_read,
                        'output_tokens': out,
                        'total_tokens': total,
                        'estimated_cost_usd': round(cost, 4),
                        'model': model,
                        'duration_seconds': duration,
                    })
                turn_index += 1
                i = j + 1
            else:
                i += 1
        else:
            i += 1

    return turn_entries


if __name__ == '__main__':
    import storage

    transcript_path = sys.argv[1]
    tracking_dir = sys.argv[2]
    session_id = sys.argv[3]
    project_name = sys.argv[4]

    msgs, usages, model = parse_transcript(transcript_path)
    turn_entries = build_turn_entries(msgs, usages, model, session_id, project_name)

    if not turn_entries:
        sys.exit(0)

    storage.upsert_turns(tracking_dir, turn_entries)
