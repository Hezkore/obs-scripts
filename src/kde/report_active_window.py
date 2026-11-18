#!/usr/bin/env python3
"""Writes the focused window's geometry for the OBS Window Crop script.

KWin only shares window geometry with its own scripts, so this loads a tiny
KWin script that reports the focused window back over D-Bus.
"""

import os
import sys

from gi.repository import Gio, GLib

RESULT_NAME = "obs-window-crop"
REPLY_TIMEOUT_MS = 2000
INTERFACE = "local.ObsWindowCrop"
OBJECT_PATH = "/ObsWindowCrop"
BUS_NAME = f"{INTERFACE}.p{os.getpid()}"
SCRIPT_NAME = f"obs-window-crop-{os.getpid()}"

INTERFACE_XML = f"""
<node>
	<interface name="{INTERFACE}">
		<method name="Report">
			<arg type="s" direction="in"/>
		</method>
	</interface>
</node>
"""

KWIN_SCRIPT = f"""
const window = workspace.activeWindow;
if (window) {{
	const frame = window.frameGeometry;
	const output = window.output.geometry;
	const values = [frame.x, frame.y, frame.width, frame.height, output.x, output.y, output.width, output.height];
	callDBus("{BUS_NAME}", "{OBJECT_PATH}", "{INTERFACE}", "Report", values.join(" "));
}}
"""


def runtime_dir():
	return os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"


def write_atomic(path, text):
	part_path = path + ".part"
	with open(part_path, "w") as file:
		file.write(text)
	os.replace(part_path, path)


def call_kwin(bus, path, interface, method, args):
	return bus.call_sync("org.kde.KWin", path, interface, method, args, None,
		Gio.DBusCallFlags.NONE, REPLY_TIMEOUT_MS, None)


def run_kwin_script(bus, script_path):
	reply = call_kwin(bus, "/Scripting", "org.kde.kwin.Scripting", "loadScript",
		GLib.Variant("(ss)", (script_path, SCRIPT_NAME)))
	script_id = reply.unpack()[0]
	if script_id < 0:
		raise RuntimeError("KWin refused to load the window script")
	call_kwin(bus, f"/Scripting/Script{script_id}", "org.kde.kwin.Script", "run", None)


def unload_kwin_script(bus):
	call_kwin(bus, "/Scripting", "org.kde.kwin.Scripting", "unloadScript",
		GLib.Variant("(s)", (SCRIPT_NAME,)))


def wait_for_report(bus, script_path):
	"""Listens for the KWin script's reply first, then runs the script."""
	loop = GLib.MainLoop()
	result = {}

	def on_call(connection, sender, path, interface, method, parameters, invocation):
		result["geometry"] = parameters.unpack()[0]
		invocation.return_value(None)
		loop.quit()

	def on_timeout():
		loop.quit()
		return GLib.SOURCE_REMOVE

	node = Gio.DBusNodeInfo.new_for_xml(INTERFACE_XML)
	bus.register_object(OBJECT_PATH, node.interfaces[0], on_call)
	bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
		"RequestName", GLib.Variant("(su)", (BUS_NAME, 0)), None,
		Gio.DBusCallFlags.NONE, REPLY_TIMEOUT_MS, None)

	run_kwin_script(bus, script_path)
	GLib.timeout_add(REPLY_TIMEOUT_MS, on_timeout)
	loop.run()
	return result.get("geometry")


def main():
	bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
	script_path = os.path.join(runtime_dir(), SCRIPT_NAME + ".js")
	write_atomic(script_path, KWIN_SCRIPT)
	try:
		geometry = wait_for_report(bus, script_path)
	finally:
		unload_kwin_script(bus)
		os.remove(script_path)

	if geometry is None:
		print("No focused window reported by KWin", file=sys.stderr)
		return 1
	write_atomic(os.path.join(runtime_dir(), RESULT_NAME), geometry)
	return 0


if __name__ == "__main__":
	sys.exit(main())
