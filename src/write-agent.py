#!/usr/bin/env python3
"""Parse subagent transcript JSONL and write aggregated token usage to SQLite."""
import sys, json, os
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cost import compute_cost


def aggregate_agent_usage(transcript_path):
    """Sum usage across all assistant messages in a transcript.

    Returns a dict with keys: input_tokens, output_tokens, cache_creation_tokens,
    cache_read_tokens, total_tokens, turns, model, first_timestamp.
    Returns None if total tokens = 0.
    """
    total_inp = total_out = total_cache_create = total_cache_read = 0
    model = "unknown"
    turns = 0
    first_ts = None

    with open(transcript_path, encoding='utf-8') as f:
        for line in f:
            try:
                obj = json.loads(line)
                msg = obj.get('message', {})
                if not isinstance(msg, dict):
                    continue
                if msg.get('role') == 'assistant':
                    usage = msg.get('usage', {})
                    if usage:
                        total_inp          += usage.get('input_tokens', 0)
                        total_out          += usage.get('output_tokens', 0)
                        total_cache_create += usage.get('cache_creation_input_tokens', 0)
                        total_cache_read   += usage.get('cache_read_input_tokens', 0)
                        turns += 1
                    m = msg.get('model', '')
                    if m:
                        model = m
                ts = obj.get('timestamp')
                if ts and first_ts is None:
                    first_ts = ts
            except:
                pass

    total = total_inp + total_out + total_cache_create + total_cache_read
    if total == 0:
        return None

    return {
        'input_tokens': total_inp,
        'output_tokens': total_out,
        'cache_creation_tokens': total_cache_create,
        'cache_read_tokens': total_cache_read,
        'total_tokens': total,
        'turns': turns,
        'model': model,
        'first_timestamp': first_ts,
    }


def build_agent_entry(usage_data, session_id, agent_id, agent_type):
    """Build a single agent entry dict from aggregated usage data.

    usage_data: dict returned by aggregate_agent_usage()
    Returns a dict ready for storage.append_agent().
    """
    cost = compute_cost(
        usage_data['input_tokens'],
        usage_data['output_tokens'],
        usage_data['cache_creation_tokens'],
        usage_data['cache_read_tokens'],
        usage_data['model'],
    )

    try:
        ts_str = datetime.fromisoformat(
            usage_data['first_timestamp'].replace('Z', '+00:00')
        ).strftime('%Y-%m-%dT%H:%M:%SZ')
    except:
        ts_str = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

    return {
        'timestamp':             ts_str,
        'session_id':            session_id,
        'agent_id':              agent_id,
        'agent_type':            agent_type,
        'input_tokens':          usage_data['input_tokens'],
        'output_tokens':         usage_data['output_tokens'],
        'cache_creation_tokens': usage_data['cache_creation_tokens'],
        'cache_read_tokens':     usage_data['cache_read_tokens'],
        'total_tokens':          usage_data['total_tokens'],
        'turns':                 usage_data['turns'],
        'estimated_cost_usd':    round(cost, 4),
        'model':                 usage_data['model'],
    }


if __name__ == '__main__':
    import storage

    transcript_path = sys.argv[1]
    tracking_dir = sys.argv[2]
    session_id = sys.argv[3]
    agent_id = sys.argv[4]
    agent_type = sys.argv[5]

    usage_data = aggregate_agent_usage(transcript_path)
    if usage_data is None:
        sys.exit(0)

    entry = build_agent_entry(usage_data, session_id, agent_id, agent_type)
    storage.append_agent(tracking_dir, entry)
