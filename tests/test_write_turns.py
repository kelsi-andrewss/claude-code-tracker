"""Tests for src/write-turns.py — turn parsing and entry building."""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# write-turns.py has a hyphen — import via importlib
import importlib
write_turns = importlib.import_module('write-turns')
parse_transcript = write_turns.parse_transcript
build_turn_entries = write_turns.build_turn_entries

from conftest import make_user_line, make_assistant_line, write_transcript, _ts


REQUIRED_FIELDS = [
    'date', 'project', 'session_id', 'turn_index', 'turn_timestamp',
    'input_tokens', 'cache_creation_tokens', 'cache_read_tokens',
    'output_tokens', 'total_tokens', 'estimated_cost_usd', 'model',
    'duration_seconds',
]


class TestParseTranscript:

    def test_parses_3_pairs(self, simple_3turn_transcript):
        msgs, usages, model = parse_transcript(simple_3turn_transcript['path'])
        # 3 user + 3 assistant = 6 messages
        assert len(msgs) == 6
        assert len(usages) == 3
        assert model == simple_3turn_transcript['model']

    def test_skips_sidechain_user_messages(self, tmp_path):
        lines = [
            make_user_line('real', _ts(0)),
            make_user_line('sidechain', _ts(1), is_sidechain=True),
            make_assistant_line(_ts(2), 'claude-opus-4-20250514', 100, 50),
        ]
        path = write_transcript(lines, str(tmp_path / 'sc.jsonl'))
        msgs, usages, model = parse_transcript(path)
        user_msgs = [m for m in msgs if m[0] == 'user']
        assert len(user_msgs) == 1

    def test_extracts_model_from_last_assistant(self, tmp_path):
        lines = [
            make_user_line('hi', _ts(0)),
            make_assistant_line(_ts(1), 'claude-sonnet-4-20250514', 100, 50),
            make_user_line('hi again', _ts(2)),
            make_assistant_line(_ts(3), 'claude-opus-4-20250514', 100, 50),
        ]
        path = write_transcript(lines, str(tmp_path / 'model.jsonl'))
        _, _, model = parse_transcript(path)
        assert model == 'claude-opus-4-20250514'

    def test_handles_malformed_json(self, tmp_path):
        path = str(tmp_path / 'bad.jsonl')
        with open(path, 'w') as f:
            f.write('not json at all\n')
            f.write(json.dumps(make_user_line('real', _ts(0))) + '\n')
            f.write('{bad json\n')
            f.write(json.dumps(make_assistant_line(_ts(1), 'claude-opus-4-20250514', 100, 50)) + '\n')
        msgs, usages, model = parse_transcript(path)
        assert len(msgs) == 2
        assert len(usages) == 1

    def test_assistant_without_usage_not_in_usages(self, tmp_path):
        line_no_usage = {
            'type': 'assistant',
            'timestamp': _ts(1),
            'message': {
                'role': 'assistant',
                'model': 'claude-opus-4-20250514',
                'content': [{'type': 'text', 'text': 'ok'}],
            },
        }
        lines = [
            make_user_line('hi', _ts(0)),
            line_no_usage,
        ]
        path = write_transcript(lines, str(tmp_path / 'no_usage.jsonl'))
        msgs, usages, _ = parse_transcript(path)
        assert len(usages) == 0


class TestBuildTurnEntries:

    def test_3_turns_correct_values(self, simple_3turn_transcript):
        data = simple_3turn_transcript
        msgs, usages, model = parse_transcript(data['path'])
        entries = build_turn_entries(msgs, usages, model, 'sess-1', 'test-proj')

        assert len(entries) == 3
        for i, entry in enumerate(entries):
            exp = data['expected'][i]
            assert entry['turn_index'] == exp['turn_index']
            assert entry['input_tokens'] == exp['input_tokens']
            assert entry['output_tokens'] == exp['output_tokens']
            assert entry['cache_creation_tokens'] == exp['cache_creation_tokens']
            assert entry['cache_read_tokens'] == exp['cache_read_tokens']
            assert entry['total_tokens'] == exp['total_tokens']
            assert entry['estimated_cost_usd'] == exp['estimated_cost_usd']
            assert entry['duration_seconds'] == exp['duration_seconds']

    def test_zero_token_turn_excluded_but_index_increments(self, tmp_path):
        lines = [
            make_user_line('t0', _ts(0)),
            make_assistant_line(_ts(0, 5), 'claude-opus-4-20250514', 100, 50),
            make_user_line('t1', _ts(1)),
            # assistant with zero tokens
            make_assistant_line(_ts(1, 5), 'claude-opus-4-20250514', 0, 0),
            make_user_line('t2', _ts(2)),
            make_assistant_line(_ts(2, 5), 'claude-opus-4-20250514', 200, 100),
        ]
        path = write_transcript(lines, str(tmp_path / 'zero.jsonl'))
        msgs, usages, model = parse_transcript(path)
        entries = build_turn_entries(msgs, usages, model, 's1', 'p1')
        assert len(entries) == 2
        # turn_index 0 is present, turn_index 1 skipped (zero tokens), turn_index 2 present
        assert entries[0]['turn_index'] == 0
        assert entries[1]['turn_index'] == 2

    def test_duration_is_asst_minus_user_clamped(self, tmp_path):
        lines = [
            make_user_line('hi', _ts(0, 0)),
            make_assistant_line(_ts(0, 7), 'claude-opus-4-20250514', 100, 50),
        ]
        path = write_transcript(lines, str(tmp_path / 'dur.jsonl'))
        msgs, usages, model = parse_transcript(path)
        entries = build_turn_entries(msgs, usages, model, 's1', 'p1')
        assert entries[0]['duration_seconds'] == 7

    def test_unpaired_trailing_user_produces_no_turn(self, tmp_path):
        lines = [
            make_user_line('t0', _ts(0)),
            make_assistant_line(_ts(0, 5), 'claude-opus-4-20250514', 100, 50),
            make_user_line('trailing', _ts(1)),
        ]
        path = write_transcript(lines, str(tmp_path / 'trail.jsonl'))
        msgs, usages, model = parse_transcript(path)
        entries = build_turn_entries(msgs, usages, model, 's1', 'p1')
        assert len(entries) == 1

    def test_all_required_fields_present(self, simple_3turn_transcript):
        msgs, usages, model = parse_transcript(simple_3turn_transcript['path'])
        entries = build_turn_entries(msgs, usages, model, 's1', 'p1')
        for entry in entries:
            for field in REQUIRED_FIELDS:
                assert field in entry, f"Missing field: {field}"

    def test_cost_rounded_to_4_decimals(self, simple_3turn_transcript):
        msgs, usages, model = parse_transcript(simple_3turn_transcript['path'])
        entries = build_turn_entries(msgs, usages, model, 's1', 'p1')
        for entry in entries:
            cost_str = str(entry['estimated_cost_usd'])
            if '.' in cost_str:
                decimals = len(cost_str.split('.')[1])
                assert decimals <= 4

    def test_date_format_yyyy_mm_dd(self, simple_3turn_transcript):
        msgs, usages, model = parse_transcript(simple_3turn_transcript['path'])
        entries = build_turn_entries(msgs, usages, model, 's1', 'p1')
        import re
        for entry in entries:
            assert re.match(r'^\d{4}-\d{2}-\d{2}$', entry['date'])

    def test_turn_timestamp_iso_z_format(self, simple_3turn_transcript):
        msgs, usages, model = parse_transcript(simple_3turn_transcript['path'])
        entries = build_turn_entries(msgs, usages, model, 's1', 'p1')
        import re
        for entry in entries:
            assert re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$',
                            entry['turn_timestamp'])

    def test_sonnet_pricing_branch(self, sonnet_transcript):
        msgs, usages, model = parse_transcript(sonnet_transcript['path'])
        entries = build_turn_entries(msgs, usages, model, 's1', 'p1')
        assert len(entries) == 1
        assert entries[0]['estimated_cost_usd'] == sonnet_transcript['expected_cost']
