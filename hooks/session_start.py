#!/usr/bin/env python3
"""SessionStart hook -- injects session context into every new session.

This is the ONLY hook that outputs JSON to stdout (Claude Code expects it).
Reads past session data and writes context files for session awareness.

Queries:
  - Last session state from last-session.md (crash recovery)
  - Session history from JSON storage
  - Related past sessions via keyword matching
  - Compact recovery state (when source="compact")
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Add lib directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

COMPACT_RECOVERY_FILE: str = os.path.join(
    os.environ.get("TMPDIR", "/tmp"),
    "claude_session_memory_recovery.json",
)


def _extract_keywords_from_last_session() -> list[str]:
    """Extract keywords from last-session.md for related session search."""
    keywords: list[str] = []
    try:
        last_session = Path.home() / ".claude" / "context" / "last-session.md"
        if not last_session.exists():
            return keywords

        content = last_session.read_text()

        # Extract from "Working On" section
        if "## Working On" in content:
            section = content.split("## Working On")[1].split("##")[0].strip()
            if section:
                # Split into words, keep meaningful ones
                words = re.findall(r'[a-zA-Z_][a-zA-Z0-9_.-]{2,}', section)
                keywords.extend(w.lower() for w in words[:10])

        # Extract from "Recent Topics" section
        if "## Recent Topics" in content:
            section = content.split("## Recent Topics")[1].split("##")[0].strip()
            words = re.findall(r'[a-zA-Z_][a-zA-Z0-9_.-]{2,}', section)
            keywords.extend(w.lower() for w in words[:10])

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        # Filter out very common words
        stopwords = {
            "the", "and", "for", "that", "this", "with", "from", "have",
            "was", "are", "been", "not", "but", "will", "can", "had",
            "has", "its", "all", "into", "more", "some", "than", "also",
            "just", "file", "files", "code", "new", "use", "using",
        }
        for kw in keywords:
            if kw not in seen and kw not in stopwords and len(kw) > 2:
                seen.add(kw)
                unique.append(kw)
        return unique[:15]
    except Exception:
        return []


def _update_context_files() -> None:
    """Write session-history.md and session-status.md from stored sessions."""
    try:
        from storage import load_sessions
        from context import write_session_history, write_status

        sessions = load_sessions(limit=10)
        write_session_history(sessions)
        write_status(session_count=len(sessions))
    except Exception:
        pass


def main() -> None:
    # Read hook input from stdin
    hook_input: dict = {}
    if not sys.stdin.isatty():
        try:
            hook_input = json.load(sys.stdin)
        except (ValueError, EOFError):
            pass

    source: str = hook_input.get("source", "startup")

    try:
        # Always: update session history and status files
        _update_context_files()

        additional = ""

        if source == "compact":
            # Post-compaction: read recovery JSON and build rich context
            try:
                if os.path.exists(COMPACT_RECOVERY_FILE):
                    with open(COMPACT_RECOVERY_FILE, "r") as f:
                        recovery = json.load(f)

                    from context import build_compact_recovery_context
                    additional = build_compact_recovery_context(recovery)

                    # Clean up -- one-time use
                    try:
                        os.remove(COMPACT_RECOVERY_FILE)
                    except OSError:
                        pass
                else:
                    additional = (
                        "Context was just compacted. Check last-session.md "
                        "and session-history.md for continuity."
                    )
            except Exception:
                additional = (
                    "Context was just compacted. Check last-session.md "
                    "and session-history.md for continuity."
                )

        elif source == "startup":
            # Normal startup: find related past sessions
            try:
                from storage import find_related_sessions

                keywords = _extract_keywords_from_last_session()
                if keywords:
                    related = find_related_sessions(keywords, limit=3)
                    if related:
                        parts = ["Related past sessions found:"]
                        for sess in related:
                            sid = sess.session_id[:16] if sess.session_id else "?"
                            working = sess.working_on[:100] if sess.working_on else ""
                            turns = sess.turn_count
                            if working:
                                parts.append(
                                    f"- Session {sid} ({turns} turns): {working}"
                                )
                        if len(parts) > 1:
                            additional = "\n".join(parts)
            except Exception:
                pass

        elif source == "resume":
            additional = (
                "This is a resumed session. Check last-session.md for "
                "continuity state."
            )

        output = {
            "continue": True,
            "suppressOutput": True,
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "action": "context_injection",
                "additionalContext": additional,
                "files_updated": [
                    "last-session.md",
                    "session-history.md",
                    "session-status.md",
                ],
            },
        }
        print(json.dumps(output))
        sys.exit(0)

    except Exception as e:
        error_output = {
            "continue": True,
            "suppressOutput": True,
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "error": str(e),
            },
        }
        print(json.dumps(error_output))
        sys.exit(0)  # Never block session start


if __name__ == "__main__":
    main()
