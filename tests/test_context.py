"""Tests for markdown context file generation."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Add hooks/lib to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hooks", "lib"))

from models import SessionRecord, TranscriptState
from context import (
    build_compact_recovery_context, write_last_session,
    write_session_history, write_status,
)


class TestWriteLastSession(unittest.TestCase):
    """Tests for write_last_session."""

    def test_writes_valid_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            context_dir = Path(tmpdir)
            with patch("context.CONTEXT_DIR", context_dir):
                state = TranscriptState(
                    turn_count=5,
                    task_summary="Fixing the auth module",
                    last_user_request="commit the changes",
                    decisions=["Updated port to 8080 in config.json"],
                    files_modified=["/src/auth.py", "/tests/test_auth.py"],
                    topics=["authentication", "session handling"],
                )
                result = write_last_session(
                    state,
                    session_id="test-123",
                    transcript_path="/tmp/test.jsonl",
                    source="test",
                )

            content = Path(result).read_text()

        self.assertIn("# Last Session", content)
        self.assertIn("test-123", content)
        self.assertIn("**Turns**: 5", content)
        self.assertIn("Fixing the auth module", content)
        self.assertIn("commit the changes", content)
        self.assertIn("port to 8080", content)
        self.assertIn("`auth.py`", content)
        self.assertIn("authentication", content)

    def test_handles_empty_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            context_dir = Path(tmpdir)
            with patch("context.CONTEXT_DIR", context_dir):
                result = write_last_session(TranscriptState())

            content = Path(result).read_text()

        self.assertIn("# Last Session", content)
        self.assertIn("**Turns**: 0", content)

    def test_truncates_long_files_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            context_dir = Path(tmpdir)
            files = [f"/src/file_{i}.py" for i in range(15)]
            state = TranscriptState(
                turn_count=1,
                files_modified=files,
            )
            with patch("context.CONTEXT_DIR", context_dir):
                result = write_last_session(state)

            content = Path(result).read_text()

        self.assertIn("... and 5 more", content)


class TestWriteSessionHistory(unittest.TestCase):
    """Tests for write_session_history."""

    def test_writes_session_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            context_dir = Path(tmpdir)
            sessions = [
                SessionRecord(
                    session_id="session-1",
                    timestamp="2026-03-17T10:00:00",
                    turn_count=10,
                    working_on="Building auth",
                    decisions=["Fixed the config.json handler"],
                    files_modified=["/src/auth.py"],
                ),
                SessionRecord(
                    session_id="session-2",
                    timestamp="2026-03-16T10:00:00",
                    turn_count=5,
                    working_on="Deploying docker",
                ),
            ]
            with patch("context.CONTEXT_DIR", context_dir):
                result = write_session_history(sessions)

            content = Path(result).read_text()

        self.assertIn("# Session History", content)
        self.assertIn("**Sessions stored**: 2", content)
        self.assertIn("session-1", content)
        self.assertIn("Building auth", content)
        self.assertIn("config.json", content)

    def test_empty_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            context_dir = Path(tmpdir)
            with patch("context.CONTEXT_DIR", context_dir):
                result = write_session_history([])

            content = Path(result).read_text()

        self.assertIn("No previous sessions recorded yet", content)


class TestWriteStatus(unittest.TestCase):
    """Tests for write_status."""

    def test_writes_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            context_dir = Path(tmpdir)
            with patch("context.CONTEXT_DIR", context_dir):
                result = write_status(session_count=5)

            content = Path(result).read_text()

        self.assertIn("# Session Recorder Status", content)
        self.assertIn("Sessions stored: 5", content)
        self.assertIn("Backend: JSON files", content)


class TestBuildCompactRecoveryContext(unittest.TestCase):
    """Tests for build_compact_recovery_context."""

    def test_full_recovery(self) -> None:
        recovery = {
            "working_on": "Implementing session hooks",
            "last_user_request": "commit this",
            "decisions": ["Fixed the hook timeout in config.json"],
            "files_modified": ["/hooks/stop.py", "/hooks/start.py"],
            "topics": ["hooks", "session continuity"],
            "turn_count": 15,
            "last_assistant_response": "I committed the changes to the repository.",
        }
        result = build_compact_recovery_context(recovery)

        self.assertIn("CONTEXT COMPACTED", result)
        self.assertIn("Implementing session hooks", result)
        self.assertIn("commit this", result)
        self.assertIn("hook timeout", result)
        self.assertIn("stop.py", result)
        self.assertIn("15 turns", result)

    def test_empty_recovery(self) -> None:
        result = build_compact_recovery_context({})
        self.assertIn("CONTEXT COMPACTED", result)
        self.assertIn("refreshed", result)

    def test_partial_recovery(self) -> None:
        recovery = {"working_on": "Just this field"}
        result = build_compact_recovery_context(recovery)
        self.assertIn("Just this field", result)


if __name__ == "__main__":
    unittest.main()
