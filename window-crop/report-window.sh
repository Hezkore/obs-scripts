#!/usr/bin/env bash
# Writes the focused window's geometry for window-crop.lua.
# KWin only shares window geometry with its own scripts, so this runs a tiny
# KWin script that prints the geometry to the log, and reads it back from there.
set -eu

REPLY_TIMEOUT_SECONDS=2
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
REPORT_PATH="$RUNTIME_DIR/obs-window-crop"
TAG="obs-window-crop-$$"
SCRIPT_PATH="$RUNTIME_DIR/$TAG.js"
LOG_PATH="$RUNTIME_DIR/$TAG.fifo"

kwin() {
	timeout "$REPLY_TIMEOUT_SECONDS" gdbus call --session --dest org.kde.KWin "$@"
}

cleanup() {
	if [ -n "${log_pid:-}" ]; then
		kill "$log_pid" 2>/dev/null || true
	fi
	kwin --object-path /Scripting --method org.kde.kwin.Scripting.unloadScript "$TAG" >/dev/null || true
	rm -f "$SCRIPT_PATH" "$LOG_PATH"
}
trap cleanup EXIT

cat > "$SCRIPT_PATH" <<EOF
const window = workspace.activeWindow;
if (window) {
	const content = window.clientGeometry;
	const output = window.output.geometry;
	print(["$TAG", content.x, content.y, content.width, content.height, output.x, output.y, output.width, output.height].join(" "));
}
EOF

script_id=$(kwin --object-path /Scripting --method org.kde.kwin.Scripting.loadScript "$SCRIPT_PATH" "$TAG" | tr -dc '0-9-')
if [ "${script_id:--1}" -lt 0 ]; then
	echo "KWin refused to load the window script" >&2
	exit 1
fi

# Reading on from the log's current end means the print can never be missed
cursor=$(journalctl --user --lines 0 --show-cursor --quiet | sed -n 's/^-- cursor: //p')
kwin --object-path "/Scripting/Script$script_id" --method org.kde.kwin.Script.run >/dev/null

mkfifo "$LOG_PATH"
timeout "$REPLY_TIMEOUT_SECONDS" journalctl --user --follow --output cat --after-cursor "$cursor" _COMM=kwin_wayland > "$LOG_PATH" &
log_pid=$!
exec 3< "$LOG_PATH"

while read -r -t "$REPLY_TIMEOUT_SECONDS" line <&3; do
	case "$line" in
	"$TAG "*)
		printf '%s\n' "${line#"$TAG "}" > "$REPORT_PATH.part"
		mv "$REPORT_PATH.part" "$REPORT_PATH"
		exit 0
		;;
	esac
done

echo "No focused window reported by KWin" >&2
exit 1
