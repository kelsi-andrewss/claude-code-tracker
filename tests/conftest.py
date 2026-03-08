"""Shared fixtures and helpers for transcript-based tests."""
import json
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def _ts(minute, second=0):
    """Generate deterministic ISO timestamp."""
    return f"2026-03-07T10:{minute:02d}:{second:02d}.000Z"


def make_user_line(text, timestamp, is_sidechain=False):
    """Build a user-type JSONL object."""
    return {
        'type': 'user',
        'timestamp': timestamp,
        'isSidechain': is_sidechain,
        'message': {
            'role': 'user',
            'content': [{'type': 'text', 'text': text}],
        },
    }


def make_assistant_line(timestamp, model, input_tokens, output_tokens,
                        cache_creation=0, cache_read=0):
    """Build an assistant-type JSONL object with usage."""
    return {
        'type': 'assistant',
        'timestamp': timestamp,
        'message': {
            'role': 'assistant',
            'model': model,
            'content': [{'type': 'text', 'text': 'ok'}],
            'usage': {
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'cache_creation_input_tokens': cache_creation,
                'cache_read_input_tokens': cache_read,
            },
        },
    }


def write_transcript(lines, path):
    """Write JSONL lines to a file. Returns the path."""
    with open(path, 'w') as f:
        for line in lines:
            f.write(json.dumps(line) + '\n')
    return path


def make_skill_tool_use(skill_name, tool_id, timestamp, args=None):
    """Build a Skill tool_use content block inside an assistant message."""
    inp = {'skill': skill_name}
    if args is not None:
        inp['args'] = args
    return {
        'type': 'assistant',
        'timestamp': timestamp,
        'message': {
            'role': 'assistant',
            'content': [{
                'type': 'tool_use',
                'id': tool_id,
                'name': 'Skill',
                'input': inp,
            }],
        },
    }


def make_skill_tool_result(tool_id, timestamp, is_error=False, content=''):
    """Build a tool_result block for a Skill invocation."""
    return {
        'type': 'user',
        'timestamp': timestamp,
        'message': {
            'role': 'user',
            'content': [{
                'type': 'tool_result',
                'tool_use_id': tool_id,
                'is_error': is_error,
                'content': content,
            }],
        },
    }


@pytest.fixture
def simple_3turn_transcript(tmp_path):
    """3-turn opus transcript with pre-calculated expected values.

    Turn 0: input=1000, output=500, cache_create=200, cache_read=300, total=2000
            cost = 1000*15/1e6 + 200*18.75/1e6 + 300*1.50/1e6 + 500*75/1e6
                 = 0.015 + 0.00375 + 0.00045 + 0.0375 = 0.0567
            duration = 10s (ts 00:00 -> 00:10)

    Turn 1: input=2000, output=1000, cache_create=0, cache_read=500, total=3500
            cost = 2000*15/1e6 + 0 + 500*1.50/1e6 + 1000*75/1e6
                 = 0.03 + 0 + 0.00075 + 0.075 = 0.10575 (rounds to 0.1057 via banker's rounding)
            duration = 30s (ts 01:00 -> 01:30)

    Turn 2: input=500, output=200, cache_create=100, cache_read=0, total=800
            cost = 500*15/1e6 + 100*18.75/1e6 + 0 + 200*75/1e6
                 = 0.0075 + 0.001875 + 0 + 0.015 = 0.024375 -> rounds to 0.0244
            duration = 5s (ts 02:00 -> 02:05)
    """
    model = 'claude-opus-4-20250514'
    lines = [
        make_user_line('turn 0', _ts(0, 0)),
        make_assistant_line(_ts(0, 10), model, 1000, 500, cache_creation=200, cache_read=300),
        make_user_line('turn 1', _ts(1, 0)),
        make_assistant_line(_ts(1, 30), model, 2000, 1000, cache_creation=0, cache_read=500),
        make_user_line('turn 2', _ts(2, 0)),
        make_assistant_line(_ts(2, 5), model, 500, 200, cache_creation=100, cache_read=0),
    ]
    path = str(tmp_path / 'opus_3turn.jsonl')
    write_transcript(lines, path)
    return {
        'path': path,
        'model': model,
        'expected': [
            {'turn_index': 0, 'input_tokens': 1000, 'output_tokens': 500,
             'cache_creation_tokens': 200, 'cache_read_tokens': 300,
             'total_tokens': 2000, 'estimated_cost_usd': 0.0567,
             'duration_seconds': 10},
            {'turn_index': 1, 'input_tokens': 2000, 'output_tokens': 1000,
             'cache_creation_tokens': 0, 'cache_read_tokens': 500,
             'total_tokens': 3500, 'estimated_cost_usd': 0.1057,
             'duration_seconds': 30},
            {'turn_index': 2, 'input_tokens': 500, 'output_tokens': 200,
             'cache_creation_tokens': 100, 'cache_read_tokens': 0,
             'total_tokens': 800, 'estimated_cost_usd': 0.0244,
             'duration_seconds': 5},
        ],
    }


@pytest.fixture
def sonnet_transcript(tmp_path):
    """Single-turn non-opus transcript for pricing branch verification.

    Turn 0: input=1000, output=500, cache_create=200, cache_read=300, total=2000
            cost = 1000*3/1e6 + 200*3.75/1e6 + 300*0.30/1e6 + 500*15/1e6
                 = 0.003 + 0.00075 + 0.00009 + 0.0075 = 0.01134 -> rounds to 0.0113
    """
    model = 'claude-sonnet-4-20250514'
    lines = [
        make_user_line('hello', _ts(0, 0)),
        make_assistant_line(_ts(0, 5), model, 1000, 500, cache_creation=200, cache_read=300),
    ]
    path = str(tmp_path / 'sonnet_1turn.jsonl')
    write_transcript(lines, path)
    return {
        'path': path,
        'model': model,
        'expected_cost': 0.0113,
    }
