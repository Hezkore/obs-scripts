#!/usr/bin/env python3
"""Adds the desktop shortcut that crops OBS to the focused window."""

import os
import subprocess
import sys

from gi.repository import Gio, GLib

SHORTCUT_NAME = "OBS Window Crop"
DESKTOP_FILE_NAME = "net.local.obs_window_crop.desktop"
LAUNCH_ACTION = "_launch"
REPLY_TIMEOUT_MS = 2000
INDEX_TIMEOUT_SECONDS = 30

# kglobalaccel flags: mark the shortcut as live, and keep our keys over saved ones
SET_PRESENT = 2
NO_AUTOLOADING = 4

# Qt key codes, as KDE stores shortcuts: Meta+Shift+C
QT_META = 0x10000000
QT_SHIFT = 0x02000000
QT_KEY_C = 0x43
SHORTCUT_KEY = QT_META | QT_SHIFT | QT_KEY_C

REPORTER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report_active_window.py")


def write_desktop_file():
	applications_dir = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.join(os.environ["HOME"], ".local/share"), "applications")
	os.makedirs(applications_dir, exist_ok=True)
	with open(os.path.join(applications_dir, DESKTOP_FILE_NAME), "w") as file:
		file.write(
			"[Desktop Entry]\n"
			"Type=Application\n"
			f"Name={SHORTCUT_NAME}\n"
			f"Exec={REPORTER_PATH}\n"
			"NoDisplay=true\n"
			"X-KDE-GlobalAccel-CommandShortcut=true\n")


# KDE only runs a shortcut's command when it knows the app entry at registration
def index_desktop_file():
	subprocess.run(["kbuildsycoca6"], check=True, timeout=INDEX_TIMEOUT_SECONDS,
		stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def call_global_accel(bus, method, args):
	return bus.call_sync("org.kde.kglobalaccel", "/kglobalaccel", "org.kde.KGlobalAccel", method, args, None,
		Gio.DBusCallFlags.NONE, REPLY_TIMEOUT_MS, None)


def bind_shortcut():
	bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
	action_id = [DESKTOP_FILE_NAME, LAUNCH_ACTION, SHORTCUT_NAME, SHORTCUT_NAME]
	call_global_accel(bus, "doRegister", GLib.Variant("(as)", (action_id,)))
	call_global_accel(bus, "setShortcutKeys", GLib.Variant("(asa(ai)u)",
		(action_id, [([SHORTCUT_KEY, 0, 0, 0],)], SET_PRESENT | NO_AUTOLOADING)))


def main():
	write_desktop_file()
	index_desktop_file()
	bind_shortcut()
	print(f"{SHORTCUT_NAME} is on Meta+Shift+C")
	return 0


if __name__ == "__main__":
	sys.exit(main())
