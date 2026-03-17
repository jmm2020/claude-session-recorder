#!/usr/bin/env python3
"""Stop hook -- saves session state when Claude Code exits.

CRITICAL: Stop hooks must NEVER print JSON to stdout. Claude Code
parses any stdout starting with '{' as a hook response and validates
it against a strict schema. All output goes to stderr.

This hook:
1. Parses the session transcript for structured state
2. Writes last-session.md (crash recovery for next session)
3. Saves session JSON to persistent storage (session history)
"""
from __future__ import annotations

import atexit
import json
import os
import sys
from datetime import datetime

# Redirect stdout to /dev/null IMMEDIATELY -- before any imports.
# Libraries sometimes print warnings to stdout which breaks Claude Code.
_real_stderr = sys.stderr
_devnull = open(os.devnull, "w")
atexit.register(_devnull.close)
sys.stdout = _devnull

# Add lib directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))


def main() -> None:
    try:
        from transcript import parse_transcript
        from context import write_last_session
        from storage import save_session
        from models import SessionRecord

        # Read hook input from stdin
        hook_input: dict = {}
        if not sys.stdin.isatty():
            try:
                hook_input = json.load(sys.stdin)
            except (ValueError, EOFError):
                pass

        last_message: str = hook_input.get("last_assistant_message", "")
        session_id: str = hook_input.get("session_id", "")
        transcript_path: str = hook_input.get("transcript_path", "")

        # Parse transcript for structured state
        transcript_state = parse_transcript(transcript_path) if transcript_path else None

        if transcript_state is None:
            from models import TranscriptState
            transcript_state = TranscriptState()

        # Write last-session.md (crash recovery)
        write_last_session(
            transcript_state=transcript_state,
            session_id=session_id,
            transcript_path=transcript_path,
            last_message=last_message,
            source="stop hook",
        )

        # Save session to persistent storage
        turn_count = transcript_state.turn_count
        if turn_count >= 1:
            session_data = SessionRecord(
                session_id=session_id,
                timestamp=datetime.now().isoformat(),
                turn_count=turn_count,
                working_on=transcript_state.task_summary,
                last_user_request=transcript_state.last_user_request,
                last_assistant_response=transcript_state.last_assistant_response[:500],
                decisions=transcript_state.decisions,
                files_modified=transcript_state.files_modified,
                topics=transcript_state.topics,
            )
            save_session(session_data)

            files = len(transcript_state.files_modified)
            decisions = len(transcript_state.decisions)
            print(
                f"Session saved ({turn_count} turns, {files} files, {decisions} decisions)",
                file=_real_stderr,
            )
        else:
            print("Session too short to save (< 1 turn)", file=_real_stderr)

    except Exception as e:
        print(f"Stop hook error (non-fatal): {e}", file=_real_stderr)


if __name__ == "__main__":
    main()
