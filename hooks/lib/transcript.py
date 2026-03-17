"""Transcript parsing utilities for session continuity hooks.

Extracts structured task state from Claude Code session transcripts (JSONL).
Pure stdlib — no external dependencies.
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Optional

from models import TranscriptState


def parse_transcript(transcript_path: Optional[str], max_user_msgs: int = 15) -> TranscriptState:
    """Parse a Claude Code transcript JSONL into structured session state.

    Returns a TranscriptState dataclass with turn_count, messages, files,
    tools, topics, decisions, and task summary.
    """
    result = TranscriptState()

    if not transcript_path or not os.path.exists(transcript_path):
        return result

    try:
        user_msgs: list[str] = []
        assistant_msgs: list[str] = []
        files_modified: set[str] = set()
        tools_used: set[str] = set()

        with open(transcript_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except (ValueError, KeyError):
                    continue

                result.message_count += 1
                entry_type = entry.get("type", "")

                if entry_type == "user":
                    msg = entry.get("message", {})
                    content = msg.get("content", "")
                    if isinstance(content, str) and content.strip():
                        clean = content.strip()
                        if (not clean.startswith("<system-reminder>")
                                and not clean.startswith("<local-command")
                                and not clean.startswith("<command-")
                                and not clean.startswith("<task-notification")):
                            user_msgs.append(clean)
                    elif isinstance(content, list):
                        has_tool_result = False
                        for b in content:
                            if isinstance(b, dict) and b.get("type") == "tool_result":
                                has_tool_result = True
                                break
                        if not has_tool_result:
                            text_parts = []
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    text_parts.append(block.get("text", ""))
                            text = " ".join(text_parts).strip()
                            if text and not text.startswith("<system-reminder>"):
                                user_msgs.append(text)

                elif entry_type == "assistant":
                    msg = entry.get("message", {})
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        text_parts = []
                        for block in content:
                            if isinstance(block, dict):
                                if block.get("type") == "text":
                                    text_parts.append(block.get("text", ""))
                                elif block.get("type") == "tool_use":
                                    tool_name = block.get("name", "")
                                    tools_used.add(tool_name)
                                    inp = block.get("input", {})
                                    if tool_name in ("Edit", "Write"):
                                        fp = inp.get("file_path", "")
                                        if fp:
                                            files_modified.add(fp)
                                    elif tool_name == "Bash":
                                        cmd = inp.get("command", "")
                                        if cmd:
                                            first_word = cmd.split()[0] if cmd.split() else ""
                                            tools_used.add(f"Bash({first_word})")
                        text = " ".join(text_parts).strip()
                        if text:
                            assistant_msgs.append(text)
                    elif isinstance(content, str) and content.strip():
                        assistant_msgs.append(content.strip())

        all_assistant_msgs = assistant_msgs
        actual_turn_count = len(user_msgs)
        user_msgs = user_msgs[-max_user_msgs:]
        assistant_msgs = assistant_msgs[-max_user_msgs:]

        result.turn_count = actual_turn_count
        result.user_messages = user_msgs
        result.assistant_messages = assistant_msgs
        result.files_modified = sorted(files_modified)
        result.tools_used = sorted(tools_used)

        if user_msgs:
            result.last_user_request = user_msgs[-1][:500]

        if assistant_msgs:
            result.last_assistant_response = assistant_msgs[-1][:1500]

        # Extract topics from user messages
        topics: list[str] = []
        for msg in user_msgs[-5:]:
            topic = msg.split("\n")[0][:150]
            if topic and len(topic) > 5:
                topics.append(topic)
        result.topics = topics

        # Extract decisions from assistant messages
        decisions: list[str] = []
        decision_re = re.compile(
            r'(?:fixed|changed|updated|switched|corrected|deployed|built|'
            r'created|implemented|verified|configured|renamed|added|removed|'
            r'refactored|migrated|resolved|installed|enabled|disabled)'
            r'[^.!?\n]{10,150}',
            re.IGNORECASE,
        )
        for msg in all_assistant_msgs[-50:]:
            for match in decision_re.finditer(msg):
                text = match.group().strip()
                text = text.replace("**", "").replace("`", "").strip()
                text_lower = text.lower()
                if text_lower.startswith(("fixed**:", "created_during")):
                    continue
                if '"' in text or "'" in text[:20]:
                    continue
                # Require specificity: path, arrow, or technical term
                has_specifics = bool(re.search(
                    r'->|\.py|\.js|\.ts|\.yml|\.md|\.json|\.sh|\.css|\.html|'
                    r'port \d|docker|config|hook|api|endpoint|function|class|'
                    r'module|package|component|route|query|schema|table|column',
                    text_lower,
                ))
                if not has_specifics:
                    continue
                if 20 < len(text) < 200:
                    decisions.append(text[0].upper() + text[1:])

        seen: set[str] = set()
        unique: list[str] = []
        for d in decisions:
            key = d[:40].lower()
            if key not in seen:
                seen.add(key)
                unique.append(d)
        result.decisions = unique[-5:]

        # Build task summary
        task_stopwords = {
            "yes", "ok", "lets", "let's", "keep", "start", "continue",
            "sure", "thanks", "thank", "good", "great", "nice",
        }
        task_topic = ""
        for msg in reversed(user_msgs):
            first_line = msg.split("\n")[0].strip()
            first_lower = first_line.lower()
            if not any(first_lower.startswith(w) for w in task_stopwords) and len(first_line) > 15:
                cut = min(len(first_line), 120)
                for sep in ("???", "?", "...", ". "):
                    idx = first_line.find(sep, 20)
                    if 0 < idx < cut:
                        cut = idx + len(sep)
                        break
                task_topic = first_line[:cut].strip()
                break
        if not task_topic and topics:
            task_topic = topics[-1][:120]

        result.task_summary = task_topic

    except Exception as e:
        print(f"Transcript parse error (non-fatal): {e}", file=sys.stderr)

    return result
