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
import json
import os
import sys
from datetime import datetime

# Redirect stdout to /dev/null IMMEDIATELY
_real_stderr = sys.stderr
_devnull = open(os.devnull, "w")  # noqa: SIM115 — intentionally kept open for process lifetime
sys.stdout = _devnull

# Add lib directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

COMPACT_RECOVERY_FILE = os.path.join(
    os.environ.get("TMPDIR", "/tmp"),
    "claude_session_memory_recovery.json",
)


def _write_compact_recovery(hook_input, transcript_state):
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
            "working_on": transcript_state.get("task_summary", ""),
            "last_user_request": transcript_state.get("last_user_request", "")[:500],
            "last_assistant_response": transcript_state.get("last_assistant_response", "")[:800],
            "decisions": (transcript_state.get("decisions") or [])[-5:],
            "files_modified": (transcript_state.get("files_modified") or [])[-10:],
            "topics": (transcript_state.get("topics") or [])[-6:],
            "turn_count": transcript_state.get("turn_count", 0),
        }

        with open(COMPACT_RECOVERY_FILE, "w") as f:
            json.dump(recovery, f, indent=2, default=str)

        print(
            "Compact recovery written: working_on=%s, decisions=%d, files=%d" % (
                bool(recovery["working_on"]),
                len(recovery["decisions"]),
                len(recovery["files_modified"]),
            ),
            file=_real_stderr,
        )
    except Exception as e:
        print("Compact recovery write error (non-fatal): %s" % e, file=_real_stderr)


def main():
    try:
        from transcript import parse_transcript
        from context import write_last_session

        # Read hook input from stdin
        hook_input = {}
        if not sys.stdin.isatty():
            try:
                hook_input = json.load(sys.stdin)
            except (ValueError, EOFError):
                pass

        trigger = hook_input.get("trigger", "unknown")
        transcript_path = hook_input.get("transcript_path", "")
        session_id = hook_input.get("session_id", "")

        print("PreCompact fired (trigger=%s)" % trigger, file=_real_stderr)

        # Parse transcript for structured state
        transcript_state = {}
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
        print("PreCompact hook error (non-fatal): %s" % e, file=_real_stderr)


if __name__ == "__main__":
    main()
