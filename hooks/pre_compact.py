#!/usr/bin/env python3
"""PreCompact hook -- captures session state before context compaction.

CRITICAL: Hooks must NEVER print JSON to stdout. Claude Code parses any
stdout starting with '{' as a hook response. All output goes to stderr.

When compaction fires, this hook:
1. Parses the session transcript for structured state
2. Writes last-session.md (crash recovery)
3. Writes a compact recovery JSON file with rich state
   (this is the handoff to SessionStart for post-compact re-injection)
"""
from __future__ import annotations

import atexit
import json
import os
import sys
from datetime import datetime

# Redirect stdout to /dev/null IMMEDIATELY
_real_stderr = sys.stderr
_devnull = open(os.devnull, "w")
atexit.register(_devnull.close)
sys.stdout = _devnull

# Add lib directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

COMPACT_RECOVERY_FILE: str = os.path.join(
    os.environ.get("TMPDIR", "/tmp"),
    "claude_session_memory_recovery.json",
)


def _write_compact_recovery(hook_input: dict, transcript_state: "TranscriptState") -> None:
    """Write rich recovery state for post-compact SessionStart re-injection.

    This file is the handoff between PreCompact and SessionStart. When
    SessionStart fires with source="compact", it reads this file and builds
    a consciousness re-injection context string.
    """
    try:
        recovery = {
            "timestamp": datetime.now().isoformat(),
            "session_id": hook_input.get("session_id", ""),
            "trigger": hook_input.get("trigger", "auto"),
            "working_on": transcript_state.task_summary,
            "last_user_request": transcript_state.last_user_request[:500],
            "last_assistant_response": transcript_state.last_assistant_response[:800],
            "decisions": (transcript_state.decisions or [])[-5:],
            "files_modified": (transcript_state.files_modified or [])[-10:],
            "topics": (transcript_state.topics or [])[-6:],
            "turn_count": transcript_state.turn_count,
        }

        with open(COMPACT_RECOVERY_FILE, "w") as f:
            json.dump(recovery, f, indent=2, default=str)

        print(
            f"Compact recovery written: working_on={bool(recovery['working_on'])}, "
            f"decisions={len(recovery['decisions'])}, files={len(recovery['files_modified'])}",
            file=_real_stderr,
        )
    except Exception as e:
        print(f"Compact recovery write error (non-fatal): {e}", file=_real_stderr)


def main() -> None:
    try:
        from transcript import parse_transcript
        from context import write_last_session
        from models import TranscriptState

        # Read hook input from stdin
        hook_input: dict = {}
        if not sys.stdin.isatty():
            try:
                hook_input = json.load(sys.stdin)
            except (ValueError, EOFError):
                pass

        trigger: str = hook_input.get("trigger", "unknown")
        transcript_path: str = hook_input.get("transcript_path", "")
        session_id: str = hook_input.get("session_id", "")

        print(f"PreCompact fired (trigger={trigger})", file=_real_stderr)

        # Parse transcript for structured state
        transcript_state = TranscriptState()
        if transcript_path:
            transcript_state = parse_transcript(transcript_path)

        # Write last-session.md (crash recovery)
        write_last_session(
            transcript_state=transcript_state,
            session_id=session_id,
            transcript_path=transcript_path,
            source="pre-compact hook",
        )
        print("last-session.md written (pre-compact)", file=_real_stderr)

        # Write compact recovery state for post-compact SessionStart injection
        _write_compact_recovery(hook_input, transcript_state)

    except Exception as e:
        print(f"PreCompact hook error (non-fatal): {e}", file=_real_stderr)


if __name__ == "__main__":
    main()
