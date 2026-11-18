#!/usr/bin/env bash
# Adds the KDE shortcut that crops OBS to the focused window.
set -eu

SHORTCUT_NAME="OBS Window Crop"
SHORTCUT_TEXT="Meta+Shift+C"
DESKTOP_FILE_NAME="net.local.obs_window_crop.desktop"
REPLY_TIMEOUT_SECONDS=2
INDEX_TIMEOUT_SECONDS=30

# Qt key codes, as KDE stores shortcuts: Meta + Shift + C
QT_META=0x10000000
QT_SHIFT=0x02000000
QT_KEY_C=0x43
SHORTCUT_KEY=$((QT_META | QT_SHIFT | QT_KEY_C))

# kglobalaccel flags: mark the shortcut as live, and keep these keys over saved ones
SET_PRESENT=2
NO_AUTOLOADING=4

REPORTER_PATH="$(cd "$(dirname "$0")" && pwd)/report-window.sh"
APPLICATIONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

global_accel() {
	timeout "$REPLY_TIMEOUT_SECONDS" gdbus call --session --dest org.kde.kglobalaccel \
		--object-path /kglobalaccel --method "org.kde.KGlobalAccel.$1" "${@:2}" >/dev/null
}

mkdir -p "$APPLICATIONS_DIR"
cat > "$APPLICATIONS_DIR/$DESKTOP_FILE_NAME" <<EOF
[Desktop Entry]
Type=Application
Name=$SHORTCUT_NAME
Exec="$REPORTER_PATH"
NoDisplay=true
X-KDE-GlobalAccel-CommandShortcut=true
EOF

# KDE only runs a shortcut's command when it knows the app entry at registration
timeout "$INDEX_TIMEOUT_SECONDS" kbuildsycoca6 >/dev/null 2>&1

action_id="['$DESKTOP_FILE_NAME', '_launch', '$SHORTCUT_NAME', '$SHORTCUT_NAME']"
global_accel doRegister "$action_id"
global_accel setShortcutKeys "$action_id" "[([$SHORTCUT_KEY, 0, 0, 0],)]" "uint32 $((SET_PRESENT | NO_AUTOLOADING))"

echo "$SHORTCUT_NAME is on $SHORTCUT_TEXT"
