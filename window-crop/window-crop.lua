-- Window Crop: crops a full screen capture to the focused window.
-- A desktop shortcut runs report-window.sh, which writes the window
-- geometry to a file this script watches. Wayland hides other windows from OBS,
-- so the geometry has to come from the desktop.

obs = obslua

local FILTER_NAME = "Window Crop"
local SETTING_SOURCE = "source"
local REPORT_NAME = "obs-window-crop"
local REPORT_CHECK_INTERVAL_SECONDS = 0.1
local SLIDE_SECONDS = 0.35

-- OBS alignment flag, since obslua leaves out the center value
local ALIGN_CENTER = 0

local state = {
	sourceName = "",
	reportPath = (os.getenv("XDG_RUNTIME_DIR") or "/tmp") .. "/" .. REPORT_NAME,
	sinceReportCheck = 0,
	windowTarget = nil,
	slide = nil,
}

-- Rectangles

local function rect(x, y, width, height)
	return { x = x, y = y, width = width, height = height }
end

local function sameRect(a, b)
	return a and b and a.x == b.x and a.y == b.y and a.width == b.width and a.height == b.height
end

local function clampRect(r, maxWidth, maxHeight)
	local x = math.max(0, math.min(r.x, maxWidth - 1))
	local y = math.max(0, math.min(r.y, maxHeight - 1))
	local width = math.max(1, math.min(r.width, maxWidth - x))
	local height = math.max(1, math.min(r.height, maxHeight - y))
	return rect(x, y, width, height)
end

local function round(value)
	return math.floor(value + 0.5)
end

local function easeOutCubic(t)
	return 1 - (1 - t) ^ 3
end

local function lerpRect(from, to, t)
	local function lerp(a, b)
		return round(a + (b - a) * t)
	end
	return rect(lerp(from.x, to.x), lerp(from.y, to.y), lerp(from.width, to.width), lerp(from.height, to.height))
end

-- Maps a window in desktop coordinates onto the pixels of its screen's capture
local function windowOnCapture(window, output, captureWidth)
	local scale = captureWidth / output.width
	return rect(
		round((window.x - output.x) * scale),
		round((window.y - output.y) * scale),
		round(window.width * scale),
		round(window.height * scale))
end

-- OBS sources

local function withSource(action)
	local source = obs.obs_get_source_by_name(state.sourceName)
	if source == nil then
		obs.script_log(obs.LOG_WARNING, "Pick a screen capture in the Window Crop script settings first")
		return
	end
	action(source)
	obs.obs_source_release(source)
end

local function sourceSize(source)
	return obs.obs_source_get_base_width(source), obs.obs_source_get_base_height(source)
end

local function cropFilter(source)
	local filter = obs.obs_source_get_filter_by_name(source, FILTER_NAME)
	if filter ~= nil then
		return filter
	end
	local settings = obs.obs_data_create()
	obs.obs_data_set_bool(settings, "relative", false)
	filter = obs.obs_source_create_private("crop_filter", FILTER_NAME, settings)
	obs.obs_data_release(settings)
	obs.obs_source_filter_add(source, filter)
	return filter
end

local function currentCrop(filter, width, height)
	local settings = obs.obs_source_get_settings(filter)
	local crop = rect(
		obs.obs_data_get_int(settings, "left"),
		obs.obs_data_get_int(settings, "top"),
		obs.obs_data_get_int(settings, "cx"),
		obs.obs_data_get_int(settings, "cy"))
	obs.obs_data_release(settings)
	if crop.width == 0 or crop.height == 0 then
		return rect(0, 0, width, height)
	end
	return crop
end

local function applyCrop(filter, crop)
	local settings = obs.obs_data_create()
	obs.obs_data_set_bool(settings, "relative", false)
	obs.obs_data_set_int(settings, "left", crop.x)
	obs.obs_data_set_int(settings, "top", crop.y)
	obs.obs_data_set_int(settings, "cx", crop.width)
	obs.obs_data_set_int(settings, "cy", crop.height)
	obs.obs_source_update(filter, settings)
	obs.obs_data_release(settings)
end

-- Turns the capture's current size in the scene into a box the crop fits inside,
-- so a changing crop keeps the place and size the capture was given
local function keepSceneBox(source, crop)
	local sceneSource = obs.obs_frontend_get_current_scene()
	local item = obs.obs_scene_find_source(obs.obs_scene_from_source(sceneSource), obs.obs_source_get_name(source))
	if item ~= nil and obs.obs_sceneitem_get_bounds_type(item) == obs.OBS_BOUNDS_NONE then
		local scale = obs.vec2()
		obs.obs_sceneitem_get_scale(item, scale)
		local bounds = obs.vec2()
		bounds.x, bounds.y = crop.width * scale.x, crop.height * scale.y
		obs.obs_sceneitem_set_bounds_type(item, obs.OBS_BOUNDS_SCALE_INNER)
		obs.obs_sceneitem_set_bounds_alignment(item, ALIGN_CENTER)
		obs.obs_sceneitem_set_bounds(item, bounds)
	end
	obs.obs_source_release(sceneSource)
end

-- Sliding

local function slideTo(source, target)
	local width, height = sourceSize(source)
	local filter = cropFilter(source)
	state.slide = {
		from = currentCrop(filter, width, height),
		to = clampRect(target, width, height),
		elapsed = 0,
	}
	obs.obs_source_release(filter)
	keepSceneBox(source, state.slide.from)
end

local function stepSlide(seconds)
	local slide = state.slide
	slide.elapsed = math.min(slide.elapsed + seconds, SLIDE_SECONDS)
	local crop = lerpRect(slide.from, slide.to, easeOutCubic(slide.elapsed / SLIDE_SECONDS))
	withSource(function(source)
		local filter = cropFilter(source)
		applyCrop(filter, crop)
		obs.obs_source_release(filter)
	end)
	if slide.elapsed >= SLIDE_SECONDS then
		state.slide = nil
	end
end

local function showFullScreen()
	state.windowTarget = nil
	withSource(function(source)
		local width, height = sourceSize(source)
		slideTo(source, rect(0, 0, width, height))
	end)
end

-- The same window twice in a row goes back to the full screen
local function showWindow(window, output)
	withSource(function(source)
		local target = windowOnCapture(window, output, sourceSize(source))
		if sameRect(target, state.windowTarget) then
			showFullScreen()
			return
		end
		state.windowTarget = target
		slideTo(source, target)
	end)
end

-- Reports

local function parseReport(text)
	local values = {}
	for number in text:gmatch("[%d%.%-]+") do
		table.insert(values, tonumber(number))
	end
	if #values ~= 8 then
		return nil
	end
	return rect(values[1], values[2], values[3], values[4]), rect(values[5], values[6], values[7], values[8])
end

local function takeReport()
	local file = io.open(state.reportPath, "r")
	if file == nil then
		return nil
	end
	local text = file:read("*a")
	file:close()
	os.remove(state.reportPath)
	return text
end

local function checkReport(seconds)
	state.sinceReportCheck = state.sinceReportCheck + seconds
	if state.sinceReportCheck < REPORT_CHECK_INTERVAL_SECONDS then
		return
	end
	state.sinceReportCheck = 0

	local text = takeReport()
	if text == nil then
		return
	end
	local window, output = parseReport(text)
	if window == nil then
		obs.script_log(obs.LOG_WARNING, "Window Crop got an unreadable report: " .. text)
		return
	end
	showWindow(window, output)
end

-- Script interface

local function videoSourceNames()
	local names = {}
	local sources = obs.obs_enum_sources()
	for _, source in ipairs(sources or {}) do
		if bit.band(obs.obs_source_get_output_flags(source), obs.OBS_SOURCE_VIDEO) ~= 0 then
			table.insert(names, obs.obs_source_get_name(source))
		end
	end
	obs.source_list_release(sources)
	table.sort(names)
	return names
end

function script_description()
	return "Crops a full screen capture to the focused window.\nPress Meta+Shift+C on a window, and again to show the full screen."
end

function script_properties()
	local props = obs.obs_properties_create()
	local list = obs.obs_properties_add_list(props, SETTING_SOURCE, "Screen Capture",
		obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
	for _, name in ipairs(videoSourceNames()) do
		obs.obs_property_list_add_string(list, name, name)
	end
	obs.obs_properties_add_button(props, "full_screen", "Full Screen", function() showFullScreen() end)
	return props
end

function script_update(settings)
	state.sourceName = obs.obs_data_get_string(settings, SETTING_SOURCE)
end

function script_load()
	-- A report left from before OBS started is stale
	os.remove(state.reportPath)
end

function script_tick(seconds)
	checkReport(seconds)
	if state.slide then
		stepSlide(seconds)
	end
end
