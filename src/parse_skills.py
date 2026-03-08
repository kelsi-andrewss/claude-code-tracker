#!/usr/bin/env python3
"""
Parse Skill tool invocations from Claude Code JSONL transcripts.

Usage:
  python3 parse_skills.py <transcript_path> <tracking_dir> <session_id> <project>
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


def parse_skills(transcript_path, session_id, project):
    """Parse JSONL transcript for Skill tool_use blocks.
    Returns list of dicts ready for storage.replace_session_skills()."""
    lines = []
    with open(transcript_path, encoding='utf-8') as f:
        for raw in f:
            try:
                obj = json.loads(raw)
                lines.append(obj)
            except Exception:
                pass

    pending = {}  # tool_use_id -> {skill_name, args, tool_use_id, timestamp}
    entries = []

    for obj in lines:
        ts = obj.get('timestamp', '')
        msg = obj.get('message', {})
        if not isinstance(msg, dict):
            continue
        content_blocks = msg.get('content', [])
        if not isinstance(content_blocks, list):
            continue

        for block in content_blocks:
            if not isinstance(block, dict):
                continue
            btype = block.get('type')

            if btype == 'tool_use' and block.get('name') == 'Skill':
                tool_use_id = block.get('id', '')
                inp = block.get('input', {})
                pending[tool_use_id] = {
                    'skill_name': inp.get('skill', 'unknown'),
                    'args': inp.get('args'),
                    'tool_use_id': tool_use_id,
                    'timestamp': ts,
                }

            elif btype == 'tool_result':
                tool_use_id = block.get('tool_use_id', '')
                if tool_use_id not in pending:
                    continue

                info = pending.pop(tool_use_id)
                is_error = block.get('is_error', False)

                error_content = None
                if is_error:
                    raw_content = block.get('content', '')
                    if isinstance(raw_content, str):
                        error_content = raw_content
                    elif isinstance(raw_content, list):
                        error_content = ' '.join(
                            c.get('text', '') for c in raw_content
                            if isinstance(c, dict) and c.get('type') == 'text')

                duration = 0
                if info['timestamp'] and ts:
                    try:
                        use_ts = datetime.fromisoformat(
                            info['timestamp'].replace('Z', '+00:00'))
                        result_ts = datetime.fromisoformat(
                            ts.replace('Z', '+00:00'))
                        duration = max(0, int((result_ts - use_ts).total_seconds()))
                    except Exception:
                        pass

                entries.append({
                    'session_id': session_id,
                    'date': make_date(info['timestamp']),
                    'project': project,
                    'skill_name': info['skill_name'],
                    'args': info['args'],
                    'tool_use_id': info['tool_use_id'],
                    'timestamp': info['timestamp'],
                    'duration_seconds': duration,
                    'success': 0 if is_error else 1,
                    'error_message': error_content if is_error else None,
                })

    # Flush unmatched pending skills
    for tool_use_id, info in pending.items():
        entries.append({
            'session_id': session_id,
            'date': make_date(info['timestamp']),
            'project': project,
            'skill_name': info['skill_name'],
            'args': info['args'],
            'tool_use_id': info['tool_use_id'],
            'timestamp': info['timestamp'],
            'duration_seconds': 0,
            'success': 1,
            'error_message': None,
        })

    return entries


if __name__ == '__main__':
    if len(sys.argv) != 5:
        print(f"Usage: {sys.argv[0]} <transcript_path> <tracking_dir> <session_id> <project>",
              file=sys.stderr)
        sys.exit(1)

    transcript_path, tracking_dir, session_id, project = sys.argv[1:5]
    entries = parse_skills(transcript_path, session_id, project)
    storage.replace_session_skills(tracking_dir, session_id, entries)
