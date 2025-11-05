# OBS MPRIS Media Artwork Display

OBS Python script that listens to Linux MPRIS media players, shows the current track text, and updates cover art in your selected sources.

## Why
Audio players, browsers, and streaming apps expose MPRIS metadata, but wiring that information into OBS usually means gluing together separate tools. This script keeps everything inside OBS and automatically keeps your "Now Playing" widgets current.

## How
* Polls available MPRIS players over D-Bus and selects one based on your preference
* Formats the metadata into a customisable text template and pushes it to a text source
* Downloads cover art to a temporary file and feeds it into an image source

## Installation
1. Copy `media-artwork.py` into a folder
2. In OBS go to **Tools > Scripts** and add the file
3. Choose the text and image sources you want to control, set your polling interval, and adjust the format template if desired

## Usage
1. Start playback in any MPRIS-capable player (e.g. Spotify, VLC, Firefox)
2. The script will pick the active player by default; switch preferences in the UI if you want a specific one
3. Tune the transition and polling values
4. Leave sources hidden until playback starts—the script shows them automatically when music is playing

## Requirements
* OBS Studio with Python scripting enabled
* Linux desktop with D-Bus and MPRIS support (most modern players expose it)
* `curl` and `gdbus` binaries available on your `PATH` for artwork downloads and player discovery

## Limitations
* Windows and macOS are not supported because MPRIS is Linux-specific
* Artwork fetching relies on the player providing a reachable URL; some players omit it
* The script only manages one text and one image source at a time

## Uninstall
Remove the script from **Tools > Scripts** and delete any cached artwork files from the temporary directory if needed.
