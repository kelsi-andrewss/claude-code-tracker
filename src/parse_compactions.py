#!/usr/bin/env python3
"""
Parse compaction (compact_boundary) events from Claude Code JSONL transcripts.

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
    Returns list of dicts ready for storage.replace_session_compactions()."""
    entries = []
    with open(transcript_path, encoding='utf-8') as f:
        for raw in f:
            try:
                obj = json.loads(raw)
            except Exception:
                continue

            if obj.get('type') != 'system' or obj.get('subtype') != 'compact_boundary':
                continue

            ts = obj.get('timestamp', '')
            meta = obj.get('compactMetadata', {})

            entries.append({
                'session_id': session_id,
                'date': make_date(ts),
                'project': project,
                'timestamp': ts,
                'trigger': meta.get('trigger', 'auto'),
                'pre_tokens': meta.get('preTokens', 0),
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
