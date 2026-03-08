#!/usr/bin/env python3
"""
Parse context compaction events from Claude Code JSONL transcripts.

Usage:
  python3 parse_compactions.py <transcript_path> <tracking_dir> <session_id> <project>
"""
import json
import os
import sys
from datetime import date, datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import storage


def make_date(timestamp):
    try:
        return datetime.fromisoformat(
            timestamp.replace('Z', '+00:00')).strftime('%Y-%m-%d')
    except Exception:
        return date.today().isoformat()


def parse_compactions(transcript_path, session_id, project):
    """Parse JSONL transcript for compact_boundary system events.

    Derives turn_index by counting user/assistant pairs before each event.
    Returns list of dicts ready for storage.replace_session_compactions().
    """
    lines = []
    with open(transcript_path, encoding='utf-8') as f:
        for raw in f:
            try:
                obj = json.loads(raw)
                lines.append(obj)
            except Exception:
                pass

    # Build turn boundaries for turn_index calculation
    msg_list = []
    for obj in lines:
        ts = obj.get('timestamp', '')
        t = obj.get('type')
        if t == 'user' and not obj.get('isSidechain') and ts:
            msg_list.append(('user', ts))
        elif t == 'assistant' and ts:
            msg_list.append(('assistant', ts))

    # Pair user->assistant for turn boundaries
    turn_boundaries = []
    idx = 0
    while idx < len(msg_list):
        if msg_list[idx][0] == 'user':
            j = idx + 1
            while j < len(msg_list) and msg_list[j][0] != 'assistant':
                j += 1
            if j < len(msg_list):
                turn_boundaries.append((msg_list[idx][1], msg_list[j][1]))
                idx = j + 1
            else:
                idx += 1
        else:
            idx += 1

    def get_turn_index(timestamp):
        if not timestamp:
            return 0
        for ti, (user_ts, asst_ts) in enumerate(turn_boundaries):
            if timestamp <= asst_ts:
                return ti
            if ti + 1 < len(turn_boundaries):
                next_user_ts = turn_boundaries[ti + 1][0]
                if asst_ts < timestamp < next_user_ts:
                    return ti
        return max(0, len(turn_boundaries) - 1)

    entries = []
    for obj in lines:
        if obj.get('type') != 'system':
            continue
        if obj.get('subtype') != 'compact_boundary':
            continue

        ts = obj.get('timestamp', '')
        meta = obj.get('compactMetadata', {})
        if not isinstance(meta, dict):
            meta = {}

        entries.append({
            'session_id': session_id,
            'date': make_date(ts),
            'project': project,
            'timestamp': ts,
            'trigger': meta.get('trigger', 'auto'),
            'pre_tokens': meta.get('preTokens', 0),
            'turn_index': get_turn_index(ts),
        })

    return entries


if __name__ == '__main__':
    if len(sys.argv) != 5:
        print(f"Usage: {sys.argv[0]} <transcript_path> <tracking_dir> <session_id> <project>",
              file=sys.stderr)
        sys.exit(1)

    transcript_path, tracking_dir, session_id, project = sys.argv[1:5]
    entries = parse_compactions(transcript_path, session_id, project)
    storage.replace_session_compactions(tracking_dir, session_id, entries)
