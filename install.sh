#!/usr/bin/env bash
set -euo pipefail

# claude-session-recorder installer
# Installs session continuity hooks for Claude Code

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK_DEST="$HOME/.claude/hooks/session-recorder"
CONTEXT_DIR="$HOME/.claude/context"
STORAGE_DIR="$HOME/.claude/session-recorder/sessions"
SETTINGS_FILE="$HOME/.claude/settings.json"

# Colors (if terminal supports it)
if [ -t 1 ]; then
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    RED='\033[0;31m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    GREEN='' YELLOW='' RED='' BOLD='' NC=''
fi

echo -e "${BOLD}claude-session-recorder installer${NC}"
echo "=================================="
echo ""

# 1. Check Python 3.8+
echo -n "Checking Python... "
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}FAILED${NC}"
    echo "Error: python3 is required but not found."
    echo "Install Python 3.8+ and try again."
    exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(sys.version_info.major * 100 + sys.version_info.minor)')
if [ "$PY_VERSION" -lt 308 ]; then
    echo -e "${RED}FAILED${NC}"
    echo "Error: Python 3.8+ is required (found $(python3 --version))"
    exit 1
fi
echo -e "${GREEN}$(python3 --version)${NC}"

# 2. Check if already installed
if [ -d "$HOOK_DEST" ]; then
    echo -e "${YELLOW}Previous installation detected at $HOOK_DEST${NC}"
    read -p "Overwrite existing installation? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
fi

# 3. Create directories
echo -n "Creating directories... "
mkdir -p "$HOOK_DEST/lib"
mkdir -p "$CONTEXT_DIR"
mkdir -p "$STORAGE_DIR"
echo -e "${GREEN}done${NC}"

# 4. Copy hook files
echo -n "Installing hooks... "
cp "$SCRIPT_DIR/hooks/session_start.py" "$HOOK_DEST/session_start.py"
cp "$SCRIPT_DIR/hooks/stop.py" "$HOOK_DEST/stop.py"
cp "$SCRIPT_DIR/hooks/pre_compact.py" "$HOOK_DEST/pre_compact.py"
cp "$SCRIPT_DIR/hooks/lib/__init__.py" "$HOOK_DEST/lib/__init__.py"
cp "$SCRIPT_DIR/hooks/lib/transcript.py" "$HOOK_DEST/lib/transcript.py"
cp "$SCRIPT_DIR/hooks/lib/storage.py" "$HOOK_DEST/lib/storage.py"
cp "$SCRIPT_DIR/hooks/lib/context.py" "$HOOK_DEST/lib/context.py"
cp "$SCRIPT_DIR/config.json" "$HOOK_DEST/config.json"
echo -e "${GREEN}done${NC}"

# 5. Validate imports work
echo -n "Validating imports... "
if python3 -c "
import sys
sys.path.insert(0, '$HOOK_DEST/lib')
from transcript import parse_transcript
from storage import load_config, save_session, load_sessions
from context import write_last_session, write_session_history, write_status
print('ok')
" 2>/dev/null | grep -q "ok"; then
    echo -e "${GREEN}passed${NC}"
else
    echo -e "${RED}FAILED${NC}"
    echo "Error: Hook imports failed. Check Python installation."
    exit 1
fi

# 6. Update settings.json (merge hook entries)
echo -n "Configuring Claude Code hooks... "

# Backup existing settings
if [ -f "$SETTINGS_FILE" ]; then
    cp "$SETTINGS_FILE" "${SETTINGS_FILE}.backup.$(date +%Y%m%d%H%M%S)"
fi

# Use Python to safely merge JSON (handles existing hooks, edge cases)
python3 << 'PYEOF'
import json
import os
import sys

settings_file = os.path.expanduser("~/.claude/settings.json")
hook_dest = os.path.expanduser("~/.claude/hooks/session-recorder")

# Load existing settings or create new
settings = {}
if os.path.exists(settings_file):
    try:
        with open(settings_file, "r") as f:
            settings = json.load(f)
    except (ValueError, IOError):
        settings = {}

# Ensure hooks section exists
if "hooks" not in settings:
    settings["hooks"] = {}

hooks = settings["hooks"]

# Hook definitions to add
new_hooks = {
    "SessionStart": {
        "type": "command",
        "command": "python3 %s/session_start.py" % hook_dest,
    },
    "Stop": {
        "type": "command",
        "command": "python3 %s/stop.py" % hook_dest,
    },
    "PreCompact": {
        "type": "command",
        "command": "python3 %s/pre_compact.py" % hook_dest,
    },
}

marker = "session-recorder"

for event_name, hook_def in new_hooks.items():
    if event_name not in hooks:
        hooks[event_name] = []

    # Check if we already have a session-recorder hook for this event
    existing_idx = None
    for i, h in enumerate(hooks[event_name]):
        if isinstance(h, dict) and marker in h.get("command", ""):
            existing_idx = i
            break

    if existing_idx is not None:
        # Update existing entry
        hooks[event_name][existing_idx] = hook_def
    else:
        # Append new entry (never overwrite other hooks)
        hooks[event_name].append(hook_def)

# Write back
os.makedirs(os.path.dirname(settings_file), exist_ok=True)
with open(settings_file, "w") as f:
    json.dump(settings, f, indent=2)

print("ok")
PYEOF

if [ $? -eq 0 ]; then
    echo -e "${GREEN}done${NC}"
else
    echo -e "${RED}FAILED${NC}"
    echo "Error: Could not update settings.json"
    exit 1
fi

# 7. Optionally add context references to CLAUDE.md
echo ""
echo "Session Recorder writes context files to ~/.claude/context/"
echo "You can reference them in your CLAUDE.md for automatic loading:"
echo ""
echo "  @~/.claude/context/last-session.md"
echo "  @~/.claude/context/session-history.md"
echo ""
read -p "Add these references to your project's CLAUDE.md? (y/N) " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Find CLAUDE.md in common locations
    CLAUDE_MD=""
    if [ -f "./CLAUDE.md" ]; then
        CLAUDE_MD="./CLAUDE.md"
    elif [ -f "$HOME/CLAUDE.md" ]; then
        CLAUDE_MD="$HOME/CLAUDE.md"
    fi

    if [ -n "$CLAUDE_MD" ]; then
        # Check if already present
        if grep -q "~/.claude/context/last-session.md" "$CLAUDE_MD" 2>/dev/null; then
            echo "References already present in $CLAUDE_MD"
        else
            echo "" >> "$CLAUDE_MD"
            echo "# Session Context (auto-injected by claude-session-recorder)" >> "$CLAUDE_MD"
            echo "@~/.claude/context/last-session.md" >> "$CLAUDE_MD"
            echo "@~/.claude/context/session-history.md" >> "$CLAUDE_MD"
            echo -e "${GREEN}Added to $CLAUDE_MD${NC}"
        fi
    else
        echo -e "${YELLOW}No CLAUDE.md found in current directory or home.${NC}"
        echo "Add these lines manually to your CLAUDE.md:"
        echo "  @~/.claude/context/last-session.md"
        echo "  @~/.claude/context/session-history.md"
    fi
fi

# 8. Done!
echo ""
echo -e "${GREEN}${BOLD}Installation complete!${NC}"
echo ""
echo "What happens now:"
echo "  1. Start Claude Code and work normally"
echo "  2. When you exit, the stop hook saves your session"
echo "  3. Next time you start Claude Code, the session_start hook"
echo "     loads your last session context automatically"
echo "  4. If context compacts, pre_compact captures your state and"
echo "     session_start re-injects it — no context loss"
echo ""
echo "Files installed:"
echo "  Hooks:   $HOOK_DEST/"
echo "  Context: $CONTEXT_DIR/"
echo "  Storage: $STORAGE_DIR/"
echo "  Config:  $SETTINGS_FILE"
echo ""
echo "To uninstall: bash $(dirname "$0")/uninstall.sh"
