"""End-to-end smoke tests — run actual scripts via subprocess and verify DB state."""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import storage
from conftest import make_user_line, make_assistant_line, write_transcript, _ts

SRC_DIR = os.path.join(os.path.dirname(__file__), '..', 'src')
WRITE_TURNS = os.path.join(SRC_DIR, 'write-turns.py')
WRITE_AGENT = os.path.join(SRC_DIR, 'write-agent.py')


def _run_script(script, args):
    """Run a Python script as subprocess, return CompletedProcess."""
    return subprocess.run(
        [sys.executable, script] + args,
        capture_output=True, text=True,
    )


class TestWriteTurnsE2E:

    def test_full_pipeline(self, tmp_path):
        model = 'claude-opus-4-20250514'
        lines = [
            make_user_line('t0', _ts(0, 0)),
            make_assistant_line(_ts(0, 10), model, 1000, 500, cache_creation=200, cache_read=300),
            make_user_line('t1', _ts(1, 0)),
            make_assistant_line(_ts(1, 30), model, 2000, 1000, cache_creation=0, cache_read=500),
        ]
        transcript = write_transcript(lines, str(tmp_path / 'transcript.jsonl'))
        tracking_dir = str(tmp_path / 'tracking')
        os.makedirs(tracking_dir, exist_ok=True)
        storage.init_db(tracking_dir)

        result = _run_script(WRITE_TURNS, [transcript, tracking_dir, 'sess-e2e', 'test-proj'])
        assert result.returncode == 0, f"stderr: {result.stderr}"

        turns = storage.get_all_turns(tracking_dir)
        assert len(turns) == 2
        assert turns[0]['input_tokens'] == 1000
        assert turns[0]['estimated_cost_usd'] == 0.0567
        assert turns[1]['total_tokens'] == 3500

    def test_empty_transcript_exits_zero(self, tmp_path):
        transcript = write_transcript([], str(tmp_path / 'empty.jsonl'))
        tracking_dir = str(tmp_path / 'tracking')
        os.makedirs(tracking_dir, exist_ok=True)
        storage.init_db(tracking_dir)

        result = _run_script(WRITE_TURNS, [transcript, tracking_dir, 'sess-empty', 'proj'])
        assert result.returncode == 0

        turns = storage.get_all_turns(tracking_dir)
        assert len(turns) == 0

    def test_idempotent_upsert(self, tmp_path):
        model = 'claude-opus-4-20250514'
        lines = [
            make_user_line('t0', _ts(0, 0)),
            make_assistant_line(_ts(0, 10), model, 100, 50),
        ]
        transcript = write_transcript(lines, str(tmp_path / 'transcript.jsonl'))
        tracking_dir = str(tmp_path / 'tracking')
        os.makedirs(tracking_dir, exist_ok=True)
        storage.init_db(tracking_dir)

        _run_script(WRITE_TURNS, [transcript, tracking_dir, 'sess-idem', 'proj'])
        _run_script(WRITE_TURNS, [transcript, tracking_dir, 'sess-idem', 'proj'])

        turns = storage.get_all_turns(tracking_dir)
        assert len(turns) == 1


class TestWriteAgentE2E:

    def test_full_pipeline(self, tmp_path):
        model = 'claude-opus-4-20250514'
        lines = [
            make_user_line('a', _ts(0)),
            make_assistant_line(_ts(0, 5), model, 100, 50, cache_creation=10, cache_read=20),
            make_user_line('b', _ts(1)),
            make_assistant_line(_ts(1, 5), model, 200, 100, cache_creation=30, cache_read=40),
        ]
        transcript = write_transcript(lines, str(tmp_path / 'agent.jsonl'))
        tracking_dir = str(tmp_path / 'tracking')
        os.makedirs(tracking_dir, exist_ok=True)
        storage.init_db(tracking_dir)

        result = _run_script(WRITE_AGENT, [
            transcript, tracking_dir, 'sess-agent', 'agent-42', 'coder',
        ])
        assert result.returncode == 0, f"stderr: {result.stderr}"

        agents = storage.get_all_agents(tracking_dir)
        assert len(agents) == 1
        assert agents[0]['input_tokens'] == 300
        assert agents[0]['output_tokens'] == 150
        assert agents[0]['turns'] == 2
        assert agents[0]['agent_type'] == 'coder'


class TestFullPipeline:

    def test_turns_and_friction_from_same_transcript(self, tmp_path):
        """Run write-turns.py on a transcript that also has friction signals,
        then verify both turns in DB and friction data."""
        model = 'claude-opus-4-20250514'
        # A turn with a Bash tool error (friction signal)
        lines = [
            make_user_line('run tests', _ts(0, 0)),
            {
                'type': 'assistant',
                'timestamp': _ts(0, 5),
                'message': {
                    'role': 'assistant',
                    'model': model,
                    'content': [
                        {'type': 'tool_use', 'id': 'tu-1', 'name': 'Bash',
                         'input': {'command': 'npm test'}},
                    ],
                    'usage': {
                        'input_tokens': 500,
                        'output_tokens': 200,
                        'cache_creation_input_tokens': 0,
                        'cache_read_input_tokens': 0,
                    },
                },
            },
            {
                'type': 'assistant',
                'timestamp': _ts(0, 6),
                'message': {
                    'role': 'assistant',
                    'model': model,
                    'content': [
                        {'type': 'tool_result', 'tool_use_id': 'tu-1',
                         'content': 'Exit code 1\nTest failed', 'is_error': True},
                    ],
                },
            },
            make_user_line('fix it', _ts(1, 0)),
            make_assistant_line(_ts(1, 10), model, 300, 100),
        ]
        transcript = write_transcript(lines, str(tmp_path / 'mixed.jsonl'))
        tracking_dir = str(tmp_path / 'tracking')
        os.makedirs(tracking_dir, exist_ok=True)
        storage.init_db(tracking_dir)

        # Run write-turns
        result = _run_script(WRITE_TURNS, [transcript, tracking_dir, 'sess-mix', 'proj'])
        assert result.returncode == 0, f"stderr: {result.stderr}"

        turns = storage.get_all_turns(tracking_dir)
        assert len(turns) >= 1

        # Run parse_friction
        from parse_friction import parse_friction
        events = parse_friction(transcript, 'sess-mix', 'proj', 'cli')
        command_failed = [e for e in events if e['category'] == 'command_failed']
        assert len(command_failed) >= 1
