#!/usr/bin/env bash
set -euo pipefail

# claude-session-recorder uninstaller

HOOK_DEST="$HOME/.claude/hooks/session-recorder"
CONTEXT_DIR="$HOME/.claude/context"
STORAGE_DIR="$HOME/.claude/session-recorder"
SETTINGS_FILE="$HOME/.claude/settings.json"
RECOVERY_FILE="${TMPDIR:-/tmp}/claude_session_memory_recovery.json"

# Colors
if [ -t 1 ]; then
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    RED='\033[0;31m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    GREEN='' YELLOW='' RED='' BOLD='' NC=''
fi

echo -e "${BOLD}claude-session-recorder uninstaller${NC}"
echo "===================================="
echo ""

# 1. Remove hook entries from settings.json
if [ -f "$SETTINGS_FILE" ]; then
    echo -n "Removing hook entries from settings.json... "

    # Backup first
    cp "$SETTINGS_FILE" "${SETTINGS_FILE}.backup.$(date +%Y%m%d%H%M%S)"

    python3 << 'PYEOF'
import json
import os

settings_file = os.path.expanduser("~/.claude/settings.json")
marker = "session-recorder"

try:
    with open(settings_file, "r") as f:
        settings = json.load(f)
except (ValueError, IOError):
    print("skip")
    exit(0)

hooks = settings.get("hooks", {})
changed = False

for event_name in list(hooks.keys()):
    if isinstance(hooks[event_name], list):
        original_len = len(hooks[event_name])
        hooks[event_name] = [
            h for h in hooks[event_name]
            if not (isinstance(h, dict) and marker in h.get("command", ""))
        ]
        if len(hooks[event_name]) != original_len:
            changed = True
        # Remove empty arrays
        if not hooks[event_name]:
            del hooks[event_name]

if not hooks:
    del settings["hooks"]

if changed:
    with open(settings_file, "w") as f:
        json.dump(settings, f, indent=2)
    print("ok")
else:
    print("no entries found")
PYEOF

    echo -e "${GREEN}done${NC}"
else
    echo "No settings.json found (skipping)"
fi

# 2. Remove hook files
if [ -d "$HOOK_DEST" ]; then
    echo -n "Removing hook files... "
    rm -rf "$HOOK_DEST"
    echo -e "${GREEN}done${NC}"
else
    echo "No hook files found (skipping)"
fi

# 3. Remove recovery file
if [ -f "$RECOVERY_FILE" ]; then
    rm -f "$RECOVERY_FILE"
    echo "Removed temp recovery file"
fi

# 4. Optionally remove session data
echo ""
if [ -d "$STORAGE_DIR" ]; then
    SESSION_COUNT=$(find "$STORAGE_DIR/sessions" -name "*.json" 2>/dev/null | wc -l)
    echo -e "${YELLOW}Found $SESSION_COUNT saved sessions in $STORAGE_DIR${NC}"
    read -p "Remove all session data? This cannot be undone. (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$STORAGE_DIR"
        echo -e "${GREEN}Session data removed${NC}"
    else
        echo "Session data preserved at $STORAGE_DIR"
    fi
fi

# 5. Optionally remove context files
if [ -d "$CONTEXT_DIR" ]; then
    echo ""
    read -p "Remove context files from $CONTEXT_DIR? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -f "$CONTEXT_DIR/last-session.md"
        rm -f "$CONTEXT_DIR/session-history.md"
        rm -f "$CONTEXT_DIR/session-status.md"
        # Only remove dir if empty
        rmdir "$CONTEXT_DIR" 2>/dev/null || true
        echo -e "${GREEN}Context files removed${NC}"
    else
        echo "Context files preserved"
    fi
fi

echo ""
echo -e "${GREEN}${BOLD}Uninstall complete.${NC}"
echo ""
echo "Note: Your settings.json backup is at"
echo "  ${SETTINGS_FILE}.backup.*"
