"""Markdown context file generator for session continuity.

Writes structured markdown files that Claude Code reads as session context.
No external dependencies — pure stdlib.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path


CONTEXT_DIR = Path.home() / ".claude" / "context"


def _ensure_context_dir():
    """Create context directory if it doesn't exist."""
    CONTEXT_DIR.mkdir(parents=True, exist_ok=True)


def write_last_session(transcript_state, session_id="", transcript_path="",
                       last_message="", source="stop hook"):
    """Write last-session.md for next-session continuity.

    This is the crash-recovery file — what the next session sees first.

    Args:
        transcript_state: dict from parse_transcript()
        session_id: Claude session ID
        transcript_path: path to transcript JSONL
        last_message: assistant's last response text
        source: which hook wrote this ("stop hook", "pre-compact hook")

    Returns path to the written file.
    """
    _ensure_context_dir()
    context_file = CONTEXT_DIR / "last-session.md"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    turns = transcript_state.get("turn_count", 0)

    try:
        with context_file.open("w") as f:
            f.write("# Last Session\n\n")
            f.write("**Updated**: %s (written by %s)\n" % (now, source))
            if session_id:
                f.write("**Session**: %s\n" % session_id)
            if transcript_path:
                f.write("**Transcript**: %s\n" % transcript_path)
            f.write("**Turns**: %s\n\n" % turns)

            # What was being worked on
            task_summary = transcript_state.get("task_summary", "")
            if task_summary:
                f.write("## Working On\n")
                f.write("%s\n\n" % task_summary)

            # User's last request
            last_ask = transcript_state.get("last_user_request", "")
            if last_ask:
                f.write("## User's Last Request\n")
                f.write("%s\n\n" % last_ask[:500])

            # Key decisions
            decisions = transcript_state.get("decisions", [])
            if decisions:
                f.write("## Decisions Made\n")
                for d in decisions[-5:]:
                    f.write("- %s\n" % d)
                f.write("\n")

            # Files modified
            files = transcript_state.get("files_modified", [])
            if files:
                f.write("## Files Modified (%d)\n" % len(files))
                for fp in files[-10:]:
                    # Show just the filename for brevity
                    short = os.path.basename(fp)
                    f.write("- `%s`\n" % short)
                if len(files) > 10:
                    f.write("- ... and %d more\n" % (len(files) - 10))
                f.write("\n")

            # Recent topics
            topics = transcript_state.get("topics", [])
            if topics and len(topics) > 1:
                f.write("## Recent Topics\n")
                for t in topics[-5:]:
                    f.write("- %s\n" % t[:150])
                f.write("\n")

            # Last response
            last_resp = last_message or transcript_state.get("last_assistant_response", "")
            if last_resp:
                preview = last_resp[:800]
                if len(last_resp) > 800:
                    cut = preview.rfind(". ")
                    if cut > 400:
                        preview = preview[:cut + 1]
                    preview += "\n...(truncated)"
                f.write("## Assistant's Last Response\n")
                f.write("%s\n" % preview)
    except (IOError, OSError) as e:
        print("Failed to write last-session.md: %s" % e, file=sys.stderr)

    return str(context_file)


def write_session_history(sessions):
    """Write session-history.md from a list of past session dicts.

    Args:
        sessions: list of session dicts (newest first)
    """
    _ensure_context_dir()
    history_file = CONTEXT_DIR / "session-history.md"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with history_file.open("w") as f:
            f.write("# Session History\n\n")
            f.write("**Updated**: %s\n" % now)
            f.write("**Sessions stored**: %d\n\n" % len(sessions))

            if not sessions:
                f.write("No previous sessions recorded yet.\n")
                return str(history_file)

            for i, sess in enumerate(sessions[:10]):
                sid = sess.get("session_id", "?")[:16]
                ts = sess.get("timestamp", "?")
                if isinstance(ts, str) and len(ts) > 16:
                    ts = ts[:16]
                turns = sess.get("turn_count", "?")
                working = sess.get("working_on", "") or sess.get("task_summary", "")
                if working:
                    working = working[:120].replace("\n", " ")

                f.write("### %d. Session `%s`\n" % (i + 1, sid))
                f.write("- **When**: %s\n" % ts)
                f.write("- **Turns**: %s\n" % turns)
                if working:
                    f.write("- **Working on**: %s\n" % working)

                decisions = sess.get("decisions", [])
                if decisions:
                    f.write("- **Decisions**:\n")
                    for d in decisions[-3:]:
                        f.write("  - %s\n" % d[:150])

                files = sess.get("files_modified", [])
                if files:
                    short_files = [os.path.basename(fp) for fp in files[-5:]]
                    f.write("- **Files**: %s\n" % ", ".join(short_files))

                f.write("\n")
    except (IOError, OSError) as e:
        print("Failed to write session-history.md: %s" % e, file=sys.stderr)

    return str(history_file)


def write_status(session_count=0):
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
            f.write("**Updated**: %s\n\n" % now)
            f.write("## Storage\n")
            f.write("- Sessions stored: %d\n" % session_count)

            sessions_dir = Path.home() / ".claude" / "session-recorder" / "sessions"
            if sessions_dir.exists():
                total_size = sum(
                    fp.stat().st_size for fp in sessions_dir.glob("*.json")
                    if fp.is_file()
                )
                f.write("- Storage used: %.1f KB\n" % (total_size / 1024.0))
            f.write("- Backend: JSON files\n")
            f.write("- Location: ~/.claude/session-recorder/sessions/\n\n")

            f.write("## Context Files\n")
            context_dir = CONTEXT_DIR
            for name in ("last-session.md", "session-history.md", "session-status.md"):
                filepath = context_dir / name
                exists = filepath.exists()
                f.write("- %s: %s\n" % (name, "present" if exists else "missing"))
    except (IOError, OSError) as e:
        print("Failed to write session-status.md: %s" % e, file=sys.stderr)

    return str(status_file)


def build_compact_recovery_context(recovery):
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
        parts.append("**Working on**: %s" % working_on)

    last_request = recovery.get("last_user_request", "")
    if last_request:
        parts.append("**User's last request**: %s" % last_request)

    decisions = recovery.get("decisions", [])
    if decisions:
        parts.append("**Decisions made this session**:")
        for d in decisions:
            parts.append("  - %s" % d)

    files = recovery.get("files_modified", [])
    if files:
        short_files = [os.path.basename(f) for f in files]
        parts.append("**Files modified** (%d): %s" % (len(files), ", ".join(short_files)))

    topics = recovery.get("topics", [])
    if topics:
        parts.append("**Recent topics**: %s" % " | ".join(t[:100] for t in topics))

    turn_count = recovery.get("turn_count", 0)
    if turn_count:
        parts.append("**Session progress**: %d turns before compaction" % turn_count)

    last_response = recovery.get("last_assistant_response", "")
    if last_response:
        preview = last_response[:400]
        cut = preview.rfind(". ")
        if cut > 200:
            preview = preview[:cut + 1]
        parts.append("**Assistant's last response** (truncated): %s" % preview)

    parts.append(
        "\nAll context files (last-session.md, session-history.md, "
        "session-status.md) have been refreshed."
    )

    return "\n".join(parts)
