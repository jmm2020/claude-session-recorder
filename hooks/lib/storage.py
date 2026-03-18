"""JSON file storage backend for session history.

Stores session data as individual JSON files in ~/.claude/session-recorder/sessions/.
No external dependencies — pure stdlib.
"""
from __future__ import annotations

import functools
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from models import RecorderConfig, SessionRecord

# Default config values
_DEFAULTS: Dict[str, Any] = {
    "max_sessions": 20,
    "max_decisions": 5,
    "max_files_shown": 10,
    "related_sessions_limit": 3,
    "verbose_logging": False,
}


def _storage_dir() -> Path:
    """Return the sessions storage directory, creating it if needed."""
    d = Path.home() / ".claude" / "session-recorder" / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


@functools.lru_cache(maxsize=1)
def _load_config_cached() -> RecorderConfig:
    """Load config.json with defaults for missing keys (cached).

    Searches for config.json next to this file (inside the installed hooks),
    then falls back to the repo root config.json.
    """
    config = dict(_DEFAULTS)

    # Look for config.json — plugin root, legacy hooks dir, or relative to this file
    candidates: list[Path] = []
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        candidates.append(Path(plugin_root) / "config.json")
    candidates.extend([
        Path.home() / ".claude" / "hooks" / "session-recorder" / "config.json",
        Path(__file__).resolve().parent.parent.parent / "config.json",
    ])

    for candidate in candidates:
        try:
            if candidate.exists():
                with candidate.open("r") as f:
                    user_config = json.load(f)
                config.update(user_config)
                break
        except (ValueError, IOError, OSError):
            pass

    return RecorderConfig.from_dict(config)


def load_config() -> RecorderConfig:
    """Load config.json with defaults for missing keys.

    Uses lru_cache internally so the file is only read once per process.
    """
    return _load_config_cached()


def save_session(data: SessionRecord) -> None:
    """Save a session record as a timestamped JSON file.

    Prunes old sessions beyond max_sessions.

    Args:
        data: SessionRecord with session_id, timestamp, turn_count, etc.
    """
    config = load_config()
    sessions_dir = _storage_dir()

    session_id = data.session_id or "unknown"
    ts = data.timestamp or datetime.now().isoformat()

    # Filename: timestamp_sessionid.json (sortable)
    safe_ts = ts.replace(":", "-").replace(" ", "T")[:19]
    safe_id = session_id[:20].replace("/", "_")
    filename = f"{safe_ts}_{safe_id}.json"

    filepath = sessions_dir / filename
    try:
        with filepath.open("w") as f:
            json.dump(data.to_dict(), f, indent=2, default=str)
    except (IOError, OSError) as e:
        print(f"Failed to save session: {e}", file=sys.stderr)
        return

    # Prune old sessions
    _prune_sessions(sessions_dir, config.max_sessions)


def _prune_sessions(sessions_dir: Path, max_sessions: int) -> None:
    """Remove oldest session files if we exceed max_sessions."""
    try:
        files = sorted(sessions_dir.glob("*.json"))
        while len(files) > max_sessions:
            oldest = files.pop(0)
            try:
                oldest.unlink()
            except (IOError, OSError):
                pass
    except (IOError, OSError):
        pass


def load_sessions(limit: int = 10) -> List[SessionRecord]:
    """Load the N most recent session files, newest first.

    Returns list of SessionRecord dataclasses.
    """
    sessions_dir = _storage_dir()
    try:
        files = sorted(sessions_dir.glob("*.json"), reverse=True)
    except (IOError, OSError):
        return []

    results: list[SessionRecord] = []
    for fp in files[:limit]:
        try:
            with fp.open("r") as f:
                data = json.load(f)
            results.append(SessionRecord.from_dict(data))
        except (ValueError, IOError, OSError):
            pass

    return results


def find_related_sessions(keywords: List[str], limit: int = 3) -> List[SessionRecord]:
    """Find past sessions matching any of the given keywords.

    Simple case-insensitive substring matching across working_on,
    topics, decisions, and files_modified fields.

    Args:
        keywords: list of keyword strings to match
        limit: max sessions to return

    Returns list of matching SessionRecord dataclasses, sorted by relevance.
    """
    if not keywords:
        return []

    # Normalize keywords to lowercase
    keywords_lower = [k.lower() for k in keywords if k and len(k) > 2]
    if not keywords_lower:
        return []

    all_sessions = load_sessions(limit=50)  # Search across a wider window
    scored: list[tuple[int, SessionRecord]] = []

    for session in all_sessions:
        # Build a searchable text blob from all relevant fields
        parts = [
            session.working_on,
            session.last_user_request,
            session.topics[0] if session.topics else "",
        ]
        for t in session.topics:
            parts.append(t)
        for d in session.decisions:
            parts.append(d)
        for fp in session.files_modified:
            parts.append(fp)

        blob = " ".join(parts).lower()
        if not blob:
            continue

        # Score: count how many keywords match
        score = 0
        for kw in keywords_lower:
            if kw in blob:
                score += 1

        if score > 0:
            scored.append((score, session))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s[1] for s in scored[:limit]]
