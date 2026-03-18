"""Markdown context file generator for session continuity.

Writes structured markdown files that Claude Code reads as session context.
No external dependencies — pure stdlib.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from models import SessionRecord, TranscriptState

CONTEXT_DIR: Path = Path.home() / ".claude" / "context"


def _ensure_context_dir() -> None:
    """Create context directory if it doesn't exist."""
    CONTEXT_DIR.mkdir(parents=True, exist_ok=True)


def write_last_session(
    transcript_state: TranscriptState,
    session_id: str = "",
    transcript_path: str = "",
    last_message: str = "",
    source: str = "stop hook",
) -> str:
    """Write last-session.md for next-session continuity.

    This is the crash-recovery file -- what the next session sees first.

    Args:
        transcript_state: TranscriptState from parse_transcript()
        session_id: Claude session ID
        transcript_path: path to transcript JSONL
        last_message: assistant's last response text
        source: which hook wrote this ("stop hook", "pre-compact hook")

    Returns path to the written file.
    """
    _ensure_context_dir()
    context_file = CONTEXT_DIR / "last-session.md"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    turns = transcript_state.turn_count

    try:
        with context_file.open("w") as f:
            f.write("# Last Session\n\n")
            f.write(f"**Updated**: {now} (written by {source})\n")
            if session_id:
                f.write(f"**Session**: {session_id}\n")
            if transcript_path:
                f.write(f"**Transcript**: {transcript_path}\n")
            f.write(f"**Turns**: {turns}\n\n")

            # What was being worked on
            task_summary = transcript_state.task_summary
            if task_summary:
                f.write("## Working On\n")
                f.write(f"{task_summary}\n\n")

            # User's last request
            last_ask = transcript_state.last_user_request
            if last_ask:
                f.write("## User's Last Request\n")
                f.write(f"{last_ask[:500]}\n\n")

            # Key decisions
            decisions = transcript_state.decisions
            if decisions:
                f.write("## Decisions Made\n")
                for d in decisions[-5:]:
                    f.write(f"- {d}\n")
                f.write("\n")

            # Files modified
            files = transcript_state.files_modified
            if files:
                f.write(f"## Files Modified ({len(files)})\n")
                for fp in files[-10:]:
                    # Show just the filename for brevity
                    short = os.path.basename(fp)
                    f.write(f"- `{short}`\n")
                if len(files) > 10:
                    f.write(f"- ... and {len(files) - 10} more\n")
                f.write("\n")

            # Recent topics
            topics = transcript_state.topics
            if topics and len(topics) > 1:
                f.write("## Recent Topics\n")
                for t in topics[-5:]:
                    f.write(f"- {t[:150]}\n")
                f.write("\n")

            # Last response
            last_resp = last_message or transcript_state.last_assistant_response
            if last_resp:
                preview = last_resp[:800]
                if len(last_resp) > 800:
                    cut = preview.rfind(". ")
                    if cut > 400:
                        preview = preview[:cut + 1]
                    preview += "\n...(truncated)"
                f.write("## Assistant's Last Response\n")
                f.write(f"{preview}\n")
    except (IOError, OSError) as e:
        print(f"Failed to write last-session.md: {e}", file=sys.stderr)

    return str(context_file)


def write_session_history(sessions: List[SessionRecord]) -> str:
    """Write session-history.md from a list of past SessionRecord objects.

    Args:
        sessions: list of SessionRecord (newest first)
    """
    _ensure_context_dir()
    history_file = CONTEXT_DIR / "session-history.md"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with history_file.open("w") as f:
            f.write("# Session History\n\n")
            f.write(f"**Updated**: {now}\n")
            f.write(f"**Sessions stored**: {len(sessions)}\n\n")

            if not sessions:
                f.write("No previous sessions recorded yet.\n")
                return str(history_file)

            for i, sess in enumerate(sessions[:10]):
                sid = sess.session_id[:16] if sess.session_id else "?"
                ts = sess.timestamp
                if isinstance(ts, str) and len(ts) > 16:
                    ts = ts[:16]
                turns = sess.turn_count
                working = sess.working_on or ""
                if working:
                    working = working[:120].replace("\n", " ")

                f.write(f"### {i + 1}. Session `{sid}`\n")
                f.write(f"- **When**: {ts}\n")
                f.write(f"- **Turns**: {turns}\n")
                if working:
                    f.write(f"- **Working on**: {working}\n")

                decisions = sess.decisions
                if decisions:
                    f.write("- **Decisions**:\n")
                    for d in decisions[-3:]:
                        f.write(f"  - {d[:150]}\n")

                files = sess.files_modified
                if files:
                    short_files = [os.path.basename(fp) for fp in files[-5:]]
                    f.write(f"- **Files**: {', '.join(short_files)}\n")

                f.write("\n")
    except (IOError, OSError) as e:
        print(f"Failed to write session-history.md: {e}", file=sys.stderr)

    return str(history_file)


def write_status(session_count: int = 0) -> str:
    """Write session-status.md with recorder health info.

    Args:
        session_count: number of stored sessions
    """
    _ensure_context_dir()
    status_file = CONTEXT_DIR / "session-status.md"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with status_file.open("w") as f:
            f.write("# Session Recorder Status\n\n")
            f.write(f"**Updated**: {now}\n\n")
            f.write("## Storage\n")
            f.write(f"- Sessions stored: {session_count}\n")

            sessions_dir = Path.home() / ".claude" / "session-recorder" / "sessions"
            if sessions_dir.exists():
                total_size = sum(
                    fp.stat().st_size for fp in sessions_dir.glob("*.json")
                    if fp.is_file()
                )
                f.write(f"- Storage used: {total_size / 1024.0:.1f} KB\n")
            f.write("- Backend: JSON files\n")
            f.write("- Location: ~/.claude/session-recorder/sessions/\n\n")

            f.write("## Context Files\n")
            context_dir = CONTEXT_DIR
            for name in ("last-session.md", "session-history.md", "session-status.md"):
                filepath = context_dir / name
                exists = filepath.exists()
                status = "present" if exists else "missing"
                f.write(f"- {name}: {status}\n")
    except (IOError, OSError) as e:
        print(f"Failed to write session-status.md: {e}", file=sys.stderr)

    return str(status_file)


def build_compact_recovery_context(recovery: Dict[str, Any]) -> str:
    """Build rich context string from compact recovery JSON.

    This is injected as additionalContext when SessionStart fires
    after a context compaction, giving the LLM full awareness of
    what was happening before the compaction wiped its context.

    Args:
        recovery: dict loaded from the recovery JSON file

    Returns: formatted context string
    """
    parts = ["CONTEXT COMPACTED -- Session state re-injected from pre-compact snapshot.\n"]

    working_on = recovery.get("working_on", "")
    if working_on:
        parts.append(f"**Working on**: {working_on}")

    last_request = recovery.get("last_user_request", "")
    if last_request:
        parts.append(f"**User's last request**: {last_request}")

    decisions = recovery.get("decisions", [])
    if decisions:
        parts.append("**Decisions made this session**:")
        for d in decisions:
            parts.append(f"  - {d}")

    files = recovery.get("files_modified", [])
    if files:
        short_files = [os.path.basename(fp) for fp in files]
        parts.append(f"**Files modified** ({len(files)}): {', '.join(short_files)}")

    topics = recovery.get("topics", [])
    if topics:
        parts.append(f"**Recent topics**: {' | '.join(t[:100] for t in topics)}")

    turn_count = recovery.get("turn_count", 0)
    if turn_count:
        parts.append(f"**Session progress**: {turn_count} turns before compaction")

    last_response = recovery.get("last_assistant_response", "")
    if last_response:
        preview = last_response[:400]
        cut = preview.rfind(". ")
        if cut > 200:
            preview = preview[:cut + 1]
        parts.append(f"**Assistant's last response** (truncated): {preview}")

    parts.append(
        "\nAll context files (last-session.md, session-history.md, "
        "session-status.md) have been refreshed."
    )

    return "\n".join(parts)
