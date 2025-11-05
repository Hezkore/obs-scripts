# OBS Active Window Capture Hotkey

OBS Lua script for Linux / X11 that lets you bind a hotkey to retarget a chosen **Window Capture (Xcomposite)** source to whatever window is currently focused, without using any external tools.

## Why
Manually opening the source properties to pick a different window is slow.\
This script lets you keep one Window Capture source and instantly point it at the active window while streaming or recording with a push of a button.

Useful when:
- Rapidly demoing different apps
- Swapping between editor, terminal, browser, chat etc.

## How
* Registers a single hotkey (**"Change Capture Window"**)
* When pressed, gathers the active window id & title directly via X11 (LuaJIT FFI)
* Updates the source's internal fields (`window`, `capture_window`, `title`, `class`)
* OBS instantly switches the captured content (no scene changes needed)

## Installation
1. Copy `set_window_capture_current.lua` into any folder
2. In OBS: **Tools > Scripts** and click **+** and add the file
3. In the script UI choose your existing **Window Capture (Xcomposite)** source
4. Go to **Settings > Hotkeys** and set a key for **"Change Capture Window"**

## Usage
1. Focus the window you want to capture
2. Press the configured hotkey

The selected source now captures that window.

Toggle "Debug Logging" in the script UI if you want detailed log output (**View > Logs > Script Log**)

## Requirements
* OBS with LuaJIT (standard Linux OBS builds include LuaJIT)
* X11 session or XWayland windows (pure Wayland native windows will not be selectable with Xcomposite)

## Limitations
* Only works with the **Window Capture (Xcomposite)** source type
* Won't capture native Wayland windows, unless they are running under XWayland
* Cannot auto follow focus (by design), manual hotkey press required

## Uninstall
Remove it from **Tools > Scripts**.
