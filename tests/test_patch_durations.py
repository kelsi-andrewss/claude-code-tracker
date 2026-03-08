"""Tests for src/patch-durations.py — duration patching via subprocess E2E."""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import storage
from conftest import make_user_line, make_assistant_line, write_transcript, _ts

SRC_DIR = os.path.join(os.path.dirname(__file__), '..', 'src')
PATCH_DURATIONS = os.path.join(SRC_DIR, 'patch-durations.py')


def _setup_env(tmp_path):
    """Create a controlled environment for patch-durations.py.

    Returns (project_root, tracking_dir, transcripts_dir, env).

    patch-durations.py computes:
        slug = project_root.replace("/", "-")
        transcripts_dir = os.path.expanduser("~/.claude/projects/" + slug)
    So with HOME=tmp_path/fakehome:
        transcripts_dir = tmp_path/fakehome/.claude/projects/<slug>
    """
    project_root = str(tmp_path / 'myproject')
    tracking_dir = os.path.join(project_root, '.claude', 'tracking')
    os.makedirs(tracking_dir, exist_ok=True)
    storage.init_db(tracking_dir)

    fakehome = str(tmp_path / 'fakehome')
    slug = project_root.replace('/', '-')
    transcripts_dir = os.path.join(fakehome, '.claude', 'projects', slug)
    os.makedirs(transcripts_dir, exist_ok=True)

    env = os.environ.copy()
    env['HOME'] = fakehome

    return project_root, tracking_dir, transcripts_dir, env


def _insert_turn(tracking_dir, session_id, turn_index, duration_seconds=0):
    """Insert a turn row into the DB with given duration."""
    entry = {
        'session_id': session_id,
        'turn_index': turn_index,
        'date': '2026-03-07',
        'project': 'test-proj',
        'turn_timestamp': _ts(turn_index, 0),
        'input_tokens': 100,
        'output_tokens': 50,
        'total_tokens': 150,
        'duration_seconds': duration_seconds,
        'model': 'claude-opus-4-20250514',
    }
    storage.upsert_turns(tracking_dir, [entry])


def _make_transcript_file(transcripts_dir, session_id, turn_specs):
    """Write a JSONL transcript for a session.

    turn_specs: list of (user_minute, user_second, asst_minute, asst_second) tuples.
    """
    model = 'claude-opus-4-20250514'
    lines = []
    for u_min, u_sec, a_min, a_sec in turn_specs:
        lines.append(make_user_line(f'turn', _ts(u_min, u_sec)))
        lines.append(make_assistant_line(_ts(a_min, a_sec), model, 100, 50))
    path = os.path.join(transcripts_dir, session_id + '.jsonl')
    write_transcript(lines, path)


class TestPatchDurations:

    def test_patches_zero_duration_turn(self, tmp_path):
        """Turn with duration_seconds=0, transcript has 10s gap → patched to 10."""
        project_root, tracking_dir, transcripts_dir, env = _setup_env(tmp_path)

        _insert_turn(tracking_dir, 'sess-pd1', 0, duration_seconds=0)
        # User at 00:00, assistant at 00:10 → 10s gap
        _make_transcript_file(transcripts_dir, 'sess-pd1', [(0, 0, 0, 10)])

        result = subprocess.run(
            [sys.executable, PATCH_DURATIONS, project_root],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

        turns = storage.get_session_turns(tracking_dir, 'sess-pd1')
        assert len(turns) == 1
        assert turns[0]['duration_seconds'] == 10

    def test_skips_nonzero_duration(self, tmp_path):
        """Turn with duration_seconds=42 → not modified."""
        project_root, tracking_dir, transcripts_dir, env = _setup_env(tmp_path)

        _insert_turn(tracking_dir, 'sess-pd2', 0, duration_seconds=42)
        _make_transcript_file(transcripts_dir, 'sess-pd2', [(0, 0, 0, 10)])

        result = subprocess.run(
            [sys.executable, PATCH_DURATIONS, project_root],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0

        turns = storage.get_session_turns(tracking_dir, 'sess-pd2')
        assert turns[0]['duration_seconds'] == 42

    def test_skips_missing_transcript(self, tmp_path):
        """Turn in DB but no transcript file → no crash, duration stays 0."""
        project_root, tracking_dir, transcripts_dir, env = _setup_env(tmp_path)

        _insert_turn(tracking_dir, 'sess-pd3', 0, duration_seconds=0)
        # Don't create a transcript file for sess-pd3

        result = subprocess.run(
            [sys.executable, PATCH_DURATIONS, project_root],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0

        turns = storage.get_session_turns(tracking_dir, 'sess-pd3')
        assert turns[0]['duration_seconds'] == 0

    def test_patches_correct_turn_index(self, tmp_path):
        """Turns 0,1,2 all with duration=0, transcript has 5s,10s,15s gaps → each patched correctly."""
        project_root, tracking_dir, transcripts_dir, env = _setup_env(tmp_path)

        for i in range(3):
            _insert_turn(tracking_dir, 'sess-pd4', i, duration_seconds=0)

        # Turn 0: 00:00 → 00:05 (5s)
        # Turn 1: 01:00 → 01:10 (10s)
        # Turn 2: 02:00 → 02:15 (15s)
        _make_transcript_file(transcripts_dir, 'sess-pd4', [
            (0, 0, 0, 5),
            (1, 0, 1, 10),
            (2, 0, 2, 15),
        ])

        result = subprocess.run(
            [sys.executable, PATCH_DURATIONS, project_root],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

        turns = storage.get_session_turns(tracking_dir, 'sess-pd4')
        assert len(turns) == 3
        assert turns[0]['duration_seconds'] == 5
        assert turns[1]['duration_seconds'] == 10
        assert turns[2]['duration_seconds'] == 15

    def test_negative_duration_clamped(self, tmp_path):
        """Assistant ts before user ts → duration stays 0 (max(0, ...) produces 0,
        then `duration > 0` check at line 82 prevents the patch)."""
        project_root, tracking_dir, transcripts_dir, env = _setup_env(tmp_path)

        _insert_turn(tracking_dir, 'sess-pd5', 0, duration_seconds=0)
        # User at 00:10, assistant at 00:00 → negative gap
        _make_transcript_file(transcripts_dir, 'sess-pd5', [(0, 10, 0, 0)])

        result = subprocess.run(
            [sys.executable, PATCH_DURATIONS, project_root],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0

        turns = storage.get_session_turns(tracking_dir, 'sess-pd5')
        assert turns[0]['duration_seconds'] == 0
