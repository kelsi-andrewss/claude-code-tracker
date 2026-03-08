"""Tests for src/backfill.py — parse_turns, compute_turns, and E2E backfill."""
import json
import os
import subprocess
import sys
import unittest.mock as mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import storage
from conftest import make_user_line, make_assistant_line, write_transcript, _ts

SRC_DIR = os.path.join(os.path.dirname(__file__), '..', 'src')
BACKFILL = os.path.join(SRC_DIR, 'backfill.py')


def _load_backfill_functions():
    """Extract parse_turns and compute_turns from backfill.py without running module-level code.

    backfill.py has module-level code that reads sys.argv[1], accesses the filesystem,
    and calls sys.exit(0). The functions we need (parse_turns, compute_turns) are defined
    AFTER the sys.exit, so we can't import the module normally. Instead, we compile
    the source and exec only the function definitions with the required dependencies.
    """
    import types

    backfill_path = os.path.join(SRC_DIR, 'backfill.py')
    with open(backfill_path) as f:
        source = f.read()

    # Parse the AST to extract only import statements and function definitions
    import ast
    tree = ast.parse(source)

    # Build a module with only the function defs and their needed imports
    func_source_lines = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef) and node.name in ('parse_turns', 'compute_turns'):
            func_source_lines.append(ast.get_source_segment(source, node))

    # Create a namespace with all the dependencies the functions need
    namespace = {
        'json': json,
        'os': os,
        'sys': sys,
        'datetime': __import__('datetime').datetime,
        'compute_cost': __import__('cost').compute_cost,
    }

    for func_source in func_source_lines:
        exec(compile(func_source, backfill_path, 'exec'), namespace)

    return namespace['parse_turns'], namespace['compute_turns']


parse_turns, compute_turns = _load_backfill_functions()


class TestParseTurns:

    def test_parses_3_turns(self, tmp_path):
        """3-turn JSONL transcript parsed correctly."""
        model = 'claude-opus-4-20250514'
        lines = [
            make_user_line('t0', _ts(0, 0)),
            make_assistant_line(_ts(0, 10), model, 1000, 500, cache_creation=200, cache_read=300),
            make_user_line('t1', _ts(1, 0)),
            make_assistant_line(_ts(1, 30), model, 2000, 1000, cache_creation=0, cache_read=500),
            make_user_line('t2', _ts(2, 0)),
            make_assistant_line(_ts(2, 5), model, 500, 200, cache_creation=100, cache_read=0),
        ]
        path = write_transcript(lines, str(tmp_path / 'three.jsonl'))
        result = parse_turns(path)

        assert len(result) == 4  # (msgs, first_ts, model, usages)
        msgs, first_ts, m, usages = result
        assert len(msgs) == 6  # 3 user + 3 assistant
        assert len(usages) == 3
        assert m == model
        assert first_ts == _ts(0, 0)

    def test_returns_empty_on_missing_file(self):
        """Nonexistent path triggers the outer except → returns 3 values (not 4).

        This is a real asymmetry in backfill.py: happy path returns 4 values,
        error path returns 3. The caller at line 167 checks len(result)==4 and
        skips results that don't match, so this asymmetry is handled.
        """
        result = parse_turns('/nonexistent/path/transcript.jsonl')
        # Error path returns ([], None, "unknown") — 3 values
        assert len(result) == 3
        assert result[0] == []
        assert result[1] is None
        assert result[2] == "unknown"

    def test_malformed_json_skipped(self, tmp_path):
        """Bad JSON lines skipped, valid lines still parsed."""
        model = 'claude-opus-4-20250514'
        path = str(tmp_path / 'bad.jsonl')
        with open(path, 'w') as f:
            f.write('not valid json\n')
            f.write(json.dumps(make_user_line('t0', _ts(0, 0))) + '\n')
            f.write('{broken\n')
            f.write(json.dumps(make_assistant_line(_ts(0, 5), model, 100, 50)) + '\n')
        msgs, first_ts, m, usages = parse_turns(path)
        assert len(msgs) == 2
        assert len(usages) == 1


class TestComputeTurns:

    def test_3_turns_correct_values(self, tmp_path):
        """Same fixture as conftest simple_3turn_transcript — verify token counts, costs, durations."""
        model = 'claude-opus-4-20250514'
        lines = [
            make_user_line('t0', _ts(0, 0)),
            make_assistant_line(_ts(0, 10), model, 1000, 500, cache_creation=200, cache_read=300),
            make_user_line('t1', _ts(1, 0)),
            make_assistant_line(_ts(1, 30), model, 2000, 1000, cache_creation=0, cache_read=500),
            make_user_line('t2', _ts(2, 0)),
            make_assistant_line(_ts(2, 5), model, 500, 200, cache_creation=100, cache_read=0),
        ]
        path = write_transcript(lines, str(tmp_path / 'three.jsonl'))
        msgs, first_ts, m, usages = parse_turns(path)
        entries = compute_turns(msgs, usages, first_ts, m, 'sess-ct', 'proj')

        assert len(entries) == 3
        expected = [
            {'turn_index': 0, 'input_tokens': 1000, 'output_tokens': 500,
             'cache_creation_tokens': 200, 'cache_read_tokens': 300,
             'total_tokens': 2000, 'estimated_cost_usd': 0.0567, 'duration_seconds': 10},
            {'turn_index': 1, 'input_tokens': 2000, 'output_tokens': 1000,
             'cache_creation_tokens': 0, 'cache_read_tokens': 500,
             'total_tokens': 3500, 'estimated_cost_usd': 0.1057, 'duration_seconds': 30},
            {'turn_index': 2, 'input_tokens': 500, 'output_tokens': 200,
             'cache_creation_tokens': 100, 'cache_read_tokens': 0,
             'total_tokens': 800, 'estimated_cost_usd': 0.0244, 'duration_seconds': 5},
        ]
        for i, entry in enumerate(entries):
            exp = expected[i]
            for key in exp:
                assert entry[key] == exp[key], f"turn {i} key {key}: {entry[key]} != {exp[key]}"

    def test_skip_condition(self, tmp_path):
        """Pre-populated DB with turns for a session → count_turns_for_session >= expected means skip."""
        tracking_dir = str(tmp_path / 'tracking')
        os.makedirs(tracking_dir, exist_ok=True)
        storage.init_db(tracking_dir)

        # Insert 2 turns for session 'sess-skip'
        entries = [
            {'session_id': 'sess-skip', 'turn_index': 0, 'date': '2026-03-07',
             'project': 'proj', 'input_tokens': 100, 'output_tokens': 50,
             'total_tokens': 150},
            {'session_id': 'sess-skip', 'turn_index': 1, 'date': '2026-03-07',
             'project': 'proj', 'input_tokens': 200, 'output_tokens': 100,
             'total_tokens': 300},
        ]
        storage.upsert_turns(tracking_dir, entries)

        existing_count = storage.count_turns_for_session(tracking_dir, 'sess-skip')
        expected_count = 2  # same as what we'd compute from transcript

        # The skip condition from backfill.py line 180
        assert existing_count >= expected_count

    def test_replace_semantics(self, tmp_path):
        """replace_session_turns twice with different data → DB reflects latest."""
        tracking_dir = str(tmp_path / 'tracking')
        os.makedirs(tracking_dir, exist_ok=True)
        storage.init_db(tracking_dir)

        first_entries = [
            {'session_id': 'sess-rep', 'turn_index': 0, 'date': '2026-03-07',
             'project': 'proj', 'input_tokens': 100, 'output_tokens': 50,
             'total_tokens': 150},
        ]
        storage.replace_session_turns(tracking_dir, 'sess-rep', first_entries)

        second_entries = [
            {'session_id': 'sess-rep', 'turn_index': 0, 'date': '2026-03-07',
             'project': 'proj', 'input_tokens': 999, 'output_tokens': 888,
             'total_tokens': 1887},
            {'session_id': 'sess-rep', 'turn_index': 1, 'date': '2026-03-07',
             'project': 'proj', 'input_tokens': 111, 'output_tokens': 222,
             'total_tokens': 333},
        ]
        storage.replace_session_turns(tracking_dir, 'sess-rep', second_entries)

        turns = storage.get_session_turns(tracking_dir, 'sess-rep')
        assert len(turns) == 2
        assert turns[0]['input_tokens'] == 999
        assert turns[1]['input_tokens'] == 111


class TestBackfillE2E:

    def _make_transcript(self, path, model, turns):
        """Helper: write a JSONL transcript with given turns.

        turns: list of (minute, second_user, second_asst, inp, out) tuples
        """
        lines = []
        for minute, sec_u, sec_a, inp, out in turns:
            lines.append(make_user_line(f'turn-{minute}', _ts(minute, sec_u)))
            lines.append(make_assistant_line(_ts(minute, sec_a), model, inp, out))
        write_transcript(lines, path)

    def test_full_backfill_writes_to_db(self, tmp_path):
        """Create fake dir structure with 2 JSONL files, run backfill → DB has turns from both."""
        project_root = str(tmp_path / 'project')
        tracking_dir = os.path.join(project_root, '.claude', 'tracking')
        os.makedirs(tracking_dir, exist_ok=True)
        storage.init_db(tracking_dir)

        # Build transcripts dir based on slugify_path logic
        from platform_utils import slugify_path, get_transcripts_dir
        slug = slugify_path(project_root)
        transcripts_dir = os.path.join(get_transcripts_dir(), slug)
        os.makedirs(transcripts_dir, exist_ok=True)

        model = 'claude-opus-4-20250514'
        # Session 1: 2 turns
        self._make_transcript(
            os.path.join(transcripts_dir, 'sess-bf1.jsonl'), model,
            [(0, 0, 5, 100, 50), (1, 0, 5, 200, 100)],
        )
        # Session 2: 1 turn
        self._make_transcript(
            os.path.join(transcripts_dir, 'sess-bf2.jsonl'), model,
            [(0, 0, 10, 300, 150)],
        )

        result = subprocess.run(
            [sys.executable, BACKFILL, project_root],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

        turns = storage.get_all_turns(tracking_dir)
        assert len(turns) == 3
        session_ids = {t['session_id'] for t in turns}
        assert 'sess-bf1' in session_ids
        assert 'sess-bf2' in session_ids

    def test_backfill_skips_already_present(self, tmp_path):
        """Pre-populate DB with all expected turns, run backfill → no changes."""
        project_root = str(tmp_path / 'project')
        tracking_dir = os.path.join(project_root, '.claude', 'tracking')
        os.makedirs(tracking_dir, exist_ok=True)
        storage.init_db(tracking_dir)

        from platform_utils import slugify_path, get_transcripts_dir
        slug = slugify_path(project_root)
        transcripts_dir = os.path.join(get_transcripts_dir(), slug)
        os.makedirs(transcripts_dir, exist_ok=True)

        model = 'claude-opus-4-20250514'
        # Create transcript with 1 turn
        self._make_transcript(
            os.path.join(transcripts_dir, 'sess-skip.jsonl'), model,
            [(0, 0, 5, 100, 50)],
        )

        # Pre-populate by running backfill once
        subprocess.run(
            [sys.executable, BACKFILL, project_root],
            capture_output=True, text=True,
        )
        initial_turns = storage.get_all_turns(tracking_dir)
        initial_count = len(initial_turns)

        # Run backfill again
        result = subprocess.run(
            [sys.executable, BACKFILL, project_root],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert '0 sessions processed' in result.stdout

        final_turns = storage.get_all_turns(tracking_dir)
        assert len(final_turns) == initial_count
