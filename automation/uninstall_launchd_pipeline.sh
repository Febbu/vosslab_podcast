#!/usr/bin/env bash
set -euo pipefail

LABEL="com.vosslab.podcast.pipeline"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"
GUI_DOMAIN="gui/$(id -u)"

log_step() {
	local now_text
	now_text="$(date +"%H:%M:%S")"
	echo "[uninstall_launchd_pipeline ${now_text}] $*"
}

log_step "Removing launchd job: $LABEL"
log_step "Bootout from domain: $GUI_DOMAIN"
launchctl bootout "$GUI_DOMAIN" "$PLIST_PATH" >/dev/null 2>&1 || true
log_step "Removing plist file: $PLIST_PATH"
rm -f "$PLIST_PATH"

log_step "Uninstalled launchd job: $LABEL"
