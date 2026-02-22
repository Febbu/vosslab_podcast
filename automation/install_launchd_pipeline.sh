#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LABEL="com.vosslab.podcast.pipeline"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$LAUNCH_AGENTS_DIR/$LABEL.plist"
RUN_SCRIPT="$REPO_ROOT/automation/run_local_pipeline.sh"
STDOUT_LOG="$REPO_ROOT/out/launchd_pipeline.log"
STDERR_LOG="$REPO_ROOT/out/launchd_pipeline.error.log"
GUI_DOMAIN="gui/$(id -u)"

mkdir -p "$LAUNCH_AGENTS_DIR"
mkdir -p "$REPO_ROOT/out"

if [[ ! -x "$RUN_SCRIPT" ]]; then
	echo "Missing executable run script: $RUN_SCRIPT"
	exit 1
fi

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
		<string>cd "$REPO_ROOT" && "$RUN_SCRIPT"</string>
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

launchctl bootout "$GUI_DOMAIN" "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl bootstrap "$GUI_DOMAIN" "$PLIST_PATH"
launchctl enable "$GUI_DOMAIN/$LABEL"

echo "Installed launchd job: $LABEL"
echo "Plist: $PLIST_PATH"
echo "Schedule: every Monday at 09:00 local time"
echo "Logs: $STDOUT_LOG and $STDERR_LOG"
