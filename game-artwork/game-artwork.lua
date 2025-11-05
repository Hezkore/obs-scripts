--[[
Hezkore's Steam Game Artwork Fetcher

See README.md for usage details and limitations.
]]

local obs = obslua

local SCRIPT_VERSION = '1.0.0'

local USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) OBS-Lua-SteamArt/1.0"

local BACKGROUND_VARIANTS = {
	{ url = "https://cdn.cloudflare.steamstatic.com/steam/apps/%d/page_bg_generated_v6b.jpg", ext = "jpg" },
	{ url = "https://cdn.akamai.steamstatic.com/steam/apps/%d/page_bg_generated_v6b.jpg", ext = "jpg" },
	{ url = "https://cdn.cloudflare.steamstatic.com/steam/apps/%d/page_bg_generated_v6.jpg", ext = "jpg" },
	{ url = "https://cdn.akamai.steamstatic.com/steam/apps/%d/page_bg_generated_v6.jpg", ext = "jpg" },
	{ url = "https://cdn.cloudflare.steamstatic.com/steam/apps/%d/page_bg_generated.jpg", ext = "jpg" },
	{ url = "https://cdn.akamai.steamstatic.com/steam/apps/%d/page_bg_generated.jpg", ext = "jpg" },
	{ url = "https://cdn.cloudflare.steamstatic.com/steam/apps/%d/library_hero.jpg", ext = "jpg" },
	{ url = "https://cdn.akamai.steamstatic.com/steam/apps/%d/library_hero.jpg", ext = "jpg" },
	{ url = "https://cdn.cloudflare.steamstatic.com/steam/apps/%d/hero_capsule.jpg", ext = "jpg" },
	{ url = "https://cdn.akamai.steamstatic.com/steam/apps/%d/hero_capsule.jpg", ext = "jpg" },
	{ url = "https://cdn.cloudflare.steamstatic.com/steam/apps/%d/library_600x900.jpg", ext = "jpg" },
	{ url = "https://cdn.akamai.steamstatic.com/steam/apps/%d/library_600x900.jpg", ext = "jpg" },
	{ url = "https://cdn.cloudflare.steamstatic.com/steam/apps/%d/header.jpg", ext = "jpg" },
	{ url = "https://cdn.akamai.steamstatic.com/steam/apps/%d/header.jpg", ext = "jpg" }
}

local BANNER_VARIANTS = {
	{ url = "https://cdn.cloudflare.steamstatic.com/steam/apps/%d/header.jpg", ext = "jpg" },
	{ url = "https://cdn.akamai.steamstatic.com/steam/apps/%d/header.jpg", ext = "jpg" },
	{ url = "https://cdn.cloudflare.steamstatic.com/steam/apps/%d/capsule_616x353.jpg", ext = "jpg" },
	{ url = "https://cdn.akamai.steamstatic.com/steam/apps/%d/capsule_616x353.jpg", ext = "jpg" },
	{ url = "https://cdn.cloudflare.steamstatic.com/steam/apps/%d/library_hero.jpg", ext = "jpg" },
	{ url = "https://cdn.akamai.steamstatic.com/steam/apps/%d/library_hero.jpg", ext = "jpg" }
}

local LOGO_VARIANTS = {
	{ url = "https://cdn.cloudflare.steamstatic.com/steam/apps/%d/logo.png", ext = "png" },
	{ url = "https://cdn.akamai.steamstatic.com/steam/apps/%d/logo.png", ext = "png" },
	{ url = "https://cdn.cloudflare.steamstatic.com/steam/apps/%d/logo.jpg", ext = "jpg" },
	{ url = "https://cdn.akamai.steamstatic.com/steam/apps/%d/logo.jpg", ext = "jpg" },
	{ url = "https://cdn.cloudflare.steamstatic.com/steam/apps/%d/library_hero.jpg", ext = "jpg" },
	{ url = "https://cdn.akamai.steamstatic.com/steam/apps/%d/library_hero.jpg", ext = "jpg" },
	{ url = "https://cdn.cloudflare.steamstatic.com/steam/apps/%d/header.jpg", ext = "jpg" },
	{ url = "https://cdn.akamai.steamstatic.com/steam/apps/%d/header.jpg", ext = "jpg" }
}

local current_game_name = ""
local background_source_name = ""
local banner_source_name = ""
local logo_source_name = ""
local asset_dir = ""

local function trim(str)
	if not str then
		return ""
	end
	return (str:gsub("^%s+", ""):gsub("%s+$", ""))
end

local function url_encode(str)
	if not str then
		return ""
	end
	return str:gsub("([^%w%-_%.~])", function(char)
		return string.format("%%%02X", string.byte(char))
	end)
end

local function sanitize_filename(str)
	local sanitized = (str or ""):lower()
	sanitized = sanitized:gsub("%s+", "_")
	sanitized = sanitized:gsub("[^%w%-_%.]", "")
	sanitized = sanitized:gsub("_+", "_")
	sanitized = sanitized:gsub("^_", "")
	sanitized = sanitized:gsub("_$", "")
	if sanitized == "" then
		sanitized = "game_" .. tostring(os.time())
	end
	return sanitized
end

local function url_strip_query(url)
	local q = url:find("?", 1, true)
	if q then
		return url:sub(1, q - 1)
	end
	return url
end

local function url_extension(url)
	local path = url_strip_query(url)
	local ext = path:match("%.([%w]+)$")
	if ext then
		return ext:lower()
	end
	return "jpg"
end

local function run_command(cmd)
	local result = os.execute(cmd)
	if result == nil then
		return false
	end
	if type(result) == "number" then
		return result == 0
	end
	if type(result) == "boolean" then
		return result
	end
	return false
end

local function make_dir(path)
	if not path or path == "" then
		return
	end
	run_command(string.format('mkdir -p %q', path))
end

local function ensure_parent_dir(path)
	if not path then
		return
	end
	local dir = path:match("^(.*)/")
	if dir and dir ~= "" then
		make_dir(dir)
	end
end

local function file_size(path)
	local file = io.open(path, "rb")
	if not file then
		return 0
	end
	local size = file:seek("end")
	file:close()
	return size or 0
end

local function download_file(url, dest_path)
	ensure_parent_dir(dest_path)
	local temp_path = dest_path .. ".part"
	local cmd = string.format('curl -fsSL --compressed --retry 2 --retry-delay 1 -A %q -o %q %q', USER_AGENT, temp_path, url)
	if not run_command(cmd) then
		os.remove(temp_path)
		return false
	end
	if file_size(temp_path) == 0 then
		os.remove(temp_path)
		return false
	end
	os.remove(dest_path)
	os.rename(temp_path, dest_path)
	return true
end

local function http_get(url)
	local cmd = string.format('curl -fsSL --compressed -A %q %q', USER_AGENT, url)
	local pipe = io.popen(cmd)
	if not pipe then
		return nil, "unable to start curl"
	end
	local body = pipe:read("*a")
	local ok, reason, code = pipe:close()
	if ok == nil then
		if reason == "exit" then
			return nil, string.format("curl exited with code %d", code or -1)
		end
		return nil, "curl interrupted"
	end
	if not body or body == "" then
		return nil, "empty response"
	end
	return body, nil
end

local function populate_source_property(prop)
	obs.obs_property_list_clear(prop)
	obs.obs_property_list_add_string(prop, "(leave unchanged)", "")
	local sources = obs.obs_enum_sources()
	if sources ~= nil then
		for _, source in ipairs(sources) do
			local source_id = obs.obs_source_get_id(source)
			if source_id == "image_source" then
				local name = obs.obs_source_get_name(source)
				obs.obs_property_list_add_string(prop, name, name)
			end
		end
		obs.source_list_release(sources)
	end
end

local function refresh_source_lists(props)
	local background_prop = obs.obs_properties_get(props, "background_source")
	if background_prop ~= nil then
		populate_source_property(background_prop)
	end
	local banner_prop = obs.obs_properties_get(props, "banner_source")
	if banner_prop ~= nil then
		populate_source_property(banner_prop)
	end
	local logo_prop = obs.obs_properties_get(props, "logo_source")
	if logo_prop ~= nil then
		populate_source_property(logo_prop)
	end
end

-- Query the public Steam store search API for the first matching AppID
local function search_store_for_app(query)
	local url = string.format("https://store.steampowered.com/api/storesearch/?term=%s&cc=US&l=en", url_encode(query))
	local body, err = http_get(url)
	if not body then
		return nil, err
	end
	local data = obs.obs_data_create_from_json(body)
	if data == nil then
		return nil, "store search JSON parse failed"
	end
	local result = nil
	local items = obs.obs_data_get_array(data, "items")
	if items ~= nil then
		local count = obs.obs_data_array_count(items)
		for i = 0, count - 1 do
			local item = obs.obs_data_array_item(items, i)
			local item_type = obs.obs_data_get_string(item, "type")
			if item_type == nil or item_type == "app" then
				local appid = tonumber(obs.obs_data_get_int(item, "id"))
				if appid and appid > 0 then
					local name = obs.obs_data_get_string(item, "name")
					result = { appid = appid, name = name }
					obs.obs_data_release(item)
					break
				end
			end
			obs.obs_data_release(item)
		end
		obs.obs_data_array_release(items)
	end
	obs.obs_data_release(data)
	if result then
		return result, nil
	end
	return nil, "no app found"
end

-- Fallback to the more permissive community search when the store API misses
local function search_apps_for_app(query)
	if not obs.obs_data_array_create_from_json then
		return nil, "array parser unavailable"
	end
	local url = string.format("https://steamcommunity.com/actions/SearchApps/%s", url_encode(query))
	local body, err = http_get(url)
	if not body then
		return nil, err
	end
	local array = obs.obs_data_array_create_from_json(body)
	if array == nil then
		return nil, "SearchApps JSON parse failed"
	end
	local result = nil
	local count = obs.obs_data_array_count(array)
	for i = 0, count - 1 do
		local item = obs.obs_data_array_item(array, i)
		local appid = tonumber(obs.obs_data_get_int(item, "appid"))
		if appid and appid > 0 then
			local name = obs.obs_data_get_string(item, "name")
			result = { appid = appid, name = name }
			obs.obs_data_release(item)
			break
		end
		obs.obs_data_release(item)
	end
	obs.obs_data_array_release(array)
	if result then
		return result, nil
	end
	return nil, "no app found"
end

-- Try both search endpoints and return the first match (appid + name)
local function lookup_app(query)
	local result, err = search_store_for_app(query)
	if result then
		return result, nil
	end
	result, err = search_apps_for_app(query)
	if result then
		return result, nil
	end
	return nil, err
end

-- Iterate all known CDN patterns until one successfully downloads
local function fetch_variant(appid, slug, label, variants)
	for _, variant in ipairs(variants) do
		local url = string.format(variant.url, appid)
		local dest = string.format("%s/%s_%s.%s", asset_dir, slug, label, variant.ext)
		if download_file(url, dest) then
			return dest
		end
	end
	return nil
end

local function get_app_background_url(appid)
	local details_url = string.format("https://store.steampowered.com/api/appdetails?appids=%d&cc=US&l=en", appid)
	local body, err = http_get(details_url)
	if not body then
		return nil
	end
	local root = obs.obs_data_create_from_json(body)
	if root == nil then
		return nil
	end
	local key = tostring(appid)
	local entry = obs.obs_data_get_obj(root, key)
	if entry == nil then
		obs.obs_data_release(root)
		return nil
	end
	local success = obs.obs_data_get_bool(entry, "success")
	if not success then
		obs.obs_data_release(entry)
		obs.obs_data_release(root)
		return nil
	end
	local data = obs.obs_data_get_obj(entry, "data")
	if data == nil then
		obs.obs_data_release(entry)
		obs.obs_data_release(root)
		return nil
	end
	local background_raw = obs.obs_data_get_string(data, "background_raw")
	local background = obs.obs_data_get_string(data, "background")
	obs.obs_data_release(data)
	obs.obs_data_release(entry)
	obs.obs_data_release(root)
	if background_raw and background_raw ~= "" then
		return background_raw
	end
	if background and background ~= "" then
		return background
	end
	return nil
end

-- Backgrounds live behind slightly different endpoints, so try metadata first
local function fetch_background(appid, slug)
	local background_url = get_app_background_url(appid)
	if background_url and background_url ~= "" then
		local ext = url_extension(background_url)
		local dest = string.format("%s/%s_background.%s", asset_dir, slug, ext)
		if download_file(background_url, dest) then
			return dest
		end
	end
	return fetch_variant(appid, slug, "background", BACKGROUND_VARIANTS)
end

local function set_image_source(source_name, file_path)
	if not source_name or source_name == "" then
		return false
	end
	local source = obs.obs_get_source_by_name(source_name)
	if source == nil then
		obs.script_log(obs.LOG_WARNING, string.format("[Steam Art] Source '%s' not found", source_name))
		return false
	end
	local settings = obs.obs_source_get_settings(source)
	obs.obs_data_set_string(settings, "file", file_path)
	obs.obs_source_update(source, settings)
	obs.obs_data_release(settings)
	obs.obs_source_release(source)
	obs.script_log(obs.LOG_INFO, string.format("[Steam Art] Updated '%s' -> %s", source_name, file_path))
	return true
end

local function for_each_selected_source(callback)
	local seen = {}
	local function apply(name)
		if name and name ~= "" and not seen[name] then
			seen[name] = true
			callback(name)
		end
	end
	apply(background_source_name)
	apply(banner_source_name)
	apply(logo_source_name)
end

local function set_scene_visibility(scene_source, source_name, visible)
	if scene_source == nil or not source_name or source_name == "" then
		return
	end
	local scene = obs.obs_scene_from_source(scene_source)
	if scene == nil then
		return
	end
	local sceneitem = obs.obs_scene_find_source(scene, source_name)
	if sceneitem ~= nil then
		obs.obs_sceneitem_set_visible(sceneitem, visible)
	end
end

local function set_visibility_for_source_name(source_name, visible)
	if not source_name or source_name == "" then
		return
	end
	local program_scene = obs.obs_frontend_get_current_scene()
	local preview_scene = obs.obs_frontend_get_current_preview_scene()
	local same_scene = program_scene ~= nil and preview_scene ~= nil and program_scene == preview_scene

	if program_scene ~= nil then
		set_scene_visibility(program_scene, source_name, visible)
		obs.obs_source_release(program_scene)
	end

	if preview_scene ~= nil then
		if not same_scene then
			set_scene_visibility(preview_scene, source_name, visible)
		end
		obs.obs_source_release(preview_scene)
	end
end

-- Toggle visibility for any scene items using the selected artwork sources
local function set_selected_sources_visible(visible)
	for_each_selected_source(function(name)
		set_visibility_for_source_name(name, visible)
	end)
end

local function clear_image_source(source_name)
	if not source_name or source_name == "" then
		return false
	end
	local source = obs.obs_get_source_by_name(source_name)
	if source == nil then
		obs.script_log(obs.LOG_WARNING, string.format("[Steam Art] Source '%s' not found", source_name))
		return false
	end
	local settings = obs.obs_source_get_settings(source)
	obs.obs_data_set_string(settings, "file", "")
	obs.obs_source_update(source, settings)
	obs.obs_data_release(settings)
	obs.obs_source_release(source)
	obs.script_log(obs.LOG_INFO, string.format("[Steam Art] Cleared '%s'", source_name))
	return true
end

-- Resolve artwork for the configured game name and push to OBS image sources
local function fetch_and_apply_assets()
	local query = trim(current_game_name)
	if query == "" then
		obs.script_log(obs.LOG_WARNING, "[Steam Art] Please enter a game name before fetching")
		return
	end
	set_selected_sources_visible(false)
	local app, err = lookup_app(query)
	if not app then
		obs.script_log(obs.LOG_WARNING, string.format("[Steam Art] Could not find '%s' (%s)", query, err or "unknown error"))
			set_selected_sources_visible(true)
		return
	end
	local display_name = app.name ~= "" and app.name or query
	local slug = sanitize_filename(display_name)
	obs.script_log(obs.LOG_INFO, string.format("[Steam Art] Fetching artwork for '%s' (AppID %d)", display_name, app.appid))

	local background_path = fetch_background(app.appid, slug)
	if background_path then
		set_image_source(background_source_name, background_path)
	else
		obs.script_log(obs.LOG_WARNING, string.format("[Steam Art] No background image available for '%s'", display_name))
	end

	local banner_path = fetch_variant(app.appid, slug, "banner", BANNER_VARIANTS)
	if banner_path then
		set_image_source(banner_source_name, banner_path)
	else
		obs.script_log(obs.LOG_WARNING, string.format("[Steam Art] No banner image available for '%s'", display_name))
	end

	local logo_path = fetch_variant(app.appid, slug, "logo", LOGO_VARIANTS)
	if logo_path then
		set_image_source(logo_source_name, logo_path)
	else
		obs.script_log(obs.LOG_WARNING, string.format("[Steam Art] No logo image available for '%s'", display_name))
	end

	obs.script_log(obs.LOG_INFO, string.format("[Steam Art] Finished fetching assets for '%s'", display_name))
	set_selected_sources_visible(true)
end

local function refresh_sources_button(props, property)
	refresh_source_lists(props)
	return true
end

local function fetch_button_clicked(props, property)
	fetch_and_apply_assets()
	return true
end

local function clear_button_clicked(props, property)
	-- clear_image_source(background_source_name)
	-- clear_image_source(banner_source_name)
	-- clear_image_source(logo_source_name)
	set_selected_sources_visible(false)
	obs.script_log(obs.LOG_INFO, "[Steam Art] Hid selected artwork sources")
	return true
end

local function init_asset_directory()
	local base_path = script_path()
	if not base_path or base_path == "" then
		local home = os.getenv("HOME") or "."
		base_path = home .. "/.cache/obs"
	end
	asset_dir = base_path .. "/steam_game_art"
	make_dir(asset_dir)
end

function script_description()
	return "Steam Game Art Fetcher\nFetch Steam artwork (background, banner, logo) and apply it to selected image sources.\nVersion " .. SCRIPT_VERSION
end

function script_properties()
	local props = obs.obs_properties_create()
	obs.obs_properties_add_text(props, "game_name", "Game Name", obs.OBS_TEXT_DEFAULT)

	local background_list = obs.obs_properties_add_list(props, "background_source", "Background Image Source", obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
	local banner_list = obs.obs_properties_add_list(props, "banner_source", "Banner Image Source", obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
	local logo_list = obs.obs_properties_add_list(props, "logo_source", "Logo Image Source", obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)

	refresh_source_lists(props)

	obs.obs_properties_add_button(props, "refresh_sources", "Refresh Source Lists", refresh_sources_button)
	obs.obs_properties_add_button(props, "fetch_button", "Fetch Artwork", fetch_button_clicked)
	obs.obs_properties_add_button(props, "clear_button", "Clear Artwork", clear_button_clicked)

	return props
end

function script_defaults(settings)
	obs.obs_data_set_default_string(settings, "game_name", "")
	obs.obs_data_set_default_string(settings, "background_source", "")
	obs.obs_data_set_default_string(settings, "banner_source", "")
	obs.obs_data_set_default_string(settings, "logo_source", "")
end

function script_update(settings)
	current_game_name = obs.obs_data_get_string(settings, "game_name") or ""
	background_source_name = obs.obs_data_get_string(settings, "background_source") or ""
	banner_source_name = obs.obs_data_get_string(settings, "banner_source") or ""
	logo_source_name = obs.obs_data_get_string(settings, "logo_source") or ""
end

function script_load(settings)
	init_asset_directory()
end
