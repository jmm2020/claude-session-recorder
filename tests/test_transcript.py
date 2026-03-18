"""Tests for transcript parsing."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

# Add hooks/lib to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hooks", "lib"))

from models import TranscriptState
from transcript import parse_transcript


def _write_transcript(entries: list[dict], tmpdir: str) -> str:
    """Write JSONL transcript file and return its path."""
    path = os.path.join(tmpdir, "transcript.jsonl")
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    return path


class TestParseTranscript(unittest.TestCase):
    """Tests for parse_transcript()."""

    def test_empty_path(self) -> None:
        result = parse_transcript("")
        self.assertIsInstance(result, TranscriptState)
        self.assertEqual(result.turn_count, 0)

    def test_missing_file(self) -> None:
        result = parse_transcript("/nonexistent/path.jsonl")
        self.assertEqual(result.turn_count, 0)

    def test_none_path(self) -> None:
        result = parse_transcript(None)
        self.assertEqual(result.turn_count, 0)

    def test_basic_conversation(self) -> None:
        entries = [
            {"type": "user", "message": {"content": "Fix the bug in hooks/stop.py"}},
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "I fixed the timeout in stop.py from 5s to 15s."},
                    ]
                },
            },
            {"type": "user", "message": {"content": "Thanks, commit it"}},
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "Committed the change."},
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "input": {"command": "git commit -m 'fix timeout'"},
                        },
                    ]
                },
            },
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_transcript(entries, tmpdir)
            result = parse_transcript(path)

        self.assertEqual(result.turn_count, 2)
        self.assertEqual(result.message_count, 4)
        self.assertIn("Bash", result.tools_used)
        self.assertIn("Bash(git)", result.tools_used)
        self.assertEqual(result.last_user_request, "Thanks, commit it")

    def test_file_tracking(self) -> None:
        entries = [
            {"type": "user", "message": {"content": "Edit the config file"}},
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Edit",
                            "input": {"file_path": "/src/config.py"},
                        },
                        {
                            "type": "tool_use",
                            "name": "Write",
                            "input": {"file_path": "/src/new_file.py"},
                        },
                    ]
                },
            },
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_transcript(entries, tmpdir)
            result = parse_transcript(path)

        self.assertIn("/src/config.py", result.files_modified)
        self.assertIn("/src/new_file.py", result.files_modified)

    def test_system_reminders_filtered(self) -> None:
        entries = [
            {"type": "user", "message": {
                "content": "<system-reminder>injected</system-reminder>"}},
            {"type": "user", "message": {"content": "Do the real work"}},
            {"type": "user", "message": {
                "content": "<local-command-stdout>ok</local-command-stdout>"}},
            {"type": "user", "message": {"content": "<command-name>/help</command-name>"}},
            {"type": "user", "message": {"content": "<task-notification>done</task-notification>"}},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_transcript(entries, tmpdir)
            result = parse_transcript(path)

        self.assertEqual(result.turn_count, 1)
        self.assertEqual(result.last_user_request, "Do the real work")

    def test_tool_result_messages_filtered(self) -> None:
        entries = [
            {
                "type": "user",
                "message": {
                    "content": [
                        {"type": "tool_result", "tool_use_id": "abc", "content": "result data"},
                    ]
                },
            },
            {"type": "user", "message": {"content": "Actual user message"}},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_transcript(entries, tmpdir)
            result = parse_transcript(path)

        self.assertEqual(result.turn_count, 1)

    def test_empty_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "empty.jsonl")
            with open(path, "w") as f:
                f.write("")
            result = parse_transcript(path)

        self.assertEqual(result.turn_count, 0)
        self.assertEqual(result.message_count, 0)

    def test_malformed_jsonl_lines_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "bad.jsonl")
            with open(path, "w") as f:
                f.write("not json\n")
                f.write('{"type": "user", "message": {"content": "valid line"}}\n')
                f.write("{broken\n")
            result = parse_transcript(path)

        self.assertEqual(result.turn_count, 1)
        self.assertEqual(result.message_count, 1)

    def test_max_user_msgs_limit(self) -> None:
        entries = []
        for i in range(30):
            entries.append({"type": "user", "message": {"content": f"Message number {i}"}})
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_transcript(entries, tmpdir)
            result = parse_transcript(path, max_user_msgs=5)

        self.assertEqual(result.turn_count, 30)
        self.assertEqual(len(result.user_messages), 5)
        self.assertIn("Message number 29", result.user_messages[-1])


class TestDecisionExtraction(unittest.TestCase):
    """Tests for decision extraction from assistant messages."""

    def test_extracts_technical_decisions(self) -> None:
        entries = [
            {"type": "user", "message": {"content": "Fix the deployment issue"}},
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "text",
                            "text": "I fixed the timeout in hooks/stop.py from 5s to 15s. "
                            "Also updated the docker config to use port 8080.",
                        }
                    ]
                },
            },
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_transcript(entries, tmpdir)
            result = parse_transcript(path)

        self.assertTrue(len(result.decisions) > 0)
        has_hook_decision = any("hook" in d.lower() or ".py" in d for d in result.decisions)
        self.assertTrue(has_hook_decision, f"Expected hook-related decision in {result.decisions}")

    def test_skips_non_specific_decisions(self) -> None:
        entries = [
            {"type": "user", "message": {"content": "What should we do?"}},
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "text",
                            "text": "I fixed the general issue with the system. "
                            "Updated everything to be better.",
                        }
                    ]
                },
            },
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_transcript(entries, tmpdir)
            result = parse_transcript(path)

        # These lack specificity (no file paths, ports, technical terms)
        self.assertEqual(len(result.decisions), 0)

    def test_deduplicates_decisions(self) -> None:
        entries = [
            {"type": "user", "message": {"content": "Do the work"}},
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "text",
                            "text": "Fixed the hook in config.json to use new format. "
                            "Fixed the hook in config.json to use correct schema.",
                        }
                    ]
                },
            },
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_transcript(entries, tmpdir)
            result = parse_transcript(path)

        # Should deduplicate based on first 40 chars
        self.assertLessEqual(len(result.decisions), 1)


class TestTaskSummary(unittest.TestCase):
    """Tests for task summary extraction."""

    def test_skips_short_acknowledgments(self) -> None:
        entries = [
            {"type": "user", "message": {"content": "Fix the authentication module in auth.py"}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "Done."}]}},
            {"type": "user", "message": {"content": "ok"}},
            {"type": "user", "message": {"content": "yes"}},
            {"type": "user", "message": {"content": "thanks"}},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_transcript(entries, tmpdir)
            result = parse_transcript(path)

        self.assertIn("authentication", result.task_summary.lower())

    def test_uses_topic_fallback(self) -> None:
        entries = [
            {"type": "user", "message": {
                "content": "Short msg that is long enough for topic extraction"}},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_transcript(entries, tmpdir)
            result = parse_transcript(path)

        self.assertTrue(len(result.task_summary) > 0)


if __name__ == "__main__":
    unittest.main()
