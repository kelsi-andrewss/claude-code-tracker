"""Tests for src/write-agent.py — agent usage aggregation."""
import json
import re
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import importlib
write_agent = importlib.import_module('write-agent')
aggregate_agent_usage = write_agent.aggregate_agent_usage
build_agent_entry = write_agent.build_agent_entry

from conftest import make_user_line, make_assistant_line, write_transcript, _ts


REQUIRED_AGENT_FIELDS = [
    'timestamp', 'session_id', 'agent_id', 'agent_type',
    'input_tokens', 'output_tokens', 'cache_creation_tokens',
    'cache_read_tokens', 'total_tokens', 'turns',
    'estimated_cost_usd', 'model',
]


class TestAggregateAgentUsage:

    def test_sums_across_3_assistant_messages(self, tmp_path):
        model = 'claude-opus-4-20250514'
        lines = [
            make_user_line('t0', _ts(0)),
            make_assistant_line(_ts(0, 5), model, 100, 50, cache_creation=10, cache_read=20),
            make_user_line('t1', _ts(1)),
            make_assistant_line(_ts(1, 5), model, 200, 100, cache_creation=30, cache_read=40),
            make_user_line('t2', _ts(2)),
            make_assistant_line(_ts(2, 5), model, 300, 150, cache_creation=50, cache_read=60),
        ]
        path = write_transcript(lines, str(tmp_path / 'agent.jsonl'))
        result = aggregate_agent_usage(path)

        assert result['input_tokens'] == 600
        assert result['output_tokens'] == 300
        assert result['cache_creation_tokens'] == 90
        assert result['cache_read_tokens'] == 120
        assert result['total_tokens'] == 1110
        assert result['turns'] == 3

    def test_returns_none_when_total_zero(self, tmp_path):
        lines = [
            make_user_line('hi', _ts(0)),
            # assistant with zero tokens
            make_assistant_line(_ts(0, 5), 'claude-opus-4-20250514', 0, 0),
        ]
        path = write_transcript(lines, str(tmp_path / 'zero.jsonl'))
        assert aggregate_agent_usage(path) is None

    def test_counts_turns_as_assistant_msgs_with_usage(self, tmp_path):
        model = 'claude-opus-4-20250514'
        # Two assistant messages with usage
        lines = [
            make_user_line('a', _ts(0)),
            make_assistant_line(_ts(0, 5), model, 100, 50),
            make_user_line('b', _ts(1)),
            make_assistant_line(_ts(1, 5), model, 200, 100),
        ]
        path = write_transcript(lines, str(tmp_path / 'turns.jsonl'))
        result = aggregate_agent_usage(path)
        assert result['turns'] == 2

    def test_captures_first_timestamp_and_last_model(self, tmp_path):
        lines = [
            make_user_line('a', _ts(0)),
            make_assistant_line(_ts(0, 5), 'claude-sonnet-4-20250514', 100, 50),
            make_user_line('b', _ts(1)),
            make_assistant_line(_ts(1, 5), 'claude-opus-4-20250514', 200, 100),
        ]
        path = write_transcript(lines, str(tmp_path / 'models.jsonl'))
        result = aggregate_agent_usage(path)
        assert result['first_timestamp'] == _ts(0)
        assert result['model'] == 'claude-opus-4-20250514'

    def test_malformed_json_lines_skipped(self, tmp_path):
        """Bad JSON lines are skipped; valid assistant lines still summed."""
        model = 'claude-opus-4-20250514'
        path = str(tmp_path / 'mixed.jsonl')
        with open(path, 'w') as f:
            f.write('not json at all\n')
            f.write(json.dumps(make_assistant_line(_ts(0, 5), model, 100, 50)) + '\n')
            f.write('{broken json\n')
            f.write(json.dumps(make_assistant_line(_ts(1, 5), model, 200, 100)) + '\n')
        result = aggregate_agent_usage(path)
        assert result['input_tokens'] == 300
        assert result['output_tokens'] == 150
        assert result['turns'] == 2

    def test_missing_file_raises(self):
        """aggregate_agent_usage on nonexistent file raises FileNotFoundError."""
        import pytest
        with pytest.raises(FileNotFoundError):
            aggregate_agent_usage('/nonexistent/path/transcript.jsonl')

    def test_handles_non_dict_message_field(self, tmp_path):
        lines = [
            {'type': 'user', 'timestamp': _ts(0), 'message': 'not a dict'},
            make_assistant_line(_ts(0, 5), 'claude-opus-4-20250514', 100, 50),
        ]
        path = write_transcript(lines, str(tmp_path / 'nondict.jsonl'))
        result = aggregate_agent_usage(path)
        assert result['input_tokens'] == 100
        assert result['output_tokens'] == 50


class TestBuildAgentEntry:

    def test_all_required_fields_present(self):
        usage_data = {
            'input_tokens': 100, 'output_tokens': 50,
            'cache_creation_tokens': 10, 'cache_read_tokens': 20,
            'total_tokens': 180, 'turns': 1,
            'model': 'claude-opus-4-20250514',
            'first_timestamp': '2026-03-07T10:00:00.000Z',
        }
        entry = build_agent_entry(usage_data, 'sess-1', 'agent-1', 'coder')
        for field in REQUIRED_AGENT_FIELDS:
            assert field in entry, f"Missing field: {field}"

    def test_opus_cost_calculation(self):
        usage_data = {
            'input_tokens': 1000, 'output_tokens': 500,
            'cache_creation_tokens': 200, 'cache_read_tokens': 300,
            'total_tokens': 2000, 'turns': 1,
            'model': 'claude-opus-4-20250514',
            'first_timestamp': '2026-03-07T10:00:00.000Z',
        }
        entry = build_agent_entry(usage_data, 's1', 'a1', 'coder')
        assert entry['estimated_cost_usd'] == 0.0567

    def test_non_opus_cost_calculation(self):
        usage_data = {
            'input_tokens': 1000, 'output_tokens': 500,
            'cache_creation_tokens': 200, 'cache_read_tokens': 300,
            'total_tokens': 2000, 'turns': 1,
            'model': 'claude-sonnet-4-20250514',
            'first_timestamp': '2026-03-07T10:00:00.000Z',
        }
        entry = build_agent_entry(usage_data, 's1', 'a1', 'coder')
        assert entry['estimated_cost_usd'] == 0.0113

    def test_timestamp_normalized_to_iso_z(self):
        usage_data = {
            'input_tokens': 100, 'output_tokens': 50,
            'cache_creation_tokens': 0, 'cache_read_tokens': 0,
            'total_tokens': 150, 'turns': 1,
            'model': 'claude-opus-4-20250514',
            'first_timestamp': '2026-03-07T10:00:00.000Z',
        }
        entry = build_agent_entry(usage_data, 's1', 'a1', 'coder')
        assert entry['timestamp'] == '2026-03-07T10:00:00Z'

    def test_none_timestamp_uses_fallback(self):
        """None first_timestamp triggers except branch, falls back to utcnow()."""
        usage_data = {
            'input_tokens': 100, 'output_tokens': 50,
            'cache_creation_tokens': 0, 'cache_read_tokens': 0,
            'total_tokens': 150, 'turns': 1,
            'model': 'claude-opus-4-20250514',
            'first_timestamp': None,
        }
        entry = build_agent_entry(usage_data, 's1', 'a1', 'coder')
        # Fallback produces YYYY-MM-DDTHH:MM:SSZ format
        assert re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$', entry['timestamp'])
