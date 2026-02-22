#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LABEL="com.vosslab.podcast.pipeline"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$LAUNCH_AGENTS_DIR/$LABEL.plist"
RUN_SCRIPT="$REPO_ROOT/automation/run_local_pipeline.py"
STDOUT_LOG="$REPO_ROOT/out/launchd_pipeline.log"
STDERR_LOG="$REPO_ROOT/out/launchd_pipeline.error.log"
GUI_DOMAIN="gui/$(id -u)"

log_step() {
	local now_text
	now_text="$(date +"%H:%M:%S")"
	echo "[install_launchd_pipeline ${now_text}] $*"
}

log_step "Installing launchd job from repo root: $REPO_ROOT"

log_step "Ensuring LaunchAgents and output directories exist."
mkdir -p "$LAUNCH_AGENTS_DIR"
mkdir -p "$REPO_ROOT/out"

if [[ ! -x "$RUN_SCRIPT" ]]; then
	log_step "Missing executable run script: $RUN_SCRIPT"
	exit 1
fi

log_step "Writing launchd plist to $PLIST_PATH"
cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key>
	<string>$LABEL</string>
	<key>ProgramArguments</key>
	<array>
		<string>/bin/bash</string>
		<string>-lc</string>
		<string>cd "$REPO_ROOT" && python3 "$RUN_SCRIPT"</string>
	</array>
	<key>RunAtLoad</key>
	<false/>
	<key>StartCalendarInterval</key>
	<dict>
		<key>Weekday</key>
		<integer>1</integer>
		<key>Hour</key>
		<integer>9</integer>
		<key>Minute</key>
		<integer>0</integer>
	</dict>
	<key>WorkingDirectory</key>
	<string>$REPO_ROOT</string>
	<key>StandardOutPath</key>
	<string>$STDOUT_LOG</string>
	<key>StandardErrorPath</key>
	<string>$STDERR_LOG</string>
</dict>
</plist>
EOF

log_step "Reloading launchd job in domain $GUI_DOMAIN"
launchctl bootout "$GUI_DOMAIN" "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl bootstrap "$GUI_DOMAIN" "$PLIST_PATH"
launchctl enable "$GUI_DOMAIN/$LABEL"

log_step "Installed launchd job: $LABEL"
log_step "Plist: $PLIST_PATH"
log_step "Schedule: every Monday at 09:00 local time"
log_step "Logs: $STDOUT_LOG and $STDERR_LOG"
