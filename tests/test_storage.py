"""Tests for JSON file storage backend."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Add hooks/lib to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hooks", "lib"))

from models import RecorderConfig, SessionRecord
from storage import _prune_sessions, find_related_sessions, load_config, load_sessions, save_session


class TestSessionRecord(unittest.TestCase):
    """Tests for SessionRecord dataclass."""

    def test_round_trip(self) -> None:
        record = SessionRecord(
            session_id="abc123",
            timestamp="2026-03-17T10:00:00",
            turn_count=5,
            working_on="Testing storage",
            decisions=["Fixed the config.json format"],
            files_modified=["/src/main.py"],
            topics=["storage", "testing"],
        )
        d = record.to_dict()
        restored = SessionRecord.from_dict(d)
        self.assertEqual(record, restored)

    def test_from_dict_ignores_unknown_keys(self) -> None:
        data = {"session_id": "abc", "unknown_field": "ignored", "extra": 42}
        record = SessionRecord.from_dict(data)
        self.assertEqual(record.session_id, "abc")

    def test_defaults(self) -> None:
        record = SessionRecord()
        self.assertEqual(record.session_id, "")
        self.assertEqual(record.turn_count, 0)
        self.assertEqual(record.decisions, [])


class TestSaveAndLoad(unittest.TestCase):
    """Tests for save_session and load_sessions."""

    def test_save_and_load_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir) / "sessions"
            sessions_dir.mkdir()

            record = SessionRecord(
                session_id="test-session",
                timestamp="2026-03-17T10:00:00",
                turn_count=10,
                working_on="Round trip test",
                decisions=["Added type hints"],
                files_modified=["/hooks/stop.py"],
                topics=["testing"],
            )

            with patch("storage._storage_dir", return_value=sessions_dir):
                save_session(record)
                loaded = load_sessions(limit=10)

            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].session_id, "test-session")
            self.assertEqual(loaded[0].turn_count, 10)
            self.assertEqual(loaded[0].working_on, "Round trip test")
            self.assertEqual(loaded[0].decisions, ["Added type hints"])

    def test_load_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir) / "sessions"
            sessions_dir.mkdir()

            for i in range(3):
                record = SessionRecord(
                    session_id=f"session-{i}",
                    timestamp=f"2026-03-1{i}T10:00:00",
                    turn_count=i + 1,
                )
                with patch("storage._storage_dir", return_value=sessions_dir):
                    save_session(record)

            with patch("storage._storage_dir", return_value=sessions_dir):
                loaded = load_sessions(limit=10)

            self.assertEqual(len(loaded), 3)
            # Newest first (session-2 has latest timestamp)
            self.assertEqual(loaded[0].session_id, "session-2")

    def test_load_respects_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir) / "sessions"
            sessions_dir.mkdir()

            for i in range(5):
                record = SessionRecord(
                    session_id=f"session-{i}",
                    timestamp=f"2026-03-1{i}T10:00:00",
                )
                with patch("storage._storage_dir", return_value=sessions_dir):
                    save_session(record)

            with patch("storage._storage_dir", return_value=sessions_dir):
                loaded = load_sessions(limit=2)

            self.assertEqual(len(loaded), 2)

    def test_load_empty_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir) / "sessions"
            sessions_dir.mkdir()

            with patch("storage._storage_dir", return_value=sessions_dir):
                loaded = load_sessions()

            self.assertEqual(loaded, [])


class TestPruning(unittest.TestCase):
    """Tests for session file pruning."""

    def test_prunes_oldest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir)
            # Create 5 files
            for i in range(5):
                (sessions_dir / f"2026-03-1{i}_sess{i}.json").write_text("{}")

            _prune_sessions(sessions_dir, max_sessions=3)

            remaining = sorted(sessions_dir.glob("*.json"))
            self.assertEqual(len(remaining), 3)
            # Oldest (10, 11) should be gone, newest (12, 13, 14) kept
            names = [f.name for f in remaining]
            self.assertNotIn("2026-03-10_sess0.json", names)
            self.assertNotIn("2026-03-11_sess1.json", names)

    def test_no_pruning_under_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir)
            (sessions_dir / "2026-03-10_sess.json").write_text("{}")

            _prune_sessions(sessions_dir, max_sessions=20)

            self.assertEqual(len(list(sessions_dir.glob("*.json"))), 1)


class TestFindRelated(unittest.TestCase):
    """Tests for find_related_sessions."""

    def test_finds_matching_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir) / "sessions"
            sessions_dir.mkdir()

            records = [
                SessionRecord(
                    session_id="docker-session",
                    timestamp="2026-03-15T10:00:00",
                    working_on="Docker compose configuration",
                    topics=["docker", "deployment"],
                ),
                SessionRecord(
                    session_id="auth-session",
                    timestamp="2026-03-16T10:00:00",
                    working_on="Authentication middleware",
                    topics=["auth", "security"],
                ),
                SessionRecord(
                    session_id="docker-again",
                    timestamp="2026-03-17T10:00:00",
                    working_on="Docker networking fix",
                    topics=["docker", "networking"],
                ),
            ]

            for r in records:
                with patch("storage._storage_dir", return_value=sessions_dir):
                    save_session(r)

            with patch("storage._storage_dir", return_value=sessions_dir):
                related = find_related_sessions(["docker"], limit=5)

            self.assertEqual(len(related), 2)
            ids = [r.session_id for r in related]
            self.assertIn("docker-session", ids)
            self.assertIn("docker-again", ids)

    def test_empty_keywords(self) -> None:
        result = find_related_sessions([])
        self.assertEqual(result, [])

    def test_short_keywords_filtered(self) -> None:
        result = find_related_sessions(["ab", "x", ""])
        self.assertEqual(result, [])


class TestLoadConfig(unittest.TestCase):
    """Tests for load_config."""

    def test_defaults(self) -> None:
        # Clear lru_cache to get fresh config
        from storage import _load_config_cached
        _load_config_cached.cache_clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Point to a non-existent config location
            with patch.dict(os.environ, {"CLAUDE_PLUGIN_ROOT": tmpdir}):
                _load_config_cached.cache_clear()
                config = load_config()

        self.assertIsInstance(config, RecorderConfig)
        self.assertEqual(config.max_sessions, 20)
        self.assertEqual(config.max_decisions, 5)
        self.assertFalse(config.verbose_logging)

    def test_custom_config(self) -> None:
        from storage import _load_config_cached
        _load_config_cached.cache_clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(json.dumps({"max_sessions": 50, "verbose_logging": True}))

            with patch.dict(os.environ, {"CLAUDE_PLUGIN_ROOT": tmpdir}):
                _load_config_cached.cache_clear()
                config = load_config()

        self.assertEqual(config.max_sessions, 50)
        self.assertTrue(config.verbose_logging)
        _load_config_cached.cache_clear()


if __name__ == "__main__":
    unittest.main()
