# OBS Twitch Chat to espeak-ng

OBS Python script that connects to Twitch chat, queues incoming messages, and speaks them out loud through `espeak-ng` while updating optional on-screen text and image sources.

## Why
Reading chat during a stream can be tough without a dedicated monitor or moderator. This script provides a lightweight text-to-speech relay so you can listen to highlighted chat messages without leaving OBS.

## How
* Connects to Twitch IRC using your nickname and optional OAuth token
* Watches for messages (optionally gated by a trigger word) and queues them
* Uses `espeak-ng` to speak messages sequentially—never overlapping audio
* Updates selected text/image sources so viewers can see what is being read

## Installation
1. Copy `text-2-espeak.py` into a folder
2. In OBS open **Tools > Scripts** and add the file
3. Fill in your Twitch channel, nickname (optionally create an OAuth token at https://twitchapps.com/tmi/)
4. Choose any text or image sources you want the script to update when a message is read

## Usage
1. Enable the script via the **Enable chat reader** checkbox
2. Optionally set a trigger word to limit which messages get read aloud
3. Adjust speech rate, pitch range, and cooldowns to taste
4. Use the greeting options to welcome new chatters once per configured interval

## Requirements
* OBS Studio with Python scripting support
* `espeak-ng` installed and accessible on your `PATH`

## Limitations
* Twitch IRC rate limits still apply—keep message volume reasonable
* Probably only works on Linux ¯\\_(ツ)_/¯

## Uninstall
Disable the script in **Tools > Scripts** and remove the file; queued data lives only in memory.
