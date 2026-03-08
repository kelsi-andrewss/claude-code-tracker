"""Tests for src/parse_skills.py — skill invocation parser."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import parse_skills
import storage

from conftest import (
    _ts, make_user_line, make_assistant_line, write_transcript,
    make_skill_tool_use, make_skill_tool_result,
)


class TestParseSkills:

    def test_single_skill_happy_path(self, tmp_path):
        lines = [
            make_user_line('do it', _ts(0, 0)),
            make_skill_tool_use('commit', 'tu1', _ts(0, 5)),
            make_skill_tool_result('tu1', _ts(0, 15)),
            make_assistant_line(_ts(0, 20), 'claude-opus-4-20250514', 100, 50),
        ]
        path = write_transcript(lines, str(tmp_path / 't.jsonl'))
        result = parse_skills.parse_skills(path, 'sess1', 'proj')

        assert len(result) == 1
        assert result[0]['skill_name'] == 'commit'
        assert result[0]['success'] == 1
        assert result[0]['duration_seconds'] == 10
        assert result[0]['session_id'] == 'sess1'
        assert result[0]['project'] == 'proj'
        assert result[0]['date'] == '2026-03-07'

    def test_multiple_skills(self, tmp_path):
        lines = [
            make_user_line('go', _ts(0, 0)),
            make_skill_tool_use('commit', 'tu1', _ts(0, 5)),
            make_skill_tool_result('tu1', _ts(0, 10)),
            make_skill_tool_use('audit', 'tu2', _ts(0, 15)),
            make_skill_tool_result('tu2', _ts(0, 25)),
            make_assistant_line(_ts(0, 30), 'claude-opus-4-20250514', 100, 50),
        ]
        path = write_transcript(lines, str(tmp_path / 't.jsonl'))
        result = parse_skills.parse_skills(path, 'sess1', 'proj')

        assert len(result) == 2
        assert result[0]['skill_name'] == 'commit'
        assert result[1]['skill_name'] == 'audit'

    def test_skill_with_error(self, tmp_path):
        lines = [
            make_user_line('go', _ts(0, 0)),
            make_skill_tool_use('ship', 'tu1', _ts(0, 5)),
            make_skill_tool_result('tu1', _ts(0, 10), is_error=True, content='Epic not found'),
            make_assistant_line(_ts(0, 15), 'claude-opus-4-20250514', 100, 50),
        ]
        path = write_transcript(lines, str(tmp_path / 't.jsonl'))
        result = parse_skills.parse_skills(path, 'sess1', 'proj')

        assert len(result) == 1
        assert result[0]['success'] == 0
        assert result[0]['error_message'] == 'Epic not found'

    def test_duration_from_timestamp_delta(self, tmp_path):
        lines = [
            make_user_line('go', _ts(0, 0)),
            make_skill_tool_use('critique', 'tu1', _ts(1, 0)),
            make_skill_tool_result('tu1', _ts(2, 30)),
            make_assistant_line(_ts(2, 35), 'claude-opus-4-20250514', 100, 50),
        ]
        path = write_transcript(lines, str(tmp_path / 't.jsonl'))
        result = parse_skills.parse_skills(path, 'sess1', 'proj')

        assert result[0]['duration_seconds'] == 90

    def test_unmatched_tool_use(self, tmp_path):
        """tool_use without a matching tool_result still gets recorded."""
        lines = [
            make_user_line('go', _ts(0, 0)),
            make_skill_tool_use('commit', 'tu1', _ts(0, 5)),
            make_assistant_line(_ts(0, 10), 'claude-opus-4-20250514', 100, 50),
        ]
        path = write_transcript(lines, str(tmp_path / 't.jsonl'))
        result = parse_skills.parse_skills(path, 'sess1', 'proj')

        assert len(result) == 1
        assert result[0]['duration_seconds'] == 0
        assert result[0]['success'] == 1

    def test_non_skill_tools_ignored(self, tmp_path):
        """tool_use blocks for non-Skill tools should be ignored."""
        lines = [
            make_user_line('go', _ts(0, 0)),
            {
                'type': 'assistant',
                'timestamp': _ts(0, 5),
                'message': {
                    'role': 'assistant',
                    'content': [{
                        'type': 'tool_use',
                        'id': 'tu1',
                        'name': 'Bash',
                        'input': {'command': 'ls'},
                    }],
                },
            },
            make_assistant_line(_ts(0, 10), 'claude-opus-4-20250514', 100, 50),
        ]
        path = write_transcript(lines, str(tmp_path / 't.jsonl'))
        result = parse_skills.parse_skills(path, 'sess1', 'proj')

        assert len(result) == 0

    def test_idempotent_via_replace(self, tmp_path):
        """replace_session_skills produces same count on re-run."""
        tracking_dir = str(tmp_path / 'tracking')
        storage.init_db(tracking_dir)

        entries = [{
            'session_id': 'sess1', 'date': '2026-03-07', 'project': 'proj',
            'skill_name': 'commit', 'tool_use_id': 'tu1',
            'timestamp': '2026-03-07T10:00:05.000Z',
            'duration_seconds': 10, 'success': 1,
        }]
        storage.replace_session_skills(tracking_dir, 'sess1', entries)
        storage.replace_session_skills(tracking_dir, 'sess1', entries)

        all_skills = storage.get_all_skills(tracking_dir)
        assert len(all_skills) == 1

    def test_empty_transcript(self, tmp_path):
        path = str(tmp_path / 't.jsonl')
        with open(path, 'w') as f:
            pass
        result = parse_skills.parse_skills(path, 'sess1', 'proj')
        assert result == []

    def test_args_preserved(self, tmp_path):
        lines = [
            make_user_line('go', _ts(0, 0)),
            make_skill_tool_use('ship', 'tu1', _ts(0, 5), args='epic-42'),
            make_skill_tool_result('tu1', _ts(0, 15)),
            make_assistant_line(_ts(0, 20), 'claude-opus-4-20250514', 100, 50),
        ]
        path = write_transcript(lines, str(tmp_path / 't.jsonl'))
        result = parse_skills.parse_skills(path, 'sess1', 'proj')

        assert result[0]['args'] == 'epic-42'
