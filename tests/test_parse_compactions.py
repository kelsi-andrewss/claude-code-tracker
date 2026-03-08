"""Tests for parse_compactions.py — context compaction event parsing from JSONL transcripts."""
import sys, os, json, tempfile, pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from parse_compactions import parse_compactions
import storage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(n):
    """Generate deterministic ISO timestamps for test data."""
    return f"2026-03-07T10:{n:02d}:00.000Z"


def _user_msg(text, ts):
    return {
        'type': 'user',
        'timestamp': ts,
        'userType': 'human',
        'isSidechain': False,
        'message': {
            'role': 'user',
            'content': [{'type': 'text', 'text': text}],
        },
    }


def _assistant_msg(ts, model='claude-sonnet-4-20250514'):
    return {
        'type': 'assistant',
        'timestamp': ts,
        'message': {
            'role': 'assistant',
            'model': model,
            'content': [{'type': 'text', 'text': 'response'}],
            'usage': {'input_tokens': 1000, 'output_tokens': 200},
        },
    }


def _compact_event(ts, trigger='auto', pre_tokens=168000):
    return {
        'type': 'system',
        'subtype': 'compact_boundary',
        'timestamp': ts,
        'compactMetadata': {
            'trigger': trigger,
            'preTokens': pre_tokens,
        },
    }


def _write_jsonl(lines, path):
    with open(path, 'w') as f:
        for line in lines:
            f.write(json.dumps(line) + '\n')


def _build_transcript(lines):
    fd, path = tempfile.mkstemp(suffix='.jsonl')
    os.close(fd)
    _write_jsonl(lines, path)
    return path


# ---------------------------------------------------------------------------
# Tests: parse_compactions
# ---------------------------------------------------------------------------

class TestParseCompactions:

    def test_empty_transcript(self):
        path = _build_transcript([])
        try:
            events = parse_compactions(path, 'sess-1', 'test-proj')
            assert events == []
        finally:
            os.unlink(path)

    def test_no_compaction_events(self):
        lines = [
            _user_msg("hello", _ts(0)),
            _assistant_msg(_ts(1)),
            _user_msg("world", _ts(2)),
            _assistant_msg(_ts(3)),
        ]
        path = _build_transcript(lines)
        try:
            events = parse_compactions(path, 'sess-1', 'test-proj')
            assert events == []
        finally:
            os.unlink(path)

    def test_single_auto_compaction(self):
        lines = [
            _user_msg("hello", _ts(0)),
            _assistant_msg(_ts(1)),
            _compact_event(_ts(2), trigger='auto', pre_tokens=168000),
            _user_msg("world", _ts(3)),
            _assistant_msg(_ts(4)),
        ]
        path = _build_transcript(lines)
        try:
            events = parse_compactions(path, 'sess-1', 'test-proj')
            assert len(events) == 1
            assert events[0]['trigger'] == 'auto'
            assert events[0]['pre_tokens'] == 168000
            assert events[0]['session_id'] == 'sess-1'
            assert events[0]['project'] == 'test-proj'
            assert events[0]['date'] == '2026-03-07'
        finally:
            os.unlink(path)

    def test_manual_compaction(self):
        lines = [
            _user_msg("hello", _ts(0)),
            _assistant_msg(_ts(1)),
            _compact_event(_ts(2), trigger='manual', pre_tokens=120000),
        ]
        path = _build_transcript(lines)
        try:
            events = parse_compactions(path, 'sess-1', 'test-proj')
            assert len(events) == 1
            assert events[0]['trigger'] == 'manual'
            assert events[0]['pre_tokens'] == 120000
        finally:
            os.unlink(path)

    def test_multiple_compactions(self):
        lines = [
            _user_msg("a", _ts(0)),
            _assistant_msg(_ts(1)),
            _compact_event(_ts(2), trigger='auto', pre_tokens=168000),
            _user_msg("b", _ts(3)),
            _assistant_msg(_ts(4)),
            _user_msg("c", _ts(5)),
            _assistant_msg(_ts(6)),
            _compact_event(_ts(7), trigger='manual', pre_tokens=150000),
            _user_msg("d", _ts(8)),
            _assistant_msg(_ts(9)),
        ]
        path = _build_transcript(lines)
        try:
            events = parse_compactions(path, 'sess-1', 'test-proj')
            assert len(events) == 2
            assert events[0]['trigger'] == 'auto'
            assert events[1]['trigger'] == 'manual'
        finally:
            os.unlink(path)

    def test_turn_index_derived(self):
        lines = [
            _user_msg("turn 0", _ts(0)),
            _assistant_msg(_ts(1)),
            _user_msg("turn 1", _ts(2)),
            _assistant_msg(_ts(3)),
            _compact_event(_ts(4), trigger='auto', pre_tokens=168000),
            _user_msg("turn 2", _ts(5)),
            _assistant_msg(_ts(6)),
        ]
        path = _build_transcript(lines)
        try:
            events = parse_compactions(path, 'sess-1', 'test-proj')
            assert len(events) == 1
            # Compaction happens after turn 1, so turn_index should be 1
            assert events[0]['turn_index'] == 1
        finally:
            os.unlink(path)

    def test_timestamp_preserved(self):
        lines = [
            _user_msg("hello", _ts(0)),
            _assistant_msg(_ts(1)),
            _compact_event(_ts(5), trigger='auto', pre_tokens=168000),
        ]
        path = _build_transcript(lines)
        try:
            events = parse_compactions(path, 'sess-1', 'test-proj')
            assert events[0]['timestamp'] == _ts(5)
        finally:
            os.unlink(path)

    def test_storage_round_trip(self, tmp_path):
        tracking_dir = str(tmp_path / 'tracking')
        os.makedirs(tracking_dir)
        storage.init_db(tracking_dir)

        entries = [{
            'session_id': 'sess-1',
            'date': '2026-03-07',
            'project': 'test-proj',
            'timestamp': _ts(5),
            'trigger': 'auto',
            'pre_tokens': 168000,
            'turn_index': 2,
        }]
        storage.replace_session_compactions(tracking_dir, 'sess-1', entries)
        result = storage.get_all_compactions(tracking_dir)
        assert len(result) == 1
        assert result[0]['trigger'] == 'auto'
        assert result[0]['pre_tokens'] == 168000

    def test_backfill_dedup(self, tmp_path):
        tracking_dir = str(tmp_path / 'tracking')
        os.makedirs(tracking_dir)
        storage.init_db(tracking_dir)

        entries = [{
            'session_id': 'sess-1',
            'date': '2026-03-07',
            'project': 'test-proj',
            'timestamp': _ts(5),
            'trigger': 'auto',
            'pre_tokens': 168000,
            'turn_index': 2,
        }]
        # Insert twice — replace_session should deduplicate
        storage.replace_session_compactions(tracking_dir, 'sess-1', entries)
        storage.replace_session_compactions(tracking_dir, 'sess-1', entries)
        result = storage.get_all_compactions(tracking_dir)
        assert len(result) == 1

    def test_missing_compact_metadata(self):
        """A compact_boundary without compactMetadata should use defaults."""
        lines = [
            _user_msg("hello", _ts(0)),
            _assistant_msg(_ts(1)),
            {'type': 'system', 'subtype': 'compact_boundary', 'timestamp': _ts(2)},
        ]
        path = _build_transcript(lines)
        try:
            events = parse_compactions(path, 'sess-1', 'test-proj')
            assert len(events) == 1
            assert events[0]['trigger'] == 'auto'
            assert events[0]['pre_tokens'] == 0
        finally:
            os.unlink(path)
