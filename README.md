# claude-session-recorder

Give Claude Code a memory that persists across sessions and survives context compaction.

**claude-session-recorder** is a lightweight plugin that automatically saves your session state when you exit Claude Code and re-injects it when you start a new session. No database, no Docker, no API keys — just Python 3.8+ and three hook scripts.

## Install

### Plugin (Recommended — Claude Code 1.0.33+)

```bash
/plugin install session-recorder@claude-plugins-official
```

Or load from a local directory:

```bash
claude --plugin-dir /path/to/claude-session-recorder
```

### Manual (Legacy — Claude Code 2.1.0+)

```bash
git clone https://github.com/jmm2020/claude-session-recorder.git
cd claude-session-recorder
bash install.sh
```

## How It Works

Three hooks run at key moments in the Claude Code lifecycle:

### 1. Stop Hook (`stop.py`)
When you exit Claude Code, this hook:
- Parses your session transcript (the JSONL file Claude Code writes)
- Extracts what you were working on, decisions made, files modified, and topics discussed
- Writes `~/.claude/context/last-session.md` (crash recovery)
- Saves a structured JSON record to `~/.claude/session-recorder/sessions/`

### 2. PreCompact Hook (`pre_compact.py`)
When Claude Code compacts your context (the moment where most tools lose everything), this hook:
- Captures your full session state before the compaction wipes it
- Writes a recovery JSON file to `/tmp/claude_session_memory_recovery.json`
- This is the key innovation — **your state survives context compaction**

### 3. SessionStart Hook (`session_start.py`)
When you start Claude Code, this hook:
- Loads your session history and writes `session-history.md` and `session-status.md`
- If recovering from compaction: reads the recovery JSON and re-injects your full state
- On normal startup: finds related past sessions via keyword matching
- Outputs `additionalContext` so Claude sees your session state immediately

## What Gets Saved

Each session record captures:

```json
{
  "session_id": "abc123",
  "timestamp": "2026-02-27T17:10:04",
  "turn_count": 15,
  "working_on": "Implementing session continuity hooks",
  "last_user_request": "commit this",
  "last_assistant_response": "I've committed the changes...",
  "decisions": ["Fixed timeout from 5s to 15s"],
  "files_modified": ["hooks/stop.py"],
  "topics": ["session continuity", "compact recovery"]
}
```

## Context Files

The hooks write three context files to `~/.claude/context/`:

| File | Purpose |
|------|---------|
| `last-session.md` | What you were doing in your last session (working on, decisions, files) |
| `session-history.md` | Summary of your recent sessions (last 10) |
| `session-status.md` | Recorder health (sessions stored, storage used) |

To have Claude automatically read these, add to your `CLAUDE.md`:

```
@~/.claude/context/last-session.md
@~/.claude/context/session-history.md
```

## Configuration

Edit `config.json` in the plugin root (or `~/.claude/hooks/session-recorder/config.json` for legacy installs):

```json
{
  "max_sessions": 20,
  "max_decisions": 5,
  "max_files_shown": 10,
  "related_sessions_limit": 3,
  "verbose_logging": false
}
```

| Setting | Default | Description |
|---------|---------|-------------|
| `max_sessions` | 20 | Maximum session files to keep (oldest pruned automatically) |
| `max_decisions` | 5 | Max decisions extracted per session |
| `max_files_shown` | 10 | Max modified files listed in context |
| `related_sessions_limit` | 3 | Max related sessions returned on startup |
| `verbose_logging` | false | Extra debug output to stderr |

## Requirements

- **Python 3.8+** (uses only stdlib — zero pip dependencies)
- **Claude Code 1.0.33+** (plugin install) or **2.1.0+** (manual install)
- **Linux or macOS** (Windows WSL should work but is untested)

## Uninstall

### Plugin

```
/plugin uninstall session-recorder@claude-plugins-official
```

### Manual

```bash
bash uninstall.sh
```

## Architecture

```
Session Exit                          Next Session Start
    |                                       |
    v                                       v
[stop.py]                            [session_start.py]
    |                                       |
    +-- parse transcript                    +-- load session history
    +-- write last-session.md               +-- write session-history.md
    +-- save session JSON                   +-- write session-status.md
                                            +-- find related sessions
                                            +-- inject additionalContext

Context Compaction
    |
    v
[pre_compact.py]                     [session_start.py (source="compact")]
    |                                       |
    +-- parse transcript                    +-- read recovery JSON
    +-- write last-session.md               +-- build rich context
    +-- write recovery JSON  ------------>  +-- delete recovery file
                                            +-- inject additionalContext
```

## How Decision Extraction Works

The transcript parser uses regex to find phrases like "Fixed the timeout", "Changed port to 8080", "Created new endpoint", etc. It filters for technical specificity (must mention file paths, ports, config terms) and deduplicates. This captures the *reasoning* behind changes, not just what files were touched.

## Plugin Structure

```
claude-session-recorder/
├── .claude-plugin/
│   └── plugin.json           # Plugin manifest
├── hooks/
│   ├── hooks.json            # Event bindings (SessionStart, Stop, PreCompact)
│   ├── session_start.py      # Injects context on startup/post-compact
│   ├── stop.py               # Saves state on exit
│   ├── pre_compact.py        # Captures state before compaction
│   └── lib/
│       ├── __init__.py
│       ├── transcript.py     # JSONL transcript parser
│       ├── storage.py        # JSON file storage backend
│       └── context.py        # Markdown context file generator
├── config.json               # User-configurable settings
├── install.sh                # Legacy manual installer
├── uninstall.sh              # Legacy manual uninstaller
├── LICENSE                   # MIT
└── README.md
```

## Comparison

| Feature | session-recorder | Default Claude Code |
|---------|-----------------|-------------------|
| Session state on restart | Full context (working on, decisions, files) | None |
| Post-compact recovery | Rich state re-injection | Brief system summary |
| Session history | Last 20 sessions with search | None |
| Related session discovery | Keyword matching across history | None |
| Dependencies | Python 3.8+ stdlib only | N/A |
| Setup time | One command | N/A |

## License

MIT
