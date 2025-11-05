"""
Hezkore's OBS MPRIS Artwork Display

See README.md for supported players, configuration, and troubleshooting tips.
"""

import ast
import obspython as obs
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

SCRIPT_VERSION = "1.0.0"

try:
	from gi.repository import GLib
except Exception:
	GLib = None

TEXT_SOURCE_IDS = {
	"text_ft2_source",
	"text_ft2_source_v2",
	"text_gdiplus",
	"text_gdiplus_v2",
}
IMAGE_SOURCE_IDS = {"image_source"}

PLAYER_FIRST = "first"
PLAYER_LAST = "last"
PLAYER_PLAYING = "playing"

# === Script Config Taken From The OBS UI ===
text_source_name = ""
image_source_name = ""
player_preference = PLAYER_PLAYING
format_template = "{artist} - {title}"
poll_interval_ms = 1000
transition_ms = 500

_display_visible = False
_poll_active = False
_last_state = None
_cached_art_url = ""
_cached_art_path = ""
_transition_state = None
_transition_deadline = 0.0
_transition_delay = 0.0
_transition_timer_active = False
_pending_state = None
_gdbus_missing = False
_last_logged_metadata = ""
_player_identities = {}


class _SafeDict(dict):
	def __missing__(self, key):
		return ""


def script_description():
	return (
		"Displays MPRIS metadata in selected OBS sources with simple transitions.\n"
		"Version " + SCRIPT_VERSION
	)


def script_defaults(settings):
	obs.obs_data_set_default_string(settings, "text_source", "")
	obs.obs_data_set_default_string(settings, "image_source", "")
	obs.obs_data_set_default_string(settings, "player_preference", PLAYER_PLAYING)
	obs.obs_data_set_default_string(settings, "format_template", "{artist} - {title}")
	obs.obs_data_set_default_int(settings, "poll_interval", 1000)
	obs.obs_data_set_default_int(settings, "transition_ms", 500)


def script_properties():
	props = obs.obs_properties_create()

	text_prop = obs.obs_properties_add_list(
		props,
		"text_source",
		"Text Source",
		obs.OBS_COMBO_TYPE_LIST,
		obs.OBS_COMBO_FORMAT_STRING,
	)
	obs.obs_property_list_add_string(text_prop, "None", "")
	_populate_source_property(text_prop, TEXT_SOURCE_IDS)

	image_prop = obs.obs_properties_add_list(
		props,
		"image_source",
		"Image Source",
		obs.OBS_COMBO_TYPE_LIST,
		obs.OBS_COMBO_FORMAT_STRING,
	)
	obs.obs_property_list_add_string(image_prop, "None", "")
	_populate_source_property(image_prop, IMAGE_SOURCE_IDS)

	pref_prop = obs.obs_properties_add_list(
		props,
		"player_preference",
		"Player Preference",
		obs.OBS_COMBO_TYPE_LIST,
		obs.OBS_COMBO_FORMAT_STRING,
	)
	obs.obs_property_list_add_string(pref_prop, "Currently playing", PLAYER_PLAYING)
	obs.obs_property_list_add_string(pref_prop, "First available", PLAYER_FIRST)
	obs.obs_property_list_add_string(pref_prop, "Last available", PLAYER_LAST)

	format_prop = obs.obs_properties_add_text(
		props,
		"format_template",
		"Format ",
		obs.OBS_TEXT_DEFAULT,
	)
	obs.obs_property_set_long_description(
		format_prop,
		"Placeholders: {title}, {artist}, {album}, {player}, {status}",
	)

	obs.obs_properties_add_int(props, "poll_interval", "Poll Interval (ms)", 100, 10000, 100)
	obs.obs_properties_add_int(props, "transition_ms", "Transition (ms)", 0, 5000, 50)

	return props


def script_load(settings):
	_restart_polling()


def script_unload():
	_stop_polling()
	_cancel_transition()
	_cleanup_art()
	_player_identities.clear()


def script_update(settings):
	global text_source_name
	global image_source_name
	global player_preference
	global format_template
	global poll_interval_ms
	global transition_ms

	text_source_name = obs.obs_data_get_string(settings, "text_source") or ""
	image_source_name = obs.obs_data_get_string(settings, "image_source") or ""
	player_preference = obs.obs_data_get_string(settings, "player_preference") or PLAYER_PLAYING
	format_template = obs.obs_data_get_string(settings, "format_template") or "{artist} - {title}"
	poll_interval_ms = max(100, int(obs.obs_data_get_int(settings, "poll_interval") or 0))
	transition_ms = max(0, int(obs.obs_data_get_int(settings, "transition_ms") or 0))

	_restart_polling()
	_poll()


def _populate_source_property(prop, allowed_ids):
	# Keep this picker filtered to sources we actually support
	sources = obs.obs_enum_sources()
	if sources is None:
		return

	try:
		for source in sources:
			source_id = obs.obs_source_get_id(source)
			if source_id in allowed_ids:
				name = obs.obs_source_get_name(source)
				obs.obs_property_list_add_string(prop, name, name)
	finally:
		obs.source_list_release(sources)


def _restart_polling():
	# Bounce the timer so it matches the latest interval
	global _poll_active

	if _poll_active:
		obs.timer_remove(_poll)
		_poll_active = False

	if poll_interval_ms > 0:
		obs.timer_add(_poll, poll_interval_ms)
		_poll_active = True


def _stop_polling():
	global _poll_active

	if _poll_active:
		obs.timer_remove(_poll)
		_poll_active = False


def _poll():
	# Timer hook that wraps the real poll work so errors stay quiet
	try:
		_poll_impl()
	except Exception as error:
		obs.script_log(obs.LOG_WARNING, f"MPRIS poll failed: {error}")


def _poll_impl():
	# Grab the current player state and push it into OBS
	global _last_state

	players = _list_players()
	if not players:
		_handle_idle()
		return

	states = []
	for player_id in players:
		state = _fetch_state(player_id)
		if state:
			states.append(state)

	if not states:
		_handle_idle()
		return

	selected = _select_state(states)
	if not selected:
		_handle_idle()
		return

	if selected["status"] != "Playing":
		_cancel_transition()
		_set_display_visibility(False)
		_last_state = selected
		return

	if transition_ms > 0 and _needs_transition(selected):
		_start_transition(selected)
	else:
		_cancel_transition()
		_apply_metadata(selected)
		_set_display_visibility(True)


def _handle_idle():
	global _last_state

	_cancel_transition()
	_set_display_visibility(False)
	_last_state = None


def _needs_transition(state):
	if _last_state is None:
		return False

	for key in ("player_id", "title", "artist", "album", "art_url"):
		if _last_state.get(key) != state.get(key):
			return True
	return False


def _start_transition(state):
	global _transition_state
	global _transition_deadline
	global _transition_delay
	global _pending_state

	_cancel_transition()

	half_ms = max(int(transition_ms / 2), 0)
	if half_ms <= 0:
		_apply_metadata(state)
		_set_display_visibility(True)
		return

	_pending_state = dict(state)
	_transition_delay = half_ms / 1000.0
	_transition_state = "wait_update"
	_transition_deadline = time.monotonic() + _transition_delay
	_set_display_visibility(False)
	_ensure_transition_timer()


def _ensure_transition_timer():
	global _transition_timer_active

	if not _transition_timer_active:
		obs.timer_add(_transition_tick, 50)
		_transition_timer_active = True


def _cancel_transition():
	global _transition_state
	global _pending_state
	global _transition_timer_active

	if _transition_timer_active:
		obs.timer_remove(_transition_tick)
		_transition_timer_active = False

	_transition_state = None
	_pending_state = None


def _transition_tick():
	global _transition_state
	global _transition_deadline
	global _pending_state
	global _transition_timer_active

	if _transition_state is None:
		obs.timer_remove(_transition_tick)
		_transition_timer_active = False
		return

	now = time.monotonic()
	if now < _transition_deadline:
		return

	if _transition_state == "wait_update":
		_transition_state = "wait_show"
		_transition_deadline = now + _transition_delay
	elif _transition_state == "wait_show":
		if _pending_state is not None:
			_apply_metadata(_pending_state)
		_set_display_visibility(True)
		_transition_state = None
		_pending_state = None
		obs.timer_remove(_transition_tick)
		_transition_timer_active = False


def _apply_metadata(state):
	global _last_state

	if state is None:
		return

	state_copy = dict(state)

	force_player_only = not state_copy.get("title")
	text = _format_text(state_copy, force_player_only=force_player_only)
	state_copy["formatted_text"] = text
	if text_source_name and text:
		if _last_state is None or _last_state.get("formatted_text") != text:
			_update_text_source(text)
	elif text_source_name and (_last_state or {}).get("formatted_text"):
		_update_text_source("")

	art_path = _resolve_art_path(state_copy.get("art_url"))
	state_copy["art_path"] = art_path
	if art_path and image_source_name:
		if _last_state is None or _last_state.get("art_path") != art_path:
			_update_image_source(art_path)

	_last_state = state_copy


def _format_text(state, force_player_only=False):
	player_only = state.get("player_name", "")
	if force_player_only:
		return player_only

	template = format_template or "{artist} - {title}"
	data = {
		"title": state.get("title", ""),
		"artist": state.get("artist", ""),
		"album": state.get("album", ""),
		"player": player_only,
		"status": state.get("status", ""),
	}

	try:
		result = template.format_map(_SafeDict(data))
	except Exception:
		fall_back = "{artist} - {title}"
		result = fall_back.format_map(_SafeDict(data))

	if not result.strip():
		return player_only

	cleaned = result.strip()
	cleaned = cleaned.strip("-:|/").strip()
	if not cleaned:
		return player_only

	return cleaned


def _select_state(states):
	if not states:
		return None

	if player_preference == PLAYER_PLAYING:
		for state in states:
			if state["status"] == "Playing":
				return state
		return None

	if player_preference == PLAYER_LAST:
		return states[-1]

	return states[0]


def _fetch_state(player_id):
	status = _get_property(player_id, "PlaybackStatus")
	metadata = _get_property(player_id, "Metadata")

	if status is None and metadata is None:
		return None

	metadata = _normalize_map(metadata)

	global _last_logged_metadata

	title = _value_to_string(_metadata_lookup(metadata, "xesam:title", "title"))
	album = _value_to_string(_metadata_lookup(metadata, "xesam:album", "album"))
	artist_value = _metadata_lookup(metadata, "xesam:artist", "artist")
	if isinstance(artist_value, (list, tuple)):
		artist = ", ".join(str(item) for item in artist_value if item)
	else:
		artist = _value_to_string(artist_value)

	art_url = _value_to_string(_metadata_lookup(metadata, "mpris:artUrl", "xesam:artUrl", "artUrl"))
	player_name = _get_player_name(player_id)
	playback_status = _value_to_string(status)

	if playback_status == "Playing" and not title:
		if metadata:
			obs.script_log(obs.LOG_DEBUG, f"No title found in metadata for {player_name}: {metadata}")
		title = player_name

	metadata_signature = repr(metadata)
	if metadata_signature != _last_logged_metadata and metadata:
		#obs.script_log(obs.LOG_DEBUG, f"MPRIS metadata for {player_name}: {metadata}")
		_last_logged_metadata = metadata_signature

	return {
		"player_id": player_id,
		"player_name": player_name,
		"status": playback_status,
		"title": title,
		"artist": artist,
		"album": album,
		"art_url": art_url,
	}


def _normalize_map(value):
	value = _extract_payload(value)
	if isinstance(value, dict):
		return {str(key): _extract_payload(val) for key, val in value.items()}
	if isinstance(value, (list, tuple)):
		result = {}
		for entry in value:
			if isinstance(entry, (list, tuple)) and len(entry) >= 2:
				key = entry[0]
				val = entry[1]
				if isinstance(key, bytes):
					key = key.decode("utf-8", "ignore")
				result[str(key)] = _extract_payload(val)
		return result
	if isinstance(value, str):
		parsed = _parse_metadata_from_string(value)
		if parsed:
			return parsed
		try:
			evaluated = ast.literal_eval(value)
		except Exception:
			return {}
		return _normalize_map(evaluated)
	return {}


def _metadata_lookup(metadata, *keys):
	for key in keys:
		if key in metadata:
			return metadata[key]
		alt = key.split(":", 1)[-1]
		if alt in metadata:
			return metadata[alt]
		lower_key = key.lower()
		for existing_key in metadata.keys():
			if existing_key.lower() == lower_key:
				return metadata[existing_key]
	return None


def _value_to_string(value):
	value = _extract_payload(value)

	if value is None:
		return ""
	if isinstance(value, (list, tuple)):
		return str(value[0]) if value else ""
	return str(value)


def _simplify_player_name(player_id):
	if not player_id:
		return ""
	name = player_id.split(".")[-1]
	name = name.replace("_", " ").strip()
	if name.lower().startswith("instance"):
		parts = name.split()
		name = " ".join(parts[1:]) if len(parts) > 1 else ""
	return name.title() if name else player_id


def _get_player_name(player_id):
	global _player_identities

	if not player_id:
		return ""

	cached = _player_identities.get(player_id)
	if cached:
		return cached

	identity = _get_property(player_id, "Identity", interface="org.mpris.MediaPlayer2")
	identity_text = _value_to_string(identity)
	if identity_text:
		_player_identities[player_id] = identity_text
		return identity_text

	fallback = _simplify_player_name(player_id)
	_player_identities[player_id] = fallback
	return fallback


def _list_players():
	raw = _run_gdbus(
		[
			"gdbus",
			"call",
			"--session",
			"--dest",
			"org.freedesktop.DBus",
			"--object-path",
			"/org/freedesktop/DBus",
			"--method",
			"org.freedesktop.DBus.ListNames",
		]
	)
	if not raw:
		return []

	candidates = [part for part in raw.split("'") if part.startswith("org.mpris.MediaPlayer2.")]
	if candidates:
		return candidates

	data = _parse_gvariant(raw)
	if isinstance(data, tuple) and data:
		data = data[0]
	if isinstance(data, list):
		return [name for name in data if name.startswith("org.mpris.MediaPlayer2.")]
	return []



def _get_property(player_id, prop_name, interface="org.mpris.MediaPlayer2.Player"):
	if not player_id:
		return None

	raw = _run_gdbus(
		[
			"gdbus",
			"call",
			"--session",
			"--dest",
			player_id,
			"--object-path",
			"/org/mpris/MediaPlayer2",
			"--method",
			"org.freedesktop.DBus.Properties.Get",
			interface,
			prop_name,
		]
	)
	data = _parse_gvariant(raw)
	value = _extract_payload(data)
	if value is None:
		value = _parse_raw_property(raw, prop_name)
		if value is None and raw:
			obs.script_log(obs.LOG_WARNING, f"Failed to parse {prop_name}: {raw}")
	return value


def _run_gdbus(command):
	global _gdbus_missing

	try:
		result = subprocess.run(
			command,
			check=True,
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
			timeout=2,
		)
		return result.stdout.decode("utf-8", "ignore").strip()
	except FileNotFoundError:
		if not _gdbus_missing:
			obs.script_log(obs.LOG_WARNING, "gdbus not found. Install glib2 utilities.")
			_gdbus_missing = True
		return ""
	except subprocess.SubprocessError:
		return ""


def _parse_gvariant(text):
	if not text:
		return None

	cleaned = text.strip()
	if cleaned.endswith(";"):
		cleaned = cleaned[:-1]
	
	if GLib is not None:
		try:
			return GLib.Variant.parse(None, cleaned, None, None).unpack()
		except Exception:
			pass

	cleaned = cleaned.replace("GLib.Variant", "Variant")
	cleaned = cleaned.replace("<", "(").replace(">", ")")
	cleaned = cleaned.replace(" true", " True").replace(" false", " False")
	cleaned = cleaned.replace("True", "True").replace("False", "False")

	try:
		return eval(cleaned, {"Variant": lambda *args: args[-1]})
	except Exception:
		pass

	try:
		return ast.literal_eval(cleaned)
	except Exception:
		if cleaned.startswith("(") and cleaned.endswith(")"):
			inner = cleaned[1:-1].strip()
			if not inner:
				return None
			split_items = [item.strip() for item in inner.split(",") if item.strip()]
			processed = [item.strip("'\"") for item in split_items]
			if not processed:
				return None
			if len(processed) == 1:
				return processed[0]
			return processed
		return None


def _parse_raw_property(raw, prop_name):
	if not raw:
		return None

	normalized = raw.strip()

	if GLib is not None:
		try:
			return GLib.Variant.parse(None, normalized, None, None).unpack()
		except Exception:
			pass

	normalized = normalized.replace("GLib.Variant", "Variant")
	normalized = normalized.replace("<", "(").replace(">", ")")
	normalized = normalized.replace(" true", " True").replace(" false", " False")

	try:
		value = eval(normalized, {"Variant": lambda *args: args[-1]})
	except Exception:
		try:
			value = ast.literal_eval(normalized)
		except Exception:
			return None

	value = _extract_payload(value)
	if isinstance(value, tuple) and len(value) == 1:
		return value[0]
	if prop_name == "Metadata" and not isinstance(value, dict):
		parsed = _parse_metadata_from_string(raw)
		if parsed:
			return parsed
	return value


def _extract_payload(value):
	if isinstance(value, dict):
		return {key: _extract_payload(val) for key, val in value.items()}
	if isinstance(value, list):
		return [_extract_payload(item) for item in value]
	if isinstance(value, tuple):
		if not value:
			return value
		if len(value) == 2 and isinstance(value[0], str):
			signature = value[0].strip("'\"")
			if signature and all(char.isalpha() or char in "{}[]()" for char in signature):
				return _extract_payload(value[1])
		return _extract_payload(value[-1])
	return value


def _parse_metadata_from_string(raw):
	entries = {}
	for match in re.finditer(r"'([^']+)':\s*<(.*?)>", raw, re.DOTALL):
		key = match.group(1)
		payload = match.group(2).strip().rstrip(",")
		if not payload:
			entries[key] = ""
			continue
		if payload == "[]":
			entries[key] = []
			continue
		try:
			value = ast.literal_eval(payload)
		except Exception:
			value = payload.strip("'\"")
		entries[key] = _extract_payload(value)
	return entries


def _resolve_art_path(art_url):
	global _cached_art_url
	global _cached_art_path

	if not art_url:
		return None

	if art_url.startswith("file://"):
		path = urllib.parse.unquote(art_url[7:])
		return _cache_local_art(path)

	if art_url.startswith("http://") or art_url.startswith("https://"):
		if art_url == _cached_art_url and _cached_art_path and os.path.isfile(_cached_art_path):
			return _cached_art_path

		old_path = _cached_art_path
		old_url = _cached_art_url

		tmp_path = None
		try:
			parsed = urllib.parse.urlparse(art_url)
			extension = os.path.splitext(parsed.path)[1] or ".jpg"
			handle, tmp_path = tempfile.mkstemp(prefix="obs_mpris_art_", suffix=extension)
			os.close(handle)
			urllib.request.urlretrieve(art_url, tmp_path)
		except (OSError, urllib.error.URLError):
			if tmp_path and os.path.isfile(tmp_path):
				try:
					os.remove(tmp_path)
				except OSError:
					pass
			_cached_art_url = old_url
			_cached_art_path = old_path
			if old_path and os.path.isfile(old_path):
				return old_path
			return None

		_cached_art_url = art_url
		_cached_art_path = tmp_path
		if old_path and os.path.isfile(old_path) and old_path != tmp_path:
			try:
				os.remove(old_path)
			except OSError:
				pass
		return tmp_path

	if os.path.isfile(art_url):
		return _cache_local_art(art_url)

	return None


def _cache_local_art(source_path):
	global _cached_art_url
	global _cached_art_path

	if not source_path or not os.path.isfile(source_path):
		return None

	if _cached_art_url == source_path and _cached_art_path and os.path.isfile(_cached_art_path):
		return _cached_art_path

	old_path = _cached_art_path
	try:
		extension = os.path.splitext(source_path)[1] or ".jpg"
		handle, tmp_path = tempfile.mkstemp(prefix="obs_mpris_art_", suffix=extension)
		os.close(handle)
		shutil.copy2(source_path, tmp_path)
	except OSError:
		if 'tmp_path' in locals() and tmp_path and os.path.isfile(tmp_path):
			try:
				os.remove(tmp_path)
			except OSError:
				pass
		if old_path and os.path.isfile(old_path):
			return old_path
		return None

	_cached_art_url = source_path
	_cached_art_path = tmp_path
	if old_path and os.path.isfile(old_path) and old_path != tmp_path:
		try:
			os.remove(old_path)
		except OSError:
			pass

	return tmp_path


def _cleanup_art():
	global _cached_art_url
	global _cached_art_path

	_cached_art_url = ""
	_cached_art_path = ""


def _update_text_source(text):
	source = obs.obs_get_source_by_name(text_source_name)
	if source is None:
		return

	try:
		settings = obs.obs_source_get_settings(source)
		try:
			obs.obs_data_set_string(settings, "text", text)
			obs.obs_source_update(source, settings)
		finally:
			obs.obs_data_release(settings)
	finally:
		obs.obs_source_release(source)


def _update_image_source(path):
	source = obs.obs_get_source_by_name(image_source_name)
	if source is None:
		return

	try:
		settings = obs.obs_source_get_settings(source)
		try:
			obs.obs_data_set_string(settings, "file", path)
			obs.obs_source_update(source, settings)
		finally:
			obs.obs_data_release(settings)
	finally:
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
