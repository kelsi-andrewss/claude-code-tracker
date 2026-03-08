#!/usr/bin/env python3
"""
Parse friction events from Claude Code JSONL transcripts.

Usage:
  python3 parse_friction.py <transcript_path> <friction_file> <session_id> <project> <source> \
    [--agent-type TYPE] [--agent-id ID]

Friction categories (priority order, first match wins):
  permission_denied, hook_blocked, cascade_error, command_failed, tool_error, correction, retry
"""
import sys, json, os, argparse


def parse_friction(transcript_path, session_id, project, source,
                   agent_type=None, agent_id=None):
    """Parse a JSONL transcript and return a list of friction event dicts."""
    events = []
    pending_tools = {}       # tool_use_id -> {name, turn_index, timestamp}
    last_error_by_tool = {}  # tool_name -> tool_use_id of last errored call
    skill_stack = []         # [(tool_use_id, skill_name)]

    msgs = []  # (role, timestamp, is_sidechain, user_type)
    lines = [] # raw parsed objects
    model = "unknown"

    with open(transcript_path, encoding='utf-8') as f:
        for line in f:
            try:
                obj = json.loads(line)
                lines.append(obj)
                t = obj.get('type')
                ts = obj.get('timestamp')
                if t == 'user' and ts:
                    msgs.append(('user', ts, obj.get('isSidechain', False),
                                 obj.get('userType')))
                elif t == 'assistant' and ts:
                    msgs.append(('assistant', ts, False, None))
                msg = obj.get('message', {})
                if isinstance(msg, dict) and msg.get('role') == 'assistant':
                    m = msg.get('model', '')
                    if m:
                        model = m
            except Exception:
                pass

    # Build turn boundaries: user (non-sidechain) -> next assistant
    turn_boundaries = []  # [(user_msg_idx, asst_msg_idx)]
    i = 0
    while i < len(msgs):
        if msgs[i][0] == 'user' and not msgs[i][2]:
            j = i + 1
            while j < len(msgs) and msgs[j][0] != 'assistant':
                j += 1
            if j < len(msgs):
                turn_boundaries.append((i, j))
                i = j + 1
            else:
                i += 1
        else:
            i += 1

    def get_turn_index(timestamp):
        if not timestamp:
            return 0
        for idx, (ui, ai) in enumerate(turn_boundaries):
            user_ts = msgs[ui][1]
            asst_ts = msgs[ai][1]
            if user_ts <= timestamp <= asst_ts:
                return idx
            if idx + 1 < len(turn_boundaries):
                next_user_ts = msgs[turn_boundaries[idx + 1][0]][1]
                if asst_ts <= timestamp < next_user_ts:
                    return idx
        return max(0, len(turn_boundaries) - 1)

    def make_date(timestamp):
        try:
            from datetime import datetime
            return datetime.fromisoformat(
                timestamp.replace('Z', '+00:00')).strftime('%Y-%m-%d')
        except Exception:
            from datetime import date
            return date.today().isoformat()

    def current_skill():
        return skill_stack[-1][1] if skill_stack else None

    def make_event(timestamp, turn_index, category, tool_name, detail, resolved=None):
        return {
            'timestamp': timestamp or '',
            'date': make_date(timestamp),
            'session_id': session_id,
            'turn_index': turn_index,
            'source': source,
            'agent_type': agent_type,
            'agent_id': agent_id,
            'project': project,
            'category': category,
            'tool_name': tool_name,
            'skill': current_skill(),
            'model': model,
            'detail': (detail or '')[:500],
            'resolved': resolved,
        }

    # Second pass: detect friction
    for obj in lines:
        ts = obj.get('timestamp', '')
        turn_idx = get_turn_index(ts)
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

            if btype == 'tool_use':
                tool_id = block.get('id', '')
                tool_name = block.get('name', '')
                pending_tools[tool_id] = {
                    'name': tool_name,
                    'turn_index': turn_idx,
                    'timestamp': ts,
                }
                if tool_name == 'Skill':
                    skill_name = block.get('input', {}).get('skill', '')
                    if skill_name:
                        skill_stack.append((tool_id, skill_name))

            elif btype == 'tool_result':
                tool_id = block.get('tool_use_id', '')
                is_error = block.get('is_error', False)
                content = ''
                raw_content = block.get('content', '')
                if isinstance(raw_content, str):
                    content = raw_content
                elif isinstance(raw_content, list):
                    content = ' '.join(
                        c.get('text', '') for c in raw_content
                        if isinstance(c, dict) and c.get('type') == 'text')

                tool_info = pending_tools.get(tool_id, {})
                tool_name = tool_info.get('name', '')

                # Pop skill stack if this is a Skill tool result
                if skill_stack and skill_stack[-1][0] == tool_id:
                    skill_stack.pop()

                content_lower = content.lower()

                # Check if this is a retry of a previously errored tool
                if tool_name and tool_name in last_error_by_tool:
                    if not is_error:
                        events.append(make_event(ts, turn_idx, 'retry',
                                                 tool_name, 'Retry succeeded', True))
                        del last_error_by_tool[tool_name]
                    else:
                        events.append(make_event(ts, turn_idx, 'retry',
                                                 tool_name, 'Retry failed', False))

                if not is_error:
                    continue

                # Priority 1: permission_denied
                if ("user doesn't want to proceed" in content_lower or
                        "tool use was rejected" in content_lower):
                    events.append(make_event(ts, turn_idx, 'permission_denied',
                                             tool_name, content))
                    last_error_by_tool[tool_name] = tool_id
                    continue

                # Priority 2: hook_blocked
                if 'pretooluse:' in content_lower and 'blocked' in content_lower:
                    events.append(make_event(ts, turn_idx, 'hook_blocked',
                                             tool_name, content))
                    last_error_by_tool[tool_name] = tool_id
                    continue

                # Priority 3: cascade_error
                if 'sibling tool call errored' in content_lower:
                    events.append(make_event(ts, turn_idx, 'cascade_error',
                                             tool_name, content))
                    continue

                # Priority 4: command_failed
                if tool_name == 'Bash' and content.startswith('Exit code '):
                    events.append(make_event(ts, turn_idx, 'command_failed',
                                             tool_name, content))
                    last_error_by_tool[tool_name] = tool_id
                    continue

                # Priority 5: tool_error (catch-all for is_error=true)
                events.append(make_event(ts, turn_idx, 'tool_error',
                                         tool_name, content))
                last_error_by_tool[tool_name] = tool_id

        # Check for corrections: user messages
        obj_type = obj.get('type')
        user_type = obj.get('userType')
        is_sidechain = obj.get('isSidechain', False)
        if obj_type == 'user' and user_type == 'human' and not is_sidechain:
            text = ''
            if isinstance(content_blocks, list):
                texts = [c.get('text', '') for c in content_blocks
                         if isinstance(c, dict) and c.get('type') == 'text']
                text = ' '.join(texts).strip()
            elif isinstance(msg.get('content'), str):
                text = msg['content'].strip()

            if text:
                text_lower = text.lower()
                first_100 = text_lower[:100]
                is_correction = False

                for prefix in ('no,', 'no ', 'wrong', 'stop', 'wait', 'actually,'):
                    if text_lower.startswith(prefix):
                        is_correction = True
                        break

                if not is_correction:
                    for phrase in ("that's wrong", "not what i", "i said", "i meant"):
                        if phrase in first_100:
                            is_correction = True
                            break

                if is_correction:
                    events.append(make_event(ts, turn_idx, 'correction',
                                             None, text[:200]))

    return events


def upsert_friction(friction_file, session_id, new_events):
    """Load existing friction.json, remove events for session_id, add new, sort, write."""
    data = []
    if os.path.exists(friction_file):
        try:
            with open(friction_file, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = []

    data = [e for e in data if e.get('session_id') != session_id]
    data.extend(new_events)

    data.sort(key=lambda x: (x.get('date', ''), x.get('session_id', ''),
                              x.get('turn_index', 0)))

    os.makedirs(os.path.dirname(os.path.abspath(friction_file)), exist_ok=True)
    with open(friction_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
        f.write('\n')

    return data


def main():
    parser = argparse.ArgumentParser(description='Parse friction events from JSONL transcript')
    parser.add_argument('transcript_path')
    parser.add_argument('friction_file')
    parser.add_argument('session_id')
    parser.add_argument('project')
    parser.add_argument('source')
    parser.add_argument('--agent-type', default=None)
    parser.add_argument('--agent-id', default=None)
    args = parser.parse_args()

    events = parse_friction(args.transcript_path, args.session_id, args.project,
                            args.source, args.agent_type, args.agent_id)

    if events:
        upsert_friction(args.friction_file, args.session_id, events)
        print(f"{len(events)} friction event(s) recorded.")
    else:
        upsert_friction(args.friction_file, args.session_id, [])


if __name__ == '__main__':
    main()
