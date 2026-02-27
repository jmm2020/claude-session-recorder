"""JSON file storage backend for session history.

Stores session data as individual JSON files in ~/.claude/session-recorder/sessions/.
No external dependencies — pure stdlib.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Default config values
_DEFAULTS = {
    "max_sessions": 20,
    "max_decisions": 5,
    "max_files_shown": 10,
    "related_sessions_limit": 3,
    "verbose_logging": False,
}

_config_cache = None


def _storage_dir():
    """Return the sessions storage directory, creating it if needed."""
    d = Path.home() / ".claude" / "session-recorder" / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_config():
    """Load config.json with defaults for missing keys.

    Searches for config.json next to this file (inside the installed hooks),
    then falls back to the repo root config.json.
    """
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    config = dict(_DEFAULTS)

    # Look for config.json in the installed hooks dir
    candidates = [
        Path.home() / ".claude" / "hooks" / "session-recorder" / "config.json",
        Path(__file__).resolve().parent.parent.parent / "config.json",
    ]

    for candidate in candidates:
        try:
            if candidate.exists():
                with candidate.open("r") as f:
                    user_config = json.load(f)
                config.update(user_config)
                break
        except (ValueError, IOError, OSError):
            pass

    _config_cache = config
    return config


def save_session(data):
    """Save a session record as a timestamped JSON file.

    Prunes old sessions beyond max_sessions.

    Args:
        data: dict with session_id, timestamp, turn_count, working_on, etc.
    """
    config = load_config()
    sessions_dir = _storage_dir()

    session_id = data.get("session_id", "unknown")
    ts = data.get("timestamp", datetime.now().isoformat())

    # Filename: timestamp_sessionid.json (sortable)
    safe_ts = ts.replace(":", "-").replace(" ", "T")[:19]
    safe_id = session_id[:20].replace("/", "_")
    filename = "%s_%s.json" % (safe_ts, safe_id)

    filepath = sessions_dir / filename
    try:
        with filepath.open("w") as f:
            json.dump(data, f, indent=2, default=str)
    except (IOError, OSError) as e:
        print("Failed to save session: %s" % e, file=sys.stderr)
        return

    # Prune old sessions
    _prune_sessions(sessions_dir, config.get("max_sessions", 20))


def _prune_sessions(sessions_dir, max_sessions):
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


def load_sessions(limit=10):
    """Load the N most recent session files, newest first.

    Returns list of dicts.
    """
    sessions_dir = _storage_dir()
    try:
        files = sorted(sessions_dir.glob("*.json"), reverse=True)
    except (IOError, OSError):
        return []

    results = []
    for fp in files[:limit]:
        try:
            with fp.open("r") as f:
                data = json.load(f)
            results.append(data)
        except (ValueError, IOError, OSError):
            pass

    return results


def find_related_sessions(keywords, limit=3):
    """Find past sessions matching any of the given keywords.

    Simple case-insensitive substring matching across working_on,
    topics, decisions, and files_modified fields.

    Args:
        keywords: list of keyword strings to match
        limit: max sessions to return

    Returns list of matching session dicts, sorted by recency.
    """
    if not keywords:
        return []

    # Normalize keywords to lowercase
    keywords_lower = [k.lower() for k in keywords if k and len(k) > 2]
    if not keywords_lower:
        return []

    all_sessions = load_sessions(limit=50)  # Search across a wider window
    scored = []

    for session in all_sessions:
        # Build a searchable text blob from all relevant fields
        parts = [
            session.get("working_on", ""),
            session.get("last_user_request", ""),
            session.get("task_summary", ""),
        ]
        for t in session.get("topics", []):
            parts.append(t)
        for d in session.get("decisions", []):
            parts.append(d)
        for fp in session.get("files_modified", []):
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

    # Sort by score descending, then by timestamp descending
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s[1] for s in scored[:limit]]
