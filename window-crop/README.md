<h1 align="center">Window Crop</h1>
<p align="center">An OBS Studio script that crops a screen capture to the focused window.<br>
Switch the shown window with one key, even while a game has focus.</p>

<p align="center">
  <img src="https://img.shields.io/badge/OBS_Studio-Lua-302e31" alt="OBS Studio Lua">
  <img src="https://img.shields.io/badge/KDE_Plasma-Wayland-1d99f3" alt="KDE Plasma Wayland">
</p>

## Why

On Wayland, OBS captures only one window, picked in a dialog.
OBS shortcuts also stop working while a game has focus.

Window Crop lets you switch the displayed window with a single key, regardless of the app.

## How

A KDE shortcut gets the focused window from KWin.
The script then crops the full screen capture to that window.

The crop slides smoothly to the next window.
Press the shortcut again on the same window to display the full screen.

## Install

Window Crop needs KDE Plasma 6 on Wayland.

 1. Clone using `git clone https://github.com/Hezkore/obs-scripts`
 2. Run `window-crop/install-shortcut.sh` to add the Meta+Shift+C shortcut.
 3. In OBS, open Tools > Scripts, add `window-crop.lua` and pick your screen capture.
 4. Set the screen capture to share the entire screen.

Change the key in System Settings > Keyboard > Shortcuts, under "OBS Window Crop".
