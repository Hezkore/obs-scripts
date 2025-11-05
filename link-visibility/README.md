# OBS Linked Source Visibility

OBS Python script that mirrors the visibility of a main source onto any number of linked child sources across all scenes.

## Why
Keeping overlays, filters, or subtitles hidden until a main source becomes visible usually requires manually toggling several scene items. This script automates the process so everything follows the main source automatically.

## How
* Choose a **Main Source** and link additional sources from the script UI
* Watches OBS visibility events, including nested scenes
* When the main source is shown or hidden, the linked sources mirror that state (optionally inverted)
* Handles scene switches and cleans up when sources are removed

## Installation
1. Copy `link-visibility.py` into a folder of your choice
2. In OBS visit **Tools > Scripts** and add the file
3. Pick the **Main Source** you want to monitor and link additional sources using the **Link** button

## Usage
1. Add all sources that should follow the main source
2. Toggle the main source in any scene; the linked items will update instantly
3. Use the **Invert visibility** option when you want linked overlays hidden while the main source is visible
4. **Unlink** or **Clear All** when you need to reconfigure the list

## Requirements
* OBS Studio with Python scripting support
* Sources must already exist in obs for the script to list them

## Limitations
* Visibility sync only works for sources that are present in the same scene tree as the main source
* Items that are not added to any scene stay untouched
* Script does not manage source transforms or audio states—visibility only

## Uninstall
Remove the script from **Tools > Scripts**; linked state is stored inside the OBS profile and will no longer be used.
