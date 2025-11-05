# OBS Steam Game Artwork Fetcher

OBS Lua script that pulls background, banner, and logo images for a Steam app and assigns them to your chosen image sources.

## Why
Switching scenes or sources manually to update art for the game you are showcasing breaks the flow. This script grabs the latest Steam artwork on demand so you can refresh overlays with a single button press.

## How
* Looks up the Steam AppID for the title you type into the script UI
* Downloads background, banner, and logo imagery via the official Steam CDN
* Writes each asset to a local cache folder next to the script
* Updates the selected OBS image sources and briefly hides them while art is replaced to avoid flicker

## Installation
1. Copy `game-artwork.lua` into a folder of your choice
2. In OBS go to **Tools > Scripts** and press **+** to add the file
3. Pick your target image sources for background, banner, and logo from the dropdowns

## Usage
1. Enter the game name in the **Game Name** field
2. Click **Fetch Artwork** to download and apply the art
3. Use **Refresh Source Lists** if you add new image sources mid-session
4. Hit **Clear Artwork** to hide all configured artwork sources without removing them from scenes

## Requirements
* OBS Studio with Lua scripting support
* `curl` available on your `PATH`
* Steam artwork must exist for the requested title

## Limitations
* Optimized for Linux/macOS shells; Windows users may need to provide compatible `curl` and `mkdir` utilities
* Only updates OBS image sources; text or media sources are unaffected
* Steam may rate-limit repeated requests if spammed

## Uninstall
Remove the script from **Tools > Scripts** and delete the cached files under `steam_game_art/` if desired.
