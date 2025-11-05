"""
Hezkore's Twitch Chat to espeak-ng Bridge

See README.md for connection and safety recommendations.
"""

import hashlib
import obspython as obs
import queue
import socket
import subprocess
import threading
import time
from typing import NamedTuple, Optional

SCRIPT_VERSION = "1.0.0"

TWITCH_SERVER = "irc.chat.twitch.tv"
TWITCH_PORT = 6667

DEFAULT_PITCH_MIN = 25
DEFAULT_PITCH_MAX = 99

TEXT_SOURCE_IDS = {
    "text_gdiplus",
    "text_gdiplus_v2",
    "text_ft2_source",
    "text_ft2_source_v2",
    "text_pango_source",
}

IMAGE_SOURCE_IDS = {
    "image_source",
    "slideshow",
}


class QueuedMessage(NamedTuple):
    speak_text: str
    pitch_value: int
    display_text: str

# Global Settings Managed Through The OBS UI
oauth_token: str = ""
nickname: str = "justinfan12345"
channel: str = "your_username"
trigger_word: str = ""
speech_rate: int = 150
speak_interval: float = 2.0
include_username: bool = False
max_tts_length: int = 280
enabled: bool = False
pitch_min: int = DEFAULT_PITCH_MIN
pitch_max: int = DEFAULT_PITCH_MAX
text_source_name: str = ""
image_source_name: str = ""
per_user_timeout: float = 0.5
greet_users: bool = False
greet_message: str = "Welcome {name}"
greet_timeout_minutes: float = 10.0

_CONFIG_PROPERTY_NAMES = (
    "channel",
    "nickname",
    "trigger_word",
    "oauth_token",
    "speech_rate",
    "speak_interval",
    "per_user_timeout",
    "greet_users",
    "greet_message",
    "greet_timeout_minutes",
    "include_username",
    "max_tts_length",
    "pitch_min",
    "pitch_max",
    "text_source_name",
    "image_source_name",
)

# Runtime State
_message_queue: "queue.Queue[QueuedMessage]" = queue.Queue(maxsize=256)
_chat_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_chat_socket: Optional[socket.socket] = None
_tts_thread: Optional[threading.Thread] = None
_last_speech_time: float = 0.0
_current_config: Optional[dict] = None
_pending_config: Optional[dict] = None
_pending_apply_time: float = 0.0
_pending_force: bool = False
_display_visible: bool = False
_user_last_trigger: dict[str, float] = {}
_user_last_greet: dict[str, float] = {}


def script_description() -> str:
    return (
        "Listens to Twitch chat and speaks messages sequentially using espeak-ng.\n"
        "Messages are queued and read every few seconds so they never overlap.\n"
        "Version " + SCRIPT_VERSION
    )


def script_defaults(settings):
    obs.obs_data_set_default_string(settings, "oauth_token", "")
    obs.obs_data_set_default_string(settings, "nickname", nickname)
    obs.obs_data_set_default_string(settings, "channel", "#your_channel")
    obs.obs_data_set_default_string(settings, "trigger_word", "")
    obs.obs_data_set_default_double(settings, "per_user_timeout", per_user_timeout)
    obs.obs_data_set_default_bool(settings, "greet_users", greet_users)
    obs.obs_data_set_default_string(settings, "greet_message", greet_message)
    obs.obs_data_set_default_double(settings, "greet_timeout_minutes", greet_timeout_minutes)
    obs.obs_data_set_default_int(settings, "speech_rate", speech_rate)
    obs.obs_data_set_default_double(settings, "speak_interval", speak_interval)
    obs.obs_data_set_default_bool(settings, "include_username", include_username)
    obs.obs_data_set_default_int(settings, "max_tts_length", max_tts_length)
    obs.obs_data_set_default_bool(settings, "enabled", False)
    obs.obs_data_set_default_int(settings, "pitch_min", DEFAULT_PITCH_MIN)
    obs.obs_data_set_default_int(settings, "pitch_max", DEFAULT_PITCH_MAX)
    obs.obs_data_set_default_string(settings, "text_source_name", "")
    obs.obs_data_set_default_string(settings, "image_source_name", "")


def script_properties():
    props = obs.obs_properties_create()

    enabled_prop = obs.obs_properties_add_bool(
        props,
        "enabled",
        "Enable chat reader",
    )
    obs.obs_property_set_modified_callback(enabled_prop, _on_enabled_modified)
    obs.obs_properties_add_text(
        props,
        "channel",
        "Twitch channel (#name)",
        obs.OBS_TEXT_DEFAULT,
    )
    obs.obs_properties_add_text(
        props,
        "nickname",
        "Nickname",
        obs.OBS_TEXT_DEFAULT,
    )
    obs.obs_properties_add_text(
        props,
        "trigger_word",
        "Trigger word",
        obs.OBS_TEXT_DEFAULT,
    )
    obs.obs_properties_add_text(
        props,
        "oauth_token",
        "OAuth token (optional)",
        obs.OBS_TEXT_PASSWORD,
    )

    obs.obs_properties_add_int(
        props,
        "speech_rate",
        "espeak-ng speed (-s)",
        80,
        350,
        10,
    )
    obs.obs_properties_add_float(
        props,
        "speak_interval",
        "Seconds between messages",
        0.5,
        10.0,
        0.5,
    )
    obs.obs_properties_add_float(
        props,
        "per_user_timeout",
        "Per user timeout (seconds)",
        0.0,
        60.0,
        0.25,
    )
    obs.obs_properties_add_bool(
        props,
        "greet_users",
        "Greet users",
    )
    obs.obs_properties_add_text(
        props,
        "greet_message",
        "Greet message",
        obs.OBS_TEXT_DEFAULT,
    )
    obs.obs_properties_add_float(
        props,
        "greet_timeout_minutes",
        "Greet timeout (minutes)",
        0.0,
        720.0,
        0.5,
    )
    obs.obs_properties_add_bool(
        props,
        "include_username",
        "Prefix chat messages with username",
    )
    obs.obs_properties_add_int(
        props,
        "max_tts_length",
        "Max characters spoken",
        50,
        500,
        10,
    )
    obs.obs_properties_add_int(
        props,
        "pitch_min",
        "Minimum pitch",
        0,
        400,
        5,
    )
    obs.obs_properties_add_int(
        props,
        "pitch_max",
        "Maximum pitch",
        0,
        400,
        5,
    )

    text_prop = obs.obs_properties_add_list(
        props,
        "text_source_name",
        "Text source",
        obs.OBS_COMBO_TYPE_LIST,
        obs.OBS_COMBO_FORMAT_STRING,
    )
    obs.obs_property_list_add_string(text_prop, "(None)", "")
    _populate_source_list(text_prop, TEXT_SOURCE_IDS)

    image_prop = obs.obs_properties_add_list(
        props,
        "image_source_name",
        "Image source",
        obs.OBS_COMBO_TYPE_LIST,
        obs.OBS_COMBO_FORMAT_STRING,
    )
    obs.obs_property_list_add_string(image_prop, "(None)", "")
    _populate_source_list(image_prop, IMAGE_SOURCE_IDS)

    _set_config_properties_enabled(props, not enabled)
    return props


def script_update(settings):
    global oauth_token, nickname, channel, speech_rate, speak_interval
    global include_username, max_tts_length, enabled, pitch_min, pitch_max
    global text_source_name, image_source_name, _display_visible, trigger_word
    global per_user_timeout, greet_users, greet_message, greet_timeout_minutes
    global _current_config, _pending_config, _pending_apply_time, _pending_force

    prev_enabled = enabled
    prev_text_source = text_source_name
    prev_image_source = image_source_name
    oauth_token = obs.obs_data_get_string(settings, "oauth_token").strip()
    nickname = obs.obs_data_get_string(settings, "nickname").strip() or "justinfan12345"
    channel = obs.obs_data_get_string(settings, "channel").strip()
    if channel and not channel.startswith("#"):
        channel = f"#{channel}"
    trigger_word = obs.obs_data_get_string(settings, "trigger_word").strip()
    per_user_timeout = max(0.0, obs.obs_data_get_double(settings, "per_user_timeout") or 0.0)
    greet_users = obs.obs_data_get_bool(settings, "greet_users")
    greet_message = obs.obs_data_get_string(settings, "greet_message").strip() or "Welcome {name}"
    greet_timeout_minutes = max(0.0, obs.obs_data_get_double(settings, "greet_timeout_minutes") or 0.0)
    speech_rate = obs.obs_data_get_int(settings, "speech_rate") or 150
    speak_interval = max(0.5, obs.obs_data_get_double(settings, "speak_interval") or 2.0)
    include_username = obs.obs_data_get_bool(settings, "include_username")
    max_tts_length = obs.obs_data_get_int(settings, "max_tts_length") or 280
    enabled = obs.obs_data_get_bool(settings, "enabled")
    pitch_min_value = obs.obs_data_get_int(settings, "pitch_min")
    pitch_max_value = obs.obs_data_get_int(settings, "pitch_max")
    text_source_name = obs.obs_data_get_string(settings, "text_source_name").strip()
    image_source_name = obs.obs_data_get_string(settings, "image_source_name").strip()

    if pitch_min_value == 0 and not obs.obs_data_has_user_value(settings, "pitch_min"):
        pitch_min_value = DEFAULT_PITCH_MIN
    if pitch_max_value == 0 and not obs.obs_data_has_user_value(settings, "pitch_max"):
        pitch_max_value = DEFAULT_PITCH_MAX

    pitch_min = pitch_min_value
    pitch_max = pitch_max_value

    if pitch_min < 0:
        pitch_min = 0
    if pitch_max < 0:
        pitch_max = 0
    if pitch_max < pitch_min:
        pitch_max = pitch_min

    if prev_text_source and prev_text_source != text_source_name:
        _apply_visibility_to_source(prev_text_source, False)
    if prev_image_source and prev_image_source != image_source_name:
        _apply_visibility_to_source(prev_image_source, False)
    if (prev_text_source != text_source_name) or (prev_image_source != image_source_name):
        _display_visible = False

    new_config = {
        "oauth_token": oauth_token,
        "nickname": nickname,
        "channel": channel,
    "trigger_word": trigger_word,
        "speech_rate": speech_rate,
        "speak_interval": speak_interval,
        "include_username": include_username,
        "max_tts_length": max_tts_length,
        "pitch_min": pitch_min,
        "pitch_max": pitch_max,
        "per_user_timeout": per_user_timeout,
        "greet_users": greet_users,
        "greet_message": greet_message,
        "greet_timeout_minutes": greet_timeout_minutes,
    }
    _pending_config = new_config
    _pending_apply_time = time.time()
    _pending_force = prev_enabled != enabled


def script_load(settings):
    script_update(settings)


def script_unload():
    stop_chat_thread()
    stop_tts_thread()
    _set_display_visibility(False)


def script_tick(seconds):
    _maybe_apply_config()
    dispatch_tts()
    _update_display_visibility_after_tts()


def restart_chat_thread():
    # Restart the Twitch listener thread with the latest configuration
    if not enabled:
        return

    stop_chat_thread()
    _drain_queue()
    start_chat_thread()


def start_chat_thread():
    # Launch the Twitch IRC worker thread if chat playback is enabled
    global _chat_thread

    if not enabled:
        return

    if not channel:
        obs.script_log(obs.LOG_WARNING, "Twitch channel is not set; skipping connect.")
        return

    _stop_event.clear()
    _chat_thread = threading.Thread(target=_chat_worker, name="TwitchChatThread", daemon=True)
    _chat_thread.start()


def stop_chat_thread():
    # Signal the chat worker to stop and wait for it to exit cleanly
    global _chat_thread, _chat_socket

    _stop_event.set()
    if _chat_socket is not None:
        try:
            _chat_socket.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            _chat_socket.close()
        except Exception:
            pass
        _chat_socket = None

    if _chat_thread is not None:
        _chat_thread.join(timeout=2.0)
        _chat_thread = None



def stop_tts_thread():
    # Join the speech synthesis worker if it is still running
    global _tts_thread

    if _tts_thread is not None and _tts_thread.is_alive():
        _tts_thread.join(timeout=1.0)
    _tts_thread = None


def _drain_queue():
    # Remove any queued messages so new configuration starts fresh
    while True:
        try:
            _message_queue.get_nowait()
        except queue.Empty:
            break


def _chat_worker():
    # Background loop that connects to Twitch IRC and parses chat messages
    global _chat_socket

    backoff = 5
    while not _stop_event.is_set() and enabled:
        try:
            _chat_socket = socket.create_connection((TWITCH_SERVER, TWITCH_PORT))
            _chat_socket.settimeout(1.0)
            _perform_handshake(_chat_socket)
            if _stop_event.is_set():
                break
            obs.script_log(obs.LOG_INFO, "Connected to Twitch chat")
            _listen_loop(_chat_socket)
            backoff = 5
        except Exception as err:
            if _stop_event.is_set():
                break
            obs.script_log(obs.LOG_WARNING, f"Chat connection error: {err}")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
        finally:
            if _chat_socket is not None:
                try:
                    _chat_socket.close()
                except Exception:
                    pass
                _chat_socket = None




def _perform_handshake(sock: socket.socket):
    if _stop_event.is_set() or not enabled:
        return

    token = oauth_token if oauth_token else "SCHMOOPIIE"
    if token and not token.startswith("oauth:"):
        token = f"oauth:{token}"

    login_lines = [
        "CAP REQ :twitch.tv/membership\r\n",
        f"PASS {token}\r\n",
        f"NICK {nickname}\r\n",
        f"JOIN {channel}\r\n",
    ]

    for line in login_lines:
        if _stop_event.is_set():
            return
        sock.sendall(line.encode("utf-8"))



def _listen_loop(sock: socket.socket):
    partial = ""
    while not _stop_event.is_set() and enabled:
        try:
            data = sock.recv(2048)
            if not data:
                raise ConnectionError("socket closed")
        except socket.timeout:
            continue
        except (OSError, ConnectionError) as err:
            if _stop_event.is_set():
                return
            raise ConnectionError(err) from err

        partial += data.decode("utf-8", errors="ignore")
        while "\r\n" in partial:
            line, partial = partial.split("\r\n", 1)
            _handle_line(sock, line)


def _handle_line(sock: socket.socket, line: str):
    if not line:
        return
    if line.startswith("PING"):
        try:
            sock.sendall("PONG :tmi.twitch.tv\r\n".encode("utf-8"))
        except Exception as err:
            obs.script_log(obs.LOG_WARNING, f"Failed to respond to PING: {err}")
        return

    if " JOIN " in line:
        _handle_join(line)
        return

    if "PRIVMSG" not in line:
        return

    prefix, _, trailing = line.partition(" PRIVMSG ")
    if not trailing:
        return

    username = prefix.split("!")[0]
    if username.startswith(":"):
        username = username[1:]

    message = trailing.split(":", 1)[-1]
    if not message:
        return

    text = message.strip()
    if not text:
        return

    if trigger_word:
        lowered = text.lower()
        trigger_lower = trigger_word.lower()
        if not lowered.startswith(trigger_lower):
            return
        suffix = text[len(trigger_word):]
        if not suffix or not suffix[0].isspace():
            return
        text = suffix.lstrip()
        if not text:
            return

    sanitized_message = _sanitize_text(text)
    if not sanitized_message:
        return

    sanitized_username = _sanitize_text(username) if username else ""
    user_key = username.lower() if username else ""

    if user_key and _is_user_on_cooldown(user_key):
        return

    if include_username and sanitized_username:
        speak_text = f"{sanitized_username} says: {sanitized_message}"
    else:
        speak_text = sanitized_message

    if len(speak_text) > max_tts_length:
        speak_text = f"{speak_text[: max_tts_length - 3]}..."

    if sanitized_username:
        display_text = f"{sanitized_username}: {sanitized_message}"
    else:
        display_text = sanitized_message

    if len(display_text) > max_tts_length:
        display_text = f"{display_text[: max_tts_length - 3]}..."

    pitch_value = _pitch_for_username(username)

    try:
        _message_queue.put_nowait(QueuedMessage(speak_text, pitch_value, display_text))
        if user_key:
            _user_last_trigger[user_key] = time.time()
    except queue.Full:
        obs.script_log(obs.LOG_WARNING, "Message queue full; dropping chat message")


def _sanitize_text(text: str) -> str:
    filtered = ''.join(ch if 32 <= ord(ch) < 127 else ' ' for ch in text)
    filtered = ' '.join(filtered.split())
    return filtered.strip()


def _is_user_on_cooldown(user_key: str) -> bool:
    if per_user_timeout <= 0.0:
        return False

    last_time = _user_last_trigger.get(user_key)
    if last_time is None:
        return False

    now = time.time()
    if now - last_time >= per_user_timeout:
        _user_last_trigger.pop(user_key, None)
        return False

    return True


def _handle_join(line: str):
    if not greet_users:
        return

    prefix, _, _ = line.partition(" JOIN ")
    if not prefix:
        return

    username = prefix.split("!")[0]
    if username.startswith(":"):
        username = username[1:]

    user_key = username.lower().strip()
    if not user_key:
        return

    if nickname and user_key == nickname.lower():
        return

    if _is_user_on_greet_cooldown(user_key):
        return

    sanitized_username = _sanitize_text(username)
    if not sanitized_username:
        return

    greet_text = greet_message.replace("{name}", sanitized_username)
    sanitized_greet = _sanitize_text(greet_text)
    if not sanitized_greet:
        return

    final_text = sanitized_greet
    if len(final_text) > max_tts_length:
        final_text = f"{final_text[: max_tts_length - 3]}..."

    pitch_value = _pitch_for_username(username)

    try:
        _message_queue.put_nowait(QueuedMessage(final_text, pitch_value, final_text))
        _user_last_greet[user_key] = time.time()
    except queue.Full:
        obs.script_log(obs.LOG_WARNING, "Message queue full; dropping greet message")


def _is_user_on_greet_cooldown(user_key: str) -> bool:
    timeout_seconds = max(0.0, greet_timeout_minutes * 60.0)
    if timeout_seconds <= 0.0:
        return False

    last_time = _user_last_greet.get(user_key)
    if last_time is None:
        return False

    now = time.time()
    if now - last_time >= timeout_seconds:
        _user_last_greet.pop(user_key, None)
        return False

    return True


def _pitch_for_username(username: str) -> int:
    local_min = max(0, pitch_min)
    local_max = max(local_min, pitch_max)

    if not username:
        if local_max == local_min:
            return local_min
        return (local_min + local_max) // 2

    key = username.lower().encode("utf-8", errors="ignore")
    digest = hashlib.sha1(key).digest()
    value = int.from_bytes(digest[:4], "big")

    span = local_max - local_min
    if span <= 0:
        return local_min

    return local_min + (value % (span + 1))


def dispatch_tts():
    global _tts_thread, _last_speech_time

    if _stop_event.is_set() or not enabled:
        return

    if _tts_thread is not None and _tts_thread.is_alive():
        return

    now = time.time()
    if now - _last_speech_time < speak_interval:
        return

    try:
        message = _message_queue.get_nowait()
    except queue.Empty:
        return

    _prepare_display(message.display_text)
    _last_speech_time = now
    _tts_thread = threading.Thread(
        target=_run_tts,
        args=(message.speak_text, message.pitch_value),
        name="TwitchTTSThread",
        daemon=True,
    )
    _tts_thread.start()


def _run_tts(speak_text: str, pitch_value: int):
    try:
        pitch_arg = _espeak_pitch_value(pitch_value)
        subprocess.run([
            "espeak-ng",
            "-s",
            str(speech_rate),
            "-p",
            str(pitch_arg),
            speak_text,
        ], check=False)
    except FileNotFoundError:
        obs.script_log(obs.LOG_ERROR, "espeak-ng not found; install it or adjust PATH")
    except Exception as err:
        obs.script_log(obs.LOG_WARNING, f"espeak-ng error: {err}")


def script_save(settings):
    # Make sure OBS keeps the current settings values
    pass


def _maybe_apply_config():
    global _pending_config, _pending_force

    if _pending_config is None:
        return

    delay = 0.0 if _pending_force else 0.75
    if time.time() - _pending_apply_time < delay:
        return

    config = _pending_config
    force = _pending_force
    _pending_config = None
    _pending_force = False
    _apply_config(config, force)


def _apply_config(config: dict, force: bool):
    global _current_config

    if not enabled:
        stop_chat_thread()
        stop_tts_thread()
        _drain_queue()
        _user_last_trigger.clear()
        _user_last_greet.clear()
        _set_display_visibility(False)
        _current_config = config
        return

    if not config.get("channel"):
        obs.script_log(obs.LOG_WARNING, "Twitch channel is not set; enable after configuring it.")
        stop_chat_thread()
        _drain_queue()
        _user_last_trigger.clear()
        _user_last_greet.clear()
        _set_display_visibility(False)
        _current_config = config
        return

    needs_restart = (
        force
        or config != _current_config
        or not _chat_thread
        or not _chat_thread.is_alive()
    )
    _current_config = config
    _user_last_trigger.clear()
    _user_last_greet.clear()

    if needs_restart:
        restart_chat_thread()


def _prepare_display(display_text: str):
    if text_source_name:
        _set_text_source_text(display_text)
    if text_source_name or image_source_name:
        _set_display_visibility(True)


def _set_text_source_text(display_text: str):
    if not text_source_name:
        return

    source = obs.obs_get_source_by_name(text_source_name)
    if source is None:
        return

    settings = obs.obs_source_get_settings(source)
    try:
        if settings is not None:
            obs.obs_data_set_string(settings, "text", display_text)
            obs.obs_source_update(source, settings)
    finally:
        if settings is not None:
            obs.obs_data_release(settings)
        obs.obs_source_release(source)


def _set_display_visibility(visible: bool):
    global _display_visible

    target_visible = bool(visible)
    _apply_visibility_to_source(text_source_name, target_visible)
    _apply_visibility_to_source(image_source_name, target_visible)
    _display_visible = target_visible and bool(text_source_name or image_source_name)


def _apply_visibility_to_source(source_name: str, visible: bool):
    if not source_name:
        return

    source = obs.obs_get_source_by_name(source_name)
    if source is None:
        return

    try:
        scenes = obs.obs_frontend_get_scenes()
        if scenes is None:
            return

        try:
            for scene_source in scenes:
                scene = obs.obs_scene_from_source(scene_source)
                if scene is None:
                    continue
                _set_source_visibility_in_scene(scene, source_name, visible)
        finally:
            obs.source_list_release(scenes)
    finally:
        obs.obs_source_release(source)


def _set_source_visibility_in_scene(scene, source_name: str, visible: bool):
    items = obs.obs_scene_enum_items(scene)
    if items is None:
        return

    try:
        for item in items:
            item_source = obs.obs_sceneitem_get_source(item)
            if item_source is None:
                continue
            if obs.obs_source_get_name(item_source) == source_name:
                obs.obs_sceneitem_set_visible(item, visible)
            child_scene = obs.obs_scene_from_source(item_source)
            if child_scene is not None:
                _set_source_visibility_in_scene(child_scene, source_name, visible)
    finally:
        obs.sceneitem_list_release(items)


def _update_display_visibility_after_tts():
    if not _display_visible:
        return
    if _tts_thread is not None and _tts_thread.is_alive():
        return
    if not _message_queue.empty():
        return
    _set_display_visibility(False)


def _populate_source_list(prop, allowed_ids):
    sources = obs.obs_enum_sources()
    if sources is None:
        return

    names = []
    try:
        for source in sources:
            try:
                source_id = obs.obs_source_get_unversioned_id(source)
            except AttributeError:
                source_id = obs.obs_source_get_id(source)
            if allowed_ids and source_id not in allowed_ids:
                continue
            name = obs.obs_source_get_name(source)
            if name:
                names.append(name)
    finally:
        obs.source_list_release(sources)

    for name in sorted(names, key=str.casefold):
        obs.obs_property_list_add_string(prop, name, name)


def _on_enabled_modified(props, prop, settings):
    enabled_state = obs.obs_data_get_bool(settings, "enabled")
    _set_config_properties_enabled(props, not enabled_state)
    return True


def _set_config_properties_enabled(props, enabled_state: bool):
    for name in _CONFIG_PROPERTY_NAMES:
        target = obs.obs_properties_get(props, name)
        if target is not None:
            obs.obs_property_set_enabled(target, enabled_state)


def _espeak_pitch_value(pitch_value: int) -> int:
    local_min = max(0, pitch_min)
    local_max = max(local_min, pitch_max)

    if pitch_value < local_min:
        pitch_value = local_min
    elif pitch_value > local_max:
        pitch_value = local_max

    span = local_max - local_min
    ratio = 0.0 if span <= 0 else (pitch_value - local_min) / span
    ratio = max(0.0, min(1.0, ratio))

    espeak_min = max(0, min(99, local_min))
    espeak_max = max(espeak_min, min(99, local_max))

    if espeak_max == espeak_min:
        return espeak_min

    espeak_value = espeak_min + ratio * (espeak_max - espeak_min)
    return int(round(espeak_value))
