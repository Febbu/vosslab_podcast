#!/usr/bin/env bash
set -euo pipefail

LABEL="com.vosslab.podcast.pipeline"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"
GUI_DOMAIN="gui/$(id -u)"

launchctl bootout "$GUI_DOMAIN" "$PLIST_PATH" >/dev/null 2>&1 || true
rm -f "$PLIST_PATH"

echo "Uninstalled launchd job: $LABEL"
