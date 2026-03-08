#!/usr/bin/env python3
"""Parse subagent transcript JSONL and write aggregated token usage to SQLite."""
import sys, json, os
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import storage

transcript_path = sys.argv[1]
tracking_dir = sys.argv[2]
session_id = sys.argv[3]
agent_id = sys.argv[4]
agent_type = sys.argv[5]

# Sum usage across ALL assistant messages in the transcript
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
    sys.exit(0)

if 'opus' in model:
    cost = total_inp * 15/1e6 + total_cache_create * 18.75/1e6 + total_cache_read * 1.50/1e6 + total_out * 75/1e6
else:
    cost = total_inp * 3/1e6 + total_cache_create * 3.75/1e6 + total_cache_read * 0.30/1e6 + total_out * 15/1e6

try:
    ts_str = datetime.fromisoformat(first_ts.replace('Z', '+00:00')).strftime('%Y-%m-%dT%H:%M:%SZ')
except:
    ts_str = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

entry = {
    'timestamp':             ts_str,
    'session_id':            session_id,
    'agent_id':              agent_id,
    'agent_type':            agent_type,
    'input_tokens':          total_inp,
    'output_tokens':         total_out,
    'cache_creation_tokens': total_cache_create,
    'cache_read_tokens':     total_cache_read,
    'total_tokens':          total,
    'turns':                 turns,
    'estimated_cost_usd':    round(cost, 4),
    'model':                 model,
}

storage.append_agent(tracking_dir, entry)
