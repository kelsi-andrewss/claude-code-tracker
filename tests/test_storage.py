"""Unit tests for src/storage.py — SQLite storage module."""
import json
import os
import sqlite3
import sys
import tempfile
import unittest

# Allow importing storage from src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import storage


def _make_turn(session_id="s1", turn_index=0, date="2026-01-01", project="proj",
               total_tokens=100, **kwargs):
    """Helper to build a turn dict with sensible defaults."""
    base = {
        "session_id": session_id,
        "turn_index": turn_index,
        "date": date,
        "project": project,
        "total_tokens": total_tokens,
    }
    base.update(kwargs)
    return base


def _make_agent(session_id="s1", agent_id="a1", timestamp="2026-01-01T00:00:00Z",
                **kwargs):
    """Helper to build an agent dict with sensible defaults."""
    base = {
        "session_id": session_id,
        "agent_id": agent_id,
        "timestamp": timestamp,
    }
    base.update(kwargs)
    return base


class TestInitDb(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_creates_database_file(self):
        storage.init_db(self.tmpdir)
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, "tracking.db")))

    def test_tables_exist(self):
        storage.init_db(self.tmpdir)
        conn = sqlite3.connect(os.path.join(self.tmpdir, "tracking.db"))
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        self.assertIn("turns", tables)
        self.assertIn("agents", tables)
        self.assertIn("metadata", tables)

    def test_idempotent(self):
        storage.init_db(self.tmpdir)
        storage.init_db(self.tmpdir)  # second call should not raise
        conn = sqlite3.connect(os.path.join(self.tmpdir, "tracking.db"))
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        self.assertIn("turns", tables)


class TestUpsertTurns(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        storage.init_db(self.tmpdir)

    def test_insert_and_dedup(self):
        turns = [
            _make_turn(turn_index=0, total_tokens=100),
            _make_turn(turn_index=1, total_tokens=200),
            _make_turn(turn_index=2, total_tokens=300),
        ]
        storage.upsert_turns(self.tmpdir, turns)

        # Re-insert same keys with different values
        updated = [
            _make_turn(turn_index=0, total_tokens=111),
            _make_turn(turn_index=1, total_tokens=222),
            _make_turn(turn_index=2, total_tokens=333),
        ]
        storage.upsert_turns(self.tmpdir, updated)

        all_turns = storage.get_all_turns(self.tmpdir)
        self.assertEqual(len(all_turns), 3)
        self.assertEqual(all_turns[0]["total_tokens"], 111)
        self.assertEqual(all_turns[1]["total_tokens"], 222)
        self.assertEqual(all_turns[2]["total_tokens"], 333)

    def test_returns_count(self):
        turns = [_make_turn(turn_index=i) for i in range(5)]
        result = storage.upsert_turns(self.tmpdir, turns)
        self.assertEqual(result, 5)


class TestAppendAgent(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        storage.init_db(self.tmpdir)

    def test_always_appends(self):
        agent = _make_agent()
        storage.append_agent(self.tmpdir, agent)
        storage.append_agent(self.tmpdir, agent)  # same data, still appends

        agents = storage.get_all_agents(self.tmpdir)
        self.assertEqual(len(agents), 2)


class TestGetAllTurns(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        storage.init_db(self.tmpdir)

    def test_ordering(self):
        # Insert out of order
        storage.upsert_turns(self.tmpdir, [
            _make_turn(session_id="s2", turn_index=1, date="2026-01-02"),
            _make_turn(session_id="s1", turn_index=0, date="2026-01-01"),
            _make_turn(session_id="s1", turn_index=1, date="2026-01-01"),
            _make_turn(session_id="s2", turn_index=0, date="2026-01-02"),
            _make_turn(session_id="s1", turn_index=0, date="2026-01-02"),
        ])

        turns = storage.get_all_turns(self.tmpdir)
        keys = [(t["date"], t["session_id"], t["turn_index"]) for t in turns]
        self.assertEqual(keys, sorted(keys))


class TestGetAllAgents(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        storage.init_db(self.tmpdir)

    def test_strips_id(self):
        storage.append_agent(self.tmpdir, _make_agent())
        agents = storage.get_all_agents(self.tmpdir)
        self.assertEqual(len(agents), 1)
        self.assertNotIn("id", agents[0])
        self.assertIn("session_id", agents[0])


class TestMigration(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_migrates_json_files(self):
        tokens_path = os.path.join(self.tmpdir, "tokens.json")
        agents_path = os.path.join(self.tmpdir, "agents.json")

        turns_data = [
            _make_turn(turn_index=0),
            _make_turn(turn_index=1),
        ]
        agents_data = [_make_agent()]

        with open(tokens_path, "w") as f:
            json.dump(turns_data, f)
        with open(agents_path, "w") as f:
            json.dump(agents_data, f)

        # get_db triggers migration
        conn = storage.get_db(self.tmpdir)
        conn.close()

        # Data should be in SQLite
        all_turns = storage.get_all_turns(self.tmpdir)
        all_agents = storage.get_all_agents(self.tmpdir)
        self.assertEqual(len(all_turns), 2)
        self.assertEqual(len(all_agents), 1)

        # .json.migrated files should exist, originals should be gone
        self.assertTrue(os.path.exists(tokens_path + ".migrated"))
        self.assertTrue(os.path.exists(agents_path + ".migrated"))
        self.assertFalse(os.path.exists(tokens_path))
        self.assertFalse(os.path.exists(agents_path))

    def test_second_get_db_does_not_remigrate(self):
        tokens_path = os.path.join(self.tmpdir, "tokens.json")
        with open(tokens_path, "w") as f:
            json.dump([_make_turn()], f)

        conn = storage.get_db(self.tmpdir)
        conn.close()

        # Place a new tokens.json — should NOT be migrated again
        with open(tokens_path, "w") as f:
            json.dump([_make_turn(turn_index=99)], f)

        conn = storage.get_db(self.tmpdir)
        conn.close()

        all_turns = storage.get_all_turns(self.tmpdir)
        # Still only the original 1 turn, not the new one
        self.assertEqual(len(all_turns), 1)
        self.assertEqual(all_turns[0]["turn_index"], 0)


class TestExportJson(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        storage.init_db(self.tmpdir)

    def test_round_trip(self):
        turns = [_make_turn(turn_index=i, total_tokens=i * 10) for i in range(3)]
        storage.upsert_turns(self.tmpdir, turns)
        storage.append_agent(self.tmpdir, _make_agent(total_tokens=42))

        tokens_out = os.path.join(self.tmpdir, "tokens_export.json")
        agents_out = os.path.join(self.tmpdir, "agents_export.json")
        storage.export_json(self.tmpdir, tokens_path=tokens_out, agents_path=agents_out)

        with open(tokens_out) as f:
            exported_turns = json.load(f)
        with open(agents_out) as f:
            exported_agents = json.load(f)

        self.assertEqual(len(exported_turns), 3)
        self.assertEqual(len(exported_agents), 1)
        # Verify content matches what's in the DB
        db_turns = storage.get_all_turns(self.tmpdir)
        self.assertEqual(exported_turns, db_turns)


class TestReplaceSessionTurns(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        storage.init_db(self.tmpdir)

    def test_replaces_only_target_session(self):
        storage.upsert_turns(self.tmpdir, [
            _make_turn(session_id="s1", turn_index=0, total_tokens=10),
            _make_turn(session_id="s1", turn_index=1, total_tokens=20),
            _make_turn(session_id="s2", turn_index=0, total_tokens=30),
        ])

        # Replace s1 with new data
        replacements = [
            _make_turn(session_id="s1", turn_index=0, total_tokens=99),
        ]
        storage.replace_session_turns(self.tmpdir, "s1", replacements)

        all_turns = storage.get_all_turns(self.tmpdir)
        s1_turns = [t for t in all_turns if t["session_id"] == "s1"]
        s2_turns = [t for t in all_turns if t["session_id"] == "s2"]

        # s1: replaced — 1 row with updated value
        self.assertEqual(len(s1_turns), 1)
        self.assertEqual(s1_turns[0]["total_tokens"], 99)

        # s2: untouched
        self.assertEqual(len(s2_turns), 1)
        self.assertEqual(s2_turns[0]["total_tokens"], 30)


class TestPatchTurnDuration(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        storage.init_db(self.tmpdir)

    def test_patch_from_zero(self):
        storage.upsert_turns(self.tmpdir, [
            _make_turn(session_id="s1", turn_index=0, duration_seconds=0),
        ])

        storage.patch_turn_duration(self.tmpdir, "s1", 0, 42)

        turns = storage.get_all_turns(self.tmpdir)
        self.assertEqual(turns[0]["duration_seconds"], 42)


class TestCountTurnsForSession(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        storage.init_db(self.tmpdir)

    def test_counts_per_session(self):
        storage.upsert_turns(self.tmpdir, [
            _make_turn(session_id="s1", turn_index=0),
            _make_turn(session_id="s1", turn_index=1),
            _make_turn(session_id="s1", turn_index=2),
            _make_turn(session_id="s2", turn_index=0),
            _make_turn(session_id="s2", turn_index=1),
        ])

        self.assertEqual(storage.count_turns_for_session(self.tmpdir, "s1"), 3)
        self.assertEqual(storage.count_turns_for_session(self.tmpdir, "s2"), 2)
        self.assertEqual(storage.count_turns_for_session(self.tmpdir, "s3"), 0)


class TestSkillsTable(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        storage.init_db(self.tmpdir)

    def _make_skill(self, **kwargs):
        base = {
            "session_id": "s1",
            "date": "2026-01-01",
            "project": "proj",
            "skill_name": "commit",
        }
        base.update(kwargs)
        return base

    def test_table_created_on_init(self):
        conn = sqlite3.connect(os.path.join(self.tmpdir, "tracking.db"))
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        self.assertIn("skills", tables)

    def test_replace_inserts_then_replaces(self):
        entries = [self._make_skill(skill_name="commit")]
        storage.replace_session_skills(self.tmpdir, "s1", entries)

        all_skills = storage.get_all_skills(self.tmpdir)
        self.assertEqual(len(all_skills), 1)
        self.assertEqual(all_skills[0]["skill_name"], "commit")

        # Replace with different data
        entries2 = [self._make_skill(skill_name="audit")]
        storage.replace_session_skills(self.tmpdir, "s1", entries2)

        all_skills = storage.get_all_skills(self.tmpdir)
        self.assertEqual(len(all_skills), 1)
        self.assertEqual(all_skills[0]["skill_name"], "audit")

    def test_get_all_strips_id(self):
        storage.replace_session_skills(self.tmpdir, "s1", [self._make_skill()])
        all_skills = storage.get_all_skills(self.tmpdir)
        self.assertEqual(len(all_skills), 1)
        self.assertNotIn("id", all_skills[0])
        self.assertIn("skill_name", all_skills[0])

    def test_schema_upgrade_on_existing_db(self):
        """Opening an existing DB with get_db should create skills table."""
        # Create a DB without the skills table
        path = os.path.join(self.tmpdir, "tracking.db")
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('migrated_at', '2026-01-01')")
        conn.commit()
        conn.close()

        # get_db should add the skills table via executescript
        conn = storage.get_db(self.tmpdir)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        self.assertIn("skills", tables)


if __name__ == "__main__":
    unittest.main()
