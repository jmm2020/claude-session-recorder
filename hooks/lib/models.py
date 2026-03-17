"""Data models for claude-session-recorder.

Dataclasses for session records, transcript state, and configuration.
Pure stdlib — no external dependencies. Python 3.8+ compatible.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class SessionRecord:
    """A persisted session record stored as JSON."""

    session_id: str = ""
    timestamp: str = ""
    turn_count: int = 0
    working_on: str = ""
    last_user_request: str = ""
    last_assistant_response: str = ""
    decisions: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict."""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SessionRecord:
        """Deserialize from a dict, ignoring unknown keys."""
        known = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


@dataclass
class TranscriptState:
    """Parsed state extracted from a session transcript JSONL."""

    turn_count: int = 0
    user_messages: List[str] = field(default_factory=list)
    assistant_messages: List[str] = field(default_factory=list)
    last_user_request: str = ""
    last_assistant_response: str = ""
    files_modified: List[str] = field(default_factory=list)
    tools_used: List[str] = field(default_factory=list)
    task_summary: str = ""
    topics: List[str] = field(default_factory=list)
    decisions: List[str] = field(default_factory=list)
    message_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict."""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TranscriptState:
        """Deserialize from a dict, ignoring unknown keys."""
        known = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


@dataclass
class RecorderConfig:
    """Configuration for the session recorder."""

    max_sessions: int = 20
    max_decisions: int = 5
    max_files_shown: int = 10
    related_sessions_limit: int = 3
    verbose_logging: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict."""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RecorderConfig:
        """Deserialize from a dict, ignoring unknown keys."""
        known = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)
