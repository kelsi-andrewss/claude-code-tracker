"""Tests for parse_friction.py — friction event detection from JSONL transcripts."""
import sys, os, json, tempfile, pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from parse_friction import parse_friction, upsert_friction


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(n):
    """Generate deterministic ISO timestamps for test data."""
    return f"2026-03-07T10:{n:02d}:00.000Z"


def _user_msg(text, ts, user_type='human', is_sidechain=False):
    """Build a user-type JSONL line."""
    return {
        'type': 'user',
        'timestamp': ts,
        'userType': user_type,
        'isSidechain': is_sidechain,
        'message': {
            'role': 'user',
            'content': [{'type': 'text', 'text': text}],
        },
    }


def _assistant_msg(content_blocks, ts, model='claude-sonnet-4-20250514'):
    """Build an assistant-type JSONL line with tool_use blocks."""
    return {
        'type': 'assistant',
        'timestamp': ts,
        'message': {
            'role': 'assistant',
            'model': model,
            'content': content_blocks,
        },
    }


def _tool_use(tool_id, name, input_data=None):
    return {'type': 'tool_use', 'id': tool_id, 'name': name,
            'input': input_data or {}}


def _tool_result(tool_use_id, content, is_error=False):
    return {'type': 'tool_result', 'tool_use_id': tool_use_id,
            'content': content, 'is_error': is_error}


def _write_jsonl(lines, path):
    with open(path, 'w') as f:
        for line in lines:
            f.write(json.dumps(line) + '\n')


def _build_transcript(lines):
    """Write lines to a temp JSONL file and return its path."""
    fd, path = tempfile.mkstemp(suffix='.jsonl')
    os.close(fd)
    _write_jsonl(lines, path)
    return path


# ---------------------------------------------------------------------------
# Synthetic transcript covering all friction categories
# ---------------------------------------------------------------------------

def _full_transcript():
    """
    Build a transcript with exactly these friction signals:

    Turn 0 (ts 00-01): user asks, assistant calls Edit -> tool_error ("Found 2 matches")
    Turn 1 (ts 02-03): user asks, assistant calls Grep -> permission_denied
    Turn 2 (ts 04-05): assistant calls Read -> cascade_error
    Turn 3 (ts 06-07): user asks, assistant calls Bash -> command_failed (Exit code 1)
    Turn 4 (ts 08-09): user says "no, use the other file" -> correction
    Turn 5 (ts 10-13): assistant calls Edit again (retry after turn 0 error) -> success
    Turn 6 (ts 14-17): assistant invokes Skill("audit"), inside which Edit errors -> tool_error with skill
    """
    lines = []

    # -- Turn 0: tool_error (Edit "Found 2 matches") --
    lines.append(_user_msg("fix the import", _ts(0)))
    lines.append(_assistant_msg([
        _tool_use('tu-1', 'Edit', {'file_path': '/foo.py', 'old_string': 'x', 'new_string': 'y'}),
    ], _ts(1)))
    lines.append(_assistant_msg([
        _tool_result('tu-1', 'Found 2 matches for old_string in the file. Please provide a unique string.', is_error=True),
    ], _ts(1)))

    # -- Turn 1: permission_denied --
    lines.append(_user_msg("search for it", _ts(2)))
    lines.append(_assistant_msg([
        _tool_use('tu-2', 'Grep'),
    ], _ts(3)))
    lines.append(_assistant_msg([
        _tool_result('tu-2', "The user doesn't want to proceed with this tool use. The tool use was rejected.", is_error=True),
    ], _ts(3)))

    # -- Turn 2: cascade_error --
    lines.append(_user_msg("read the file", _ts(4)))
    lines.append(_assistant_msg([
        _tool_use('tu-3', 'Read'),
    ], _ts(5)))
    lines.append(_assistant_msg([
        _tool_result('tu-3', 'Sibling tool call errored. Skipping this tool call.', is_error=True),
    ], _ts(5)))

    # -- Turn 3: command_failed --
    lines.append(_user_msg("run the tests", _ts(6)))
    lines.append(_assistant_msg([
        _tool_use('tu-4', 'Bash', {'command': 'npm test'}),
    ], _ts(7)))
    lines.append(_assistant_msg([
        _tool_result('tu-4', 'Exit code 1\nError: test suite failed', is_error=True),
    ], _ts(7)))

    # -- Turn 4: correction --
    lines.append(_user_msg("no, use the other file", _ts(8)))
    lines.append(_assistant_msg([
        {'type': 'text', 'text': 'OK, let me use the other file.'},
    ], _ts(9)))

    # -- Turn 5: retry of Edit (was errored in turn 0) -> success --
    lines.append(_user_msg("try the edit again", _ts(10)))
    lines.append(_assistant_msg([
        _tool_use('tu-5', 'Edit', {'file_path': '/foo.py', 'old_string': 'x = 1', 'new_string': 'y = 1'}),
    ], _ts(11)))
    lines.append(_assistant_msg([
        _tool_result('tu-5', 'File edited successfully.', is_error=False),
    ], _ts(12)))
    lines.append(_assistant_msg([
        {'type': 'text', 'text': 'Done.'},
    ], _ts(13)))

    # -- Turn 6: Skill invocation wrapping a tool_error --
    lines.append(_user_msg("audit the code", _ts(14)))
    # Assistant invokes Skill tool
    lines.append(_assistant_msg([
        _tool_use('tu-skill', 'Skill', {'skill': 'audit'}),
    ], _ts(15)))
    # Inside the skill, an Edit call errors
    lines.append(_assistant_msg([
        _tool_use('tu-6', 'Edit', {'file_path': '/bar.py', 'old_string': 'a', 'new_string': 'b'}),
    ], _ts(16)))
    lines.append(_assistant_msg([
        _tool_result('tu-6', 'old_string not found in file.', is_error=True),
    ], _ts(16)))
    # Skill tool_result comes back (closes skill stack)
    lines.append(_assistant_msg([
        _tool_result('tu-skill', 'Audit complete.', is_error=False),
    ], _ts(17)))

    return lines


# ---------------------------------------------------------------------------
# Tests: parse_friction
# ---------------------------------------------------------------------------

class TestParseFriction:

    def test_detects_all_friction_categories(self, tmp_path):
        path = _build_transcript(_full_transcript())
        try:
            events = parse_friction(path, 'sess-1', 'test-proj', 'cli')
            categories = [e['category'] for e in events]

            assert 'tool_error' in categories
            assert 'permission_denied' in categories
            assert 'cascade_error' in categories
            assert 'command_failed' in categories
            assert 'correction' in categories
            assert 'retry' in categories
        finally:
            os.unlink(path)

    def test_event_count(self, tmp_path):
        """Exactly 7 events: tool_error, permission_denied, cascade_error,
        command_failed, correction, retry (resolved), tool_error (inside skill)."""
        path = _build_transcript(_full_transcript())
        try:
            events = parse_friction(path, 'sess-1', 'test-proj', 'cli')
            assert len(events) == 7, f"Expected 7 events, got {len(events)}: {[e['category'] for e in events]}"
        finally:
            os.unlink(path)

    def test_tool_error_detail_captured(self, tmp_path):
        path = _build_transcript(_full_transcript())
        try:
            events = parse_friction(path, 'sess-1', 'test-proj', 'cli')
            tool_errors = [e for e in events if e['category'] == 'tool_error'
                           and e.get('skill') is None]
            assert len(tool_errors) >= 1
            assert 'Found 2 matches' in tool_errors[0]['detail']
            assert tool_errors[0]['tool_name'] == 'Edit'
        finally:
            os.unlink(path)

    def test_permission_denied_detail(self, tmp_path):
        path = _build_transcript(_full_transcript())
        try:
            events = parse_friction(path, 'sess-1', 'test-proj', 'cli')
            pd = [e for e in events if e['category'] == 'permission_denied']
            assert len(pd) == 1
            assert pd[0]['tool_name'] == 'Grep'
            assert "user doesn't want to proceed" in pd[0]['detail'].lower()
        finally:
            os.unlink(path)

    def test_cascade_error_detail(self, tmp_path):
        path = _build_transcript(_full_transcript())
        try:
            events = parse_friction(path, 'sess-1', 'test-proj', 'cli')
            ce = [e for e in events if e['category'] == 'cascade_error']
            assert len(ce) == 1
            assert ce[0]['tool_name'] == 'Read'
        finally:
            os.unlink(path)

    def test_command_failed_detail(self, tmp_path):
        path = _build_transcript(_full_transcript())
        try:
            events = parse_friction(path, 'sess-1', 'test-proj', 'cli')
            cf = [e for e in events if e['category'] == 'command_failed']
            assert len(cf) == 1
            assert cf[0]['tool_name'] == 'Bash'
            assert cf[0]['detail'].startswith('Exit code 1')
        finally:
            os.unlink(path)

    def test_correction_detail(self, tmp_path):
        path = _build_transcript(_full_transcript())
        try:
            events = parse_friction(path, 'sess-1', 'test-proj', 'cli')
            corr = [e for e in events if e['category'] == 'correction']
            assert len(corr) == 1
            assert 'other file' in corr[0]['detail']
            assert corr[0]['tool_name'] is None
        finally:
            os.unlink(path)

    def test_retry_resolved_true(self, tmp_path):
        path = _build_transcript(_full_transcript())
        try:
            events = parse_friction(path, 'sess-1', 'test-proj', 'cli')
            retries = [e for e in events if e['category'] == 'retry']
            assert len(retries) == 1
            assert retries[0]['resolved'] is True
            assert retries[0]['tool_name'] == 'Edit'
        finally:
            os.unlink(path)

    def test_retry_resolved_false(self, tmp_path):
        """A retry that fails again should have resolved=False."""
        lines = []
        # Turn 0: Edit errors
        lines.append(_user_msg("fix it", _ts(0)))
        lines.append(_assistant_msg([_tool_use('a1', 'Edit')], _ts(1)))
        lines.append(_assistant_msg([
            _tool_result('a1', 'old_string not found', is_error=True),
        ], _ts(1)))
        # Turn 1: Edit retried, errors again
        lines.append(_user_msg("try again", _ts(2)))
        lines.append(_assistant_msg([_tool_use('a2', 'Edit')], _ts(3)))
        lines.append(_assistant_msg([
            _tool_result('a2', 'old_string not found', is_error=True),
        ], _ts(3)))

        path = _build_transcript(lines)
        try:
            events = parse_friction(path, 'sess-2', 'test-proj', 'cli')
            retries = [e for e in events if e['category'] == 'retry']
            assert len(retries) == 1
            assert retries[0]['resolved'] is False
        finally:
            os.unlink(path)

    def test_skill_name_captured(self, tmp_path):
        """When friction occurs inside a Skill invocation, skill name is captured."""
        path = _build_transcript(_full_transcript())
        try:
            events = parse_friction(path, 'sess-1', 'test-proj', 'cli')
            skill_events = [e for e in events if e.get('skill') is not None]
            assert len(skill_events) >= 1
            assert skill_events[0]['skill'] == 'audit'
            assert skill_events[0]['category'] == 'tool_error'
        finally:
            os.unlink(path)

    def test_non_skill_events_have_null_skill(self, tmp_path):
        path = _build_transcript(_full_transcript())
        try:
            events = parse_friction(path, 'sess-1', 'test-proj', 'cli')
            non_skill = [e for e in events if e.get('skill') is None]
            # All events except the one inside the Skill should have null skill
            assert len(non_skill) == 6
        finally:
            os.unlink(path)

    def test_session_and_project_propagated(self, tmp_path):
        path = _build_transcript(_full_transcript())
        try:
            events = parse_friction(path, 'my-session', 'my-project', 'hook')
            for e in events:
                assert e['session_id'] == 'my-session'
                assert e['project'] == 'my-project'
                assert e['source'] == 'hook'
        finally:
            os.unlink(path)

    def test_agent_type_and_id_propagated(self, tmp_path):
        path = _build_transcript(_full_transcript())
        try:
            events = parse_friction(path, 's1', 'p1', 'hook',
                                    agent_type='coder', agent_id='agent-42')
            for e in events:
                assert e['agent_type'] == 'coder'
                assert e['agent_id'] == 'agent-42'
        finally:
            os.unlink(path)

    def test_model_field_captured(self, tmp_path):
        path = _build_transcript(_full_transcript())
        try:
            events = parse_friction(path, 's1', 'p1', 'cli')
            for e in events:
                assert e['model'] == 'claude-sonnet-4-20250514'
        finally:
            os.unlink(path)

    def test_detail_truncated_to_500_chars(self, tmp_path):
        lines = []
        lines.append(_user_msg("go", _ts(0)))
        lines.append(_assistant_msg([_tool_use('x1', 'Bash', {'command': 'x'})], _ts(1)))
        long_detail = 'Exit code 1\n' + 'x' * 600
        lines.append(_assistant_msg([
            _tool_result('x1', long_detail, is_error=True),
        ], _ts(1)))
        path = _build_transcript(lines)
        try:
            events = parse_friction(path, 's', 'p', 'cli')
            assert len(events[0]['detail']) <= 500
        finally:
            os.unlink(path)

    def test_empty_transcript_returns_no_events(self, tmp_path):
        path = _build_transcript([])
        try:
            events = parse_friction(path, 's', 'p', 'cli')
            assert events == []
        finally:
            os.unlink(path)

    def test_sidechain_user_msg_not_correction(self, tmp_path):
        """Sidechain user messages should not trigger correction detection."""
        lines = []
        lines.append(_user_msg("do something", _ts(0)))
        lines.append(_assistant_msg([{'type': 'text', 'text': 'ok'}], _ts(1)))
        # Sidechain message with correction-like prefix
        lines.append(_user_msg("no, wrong approach", _ts(2),
                               user_type='human', is_sidechain=True))
        lines.append(_assistant_msg([{'type': 'text', 'text': 'ok'}], _ts(3)))
        path = _build_transcript(lines)
        try:
            events = parse_friction(path, 's', 'p', 'cli')
            corrections = [e for e in events if e['category'] == 'correction']
            assert len(corrections) == 0
        finally:
            os.unlink(path)

    def test_correction_phrases_in_body(self, tmp_path):
        """Correction phrases like 'that's wrong' and 'not what i' are detected."""
        lines = []
        lines.append(_user_msg("do something", _ts(0)))
        lines.append(_assistant_msg([{'type': 'text', 'text': 'ok'}], _ts(1)))
        lines.append(_user_msg("that's wrong, the function should return a list", _ts(2)))
        lines.append(_assistant_msg([{'type': 'text', 'text': 'ok'}], _ts(3)))
        path = _build_transcript(lines)
        try:
            events = parse_friction(path, 's', 'p', 'cli')
            corrections = [e for e in events if e['category'] == 'correction']
            assert len(corrections) == 1
        finally:
            os.unlink(path)

    def test_priority_permission_denied_over_tool_error(self, tmp_path):
        """permission_denied should match before generic tool_error."""
        lines = []
        lines.append(_user_msg("go", _ts(0)))
        lines.append(_assistant_msg([_tool_use('z1', 'Edit')], _ts(1)))
        lines.append(_assistant_msg([
            _tool_result('z1', "The user doesn't want to proceed. Also old_string not found.", is_error=True),
        ], _ts(1)))
        path = _build_transcript(lines)
        try:
            events = parse_friction(path, 's', 'p', 'cli')
            assert events[0]['category'] == 'permission_denied'
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Tests: upsert_friction
# ---------------------------------------------------------------------------

class TestUpsertFriction:

    def test_creates_file_when_missing(self, tmp_path):
        friction_file = str(tmp_path / 'friction.json')
        events = [{'session_id': 's1', 'date': '2026-03-07', 'turn_index': 0,
                    'category': 'tool_error'}]
        result = upsert_friction(friction_file, 's1', events)
        assert len(result) == 1
        assert os.path.exists(friction_file)
        with open(friction_file) as f:
            data = json.load(f)
        assert len(data) == 1

    def test_replaces_events_for_same_session(self, tmp_path):
        friction_file = str(tmp_path / 'friction.json')
        # First upsert
        events_v1 = [
            {'session_id': 's1', 'date': '2026-03-07', 'turn_index': 0,
             'category': 'tool_error'},
            {'session_id': 's1', 'date': '2026-03-07', 'turn_index': 1,
             'category': 'correction'},
        ]
        upsert_friction(friction_file, 's1', events_v1)

        # Second upsert with different events for same session
        events_v2 = [
            {'session_id': 's1', 'date': '2026-03-07', 'turn_index': 0,
             'category': 'command_failed'},
        ]
        result = upsert_friction(friction_file, 's1', events_v2)
        assert len(result) == 1
        assert result[0]['category'] == 'command_failed'

    def test_preserves_other_sessions(self, tmp_path):
        friction_file = str(tmp_path / 'friction.json')
        # Session 1
        upsert_friction(friction_file, 's1', [
            {'session_id': 's1', 'date': '2026-03-07', 'turn_index': 0,
             'category': 'tool_error'},
        ])
        # Session 2
        upsert_friction(friction_file, 's2', [
            {'session_id': 's2', 'date': '2026-03-07', 'turn_index': 0,
             'category': 'correction'},
        ])
        with open(friction_file) as f:
            data = json.load(f)
        sessions = {e['session_id'] for e in data}
        assert sessions == {'s1', 's2'}

    def test_empty_events_clears_session(self, tmp_path):
        friction_file = str(tmp_path / 'friction.json')
        upsert_friction(friction_file, 's1', [
            {'session_id': 's1', 'date': '2026-03-07', 'turn_index': 0,
             'category': 'tool_error'},
        ])
        upsert_friction(friction_file, 's1', [])
        with open(friction_file) as f:
            data = json.load(f)
        assert len(data) == 0

    def test_sorted_by_date_session_turn(self, tmp_path):
        friction_file = str(tmp_path / 'friction.json')
        upsert_friction(friction_file, 's2', [
            {'session_id': 's2', 'date': '2026-03-08', 'turn_index': 0,
             'category': 'tool_error'},
        ])
        upsert_friction(friction_file, 's1', [
            {'session_id': 's1', 'date': '2026-03-07', 'turn_index': 0,
             'category': 'correction'},
        ])
        with open(friction_file) as f:
            data = json.load(f)
        assert data[0]['date'] == '2026-03-07'
        assert data[1]['date'] == '2026-03-08'

    def test_handles_corrupt_friction_file(self, tmp_path):
        friction_file = str(tmp_path / 'friction.json')
        with open(friction_file, 'w') as f:
            f.write('not json{{{')
        events = [{'session_id': 's1', 'date': '2026-03-07', 'turn_index': 0,
                    'category': 'tool_error'}]
        result = upsert_friction(friction_file, 's1', events)
        assert len(result) == 1

    def test_creates_nested_directories(self, tmp_path):
        friction_file = str(tmp_path / 'deep' / 'nested' / 'friction.json')
        events = [{'session_id': 's1', 'date': '2026-03-07', 'turn_index': 0,
                    'category': 'tool_error'}]
        result = upsert_friction(friction_file, 's1', events)
        assert len(result) == 1
        assert os.path.exists(friction_file)
