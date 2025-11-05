--[[
Hezkore's Xcomposite Window Capture Hotkey Script

See the README.md for more details
]]

local obs = obslua

local SCRIPT_VERSION = '1.0.0'

-- User settings
local selected_source_name = nil
local debug_enabled = true

-- Hotkey ID storage
local change_hotkey_id = obs.OBS_INVALID_HOTKEY_ID

-- Logging stuff
local log_info, log_warn, log_error, log_debug

-- Simple logging helpers
function log_info(msg)  obs.script_log(obs.LOG_INFO,  msg) end
function log_warn(msg)  obs.script_log(obs.LOG_WARNING,'[WARNING] ' .. msg) end
function log_error(msg) obs.script_log(obs.LOG_ERROR,  '[ERROR] ' .. msg) end
function log_debug(msg)
	if debug_enabled then
		obs.script_log(obs.LOG_INFO, '[DEBUG] ' .. msg)
	end
end

-- === Low level X11 stuff (FFI) ===============================================

-- We talk straight to Xlib so we don't need external tools like xdotool/xprop
local have_ffi, ffi = pcall(require, 'ffi')
if have_ffi then
	ffi.cdef [[
		typedef unsigned long XID; typedef XID Window; typedef unsigned long Atom; typedef struct _XDisplay Display;
		Display *XOpenDisplay(const char *display_name);
		int XCloseDisplay(Display *display);
		Atom XInternAtom(Display*, const char* name, int only_if_exists);
		int XGetWindowProperty(Display*, Window, Atom, long, long, int, Atom, Atom*, int*, unsigned long*, unsigned long*, unsigned char**);
		int XGetInputFocus(Display*, Window*, int*);
		int XFetchName(Display*, Window, char**);
		int XQueryTree(Display*, Window, Window*, Window*, Window**, unsigned int*);
		typedef struct { char *res_name; char *res_class; } XClassHint;
		int XGetClassHint(Display*, Window, XClassHint*);
		int XFree(void*);
	]]
else
	log_error('LuaJIT FFI not available (need OBS built with LuaJIT)')
end

-- === The script itself =======================================================

-- Get window title & class info
local function x11_get_window_meta(disp, win)
	local title = ''
	if not have_ffi then return title, '', '' end
	
	-- Try to get the _NET_WM_NAME first
	local ATOM_NET_WM_NAME = ffi.C.XInternAtom(disp, '_NET_WM_NAME', 1)
	local ATOM_UTF8_STRING = ffi.C.XInternAtom(disp, 'UTF8_STRING', 1)
	if ATOM_NET_WM_NAME ~= 0 and ATOM_UTF8_STRING ~= 0 then
		local actual_type = ffi.new('Atom[1]')
		local actual_format = ffi.new('int[1]')
		local nitems = ffi.new('unsigned long[1]')
		local bytes_after = ffi.new('unsigned long[1]')
		local prop = ffi.new('unsigned char*[1]')
		local r = ffi.C.XGetWindowProperty(disp, win, ATOM_NET_WM_NAME, 0, 1024, 0, ATOM_UTF8_STRING, actual_type, actual_format, nitems, bytes_after, prop)
		if r == 0 and prop[0] ~= nil and nitems[0] > 0 then
			title = ffi.string(prop[0], nitems[0])
			ffi.C.XFree(prop[0])
		end
	end
	
	-- Did we get a title?
	-- If not, try the legacy XFetchName
	if title == '' then
		local name_ptr = ffi.new('char*[1]')
		if ffi.C.XFetchName(disp, win, name_ptr) ~= 0 and name_ptr[0] ~= nil then
			title = ffi.string(name_ptr[0])
			ffi.C.XFree(name_ptr[0])
		end
	end
	
	-- Get class name & class
	local cls_name, cls_class = '', ''
	local hint = ffi.new('XClassHint')
	if ffi.C.XGetClassHint(disp, win, hint) ~= 0 then
		if hint.res_name  ~= nil then cls_name  = ffi.string(hint.res_name)  end
		if hint.res_class ~= nil then cls_class = ffi.string(hint.res_class) end
		if hint.res_name  ~= nil then ffi.C.XFree(hint.res_name)  end
		if hint.res_class ~= nil then ffi.C.XFree(hint.res_class) end
	end
	
	return title, cls_name, cls_class
end

-- Focused entire chain of window focus (stop before root!)
local function x11_get_focus_chain()
	if not have_ffi then return nil, 'ffi unavailable' end
	
	local disp = ffi.C.XOpenDisplay(nil)
	if disp == nil then return nil, 'XOpenDisplay failed' end
	
	local focus_return = ffi.new('Window[1]')
	local revert_to = ffi.new('int[1]')
	if ffi.C.XGetInputFocus(disp, focus_return, revert_to) == 0 then
		ffi.C.XCloseDisplay(disp)
		return nil, 'XGetInputFocus failed'
	end
	
	local current = tonumber(focus_return[0])
	if not current or current == 0 then
		ffi.C.XCloseDisplay(disp)
		return nil, 'No focus window'
	end
	
	local chain = {}
	local root_holder = ffi.new('Window[1]')
	local parent_holder = ffi.new('Window[1]')
	local children_ptr = ffi.new('Window*[1]')
	local nchildren = ffi.new('unsigned int[1]')
	while current and current ~= 0 do
		local title, cls_name, cls_class = x11_get_window_meta(disp, current)
		table.insert(chain, { id = current, title = title, cls_name = cls_name, cls_class = cls_class })
		
		local status = ffi.C.XQueryTree(disp, current, root_holder, parent_holder, children_ptr, nchildren)
		if status == 0 then break end
		if children_ptr[0] ~= nil then ffi.C.XFree(children_ptr[0]) end
		
		local parent = tonumber(parent_holder[0])
		local root = tonumber(root_holder[0])
		if not parent or parent == 0 or parent == root or parent == current then break end
		current = parent
	end
	
	ffi.C.XCloseDisplay(disp)
	return chain, nil
end

local function is_xcomposite_source(source)
	if not source then return false end
	local id = obs.obs_source_get_unversioned_id(source)
	return id == 'xcomposite_input'
end

local function list_xcomposite_sources()
	local results = {}
	local sources = obs.obs_enum_sources()
	if sources ~= nil then
		for _, src in ipairs(sources) do
			if is_xcomposite_source(src) then
				table.insert(results, obs.obs_source_get_name(src))
			end
		end
		obs.source_list_release(sources)
	end
	table.sort(results, function(a,b) return a:lower()<b:lower() end)
	return results
end

local function get_source_by_name(name)
	if not name or name == '' then return nil end
	
	local src = obs.obs_get_source_by_name(name)
	if src ~= nil and not is_xcomposite_source(src) then
		log_warn('Selected source "' .. name .. '" is not a Window Capture (Xcomposite) anymore.')
	end
	
	return src
end

-- Try a couple of possible text forms OBS might be expecting in its 'window' field
-- It could be padded + unpadded hex with a title (or class fallback), or a plain id >_>
local function build_window_id_candidates(win_decimal_id, title, cls_name, cls_class)
	if not win_decimal_id or win_decimal_id == '' then return {} end
	
	local num = tonumber(win_decimal_id)
	if not num then return {} end
	title    = title or ''
	cls_name = cls_name or ''
	cls_class= cls_class or ''

	local title_pref = title
	if title_pref == '' then
		if cls_name ~= '' then title_pref = cls_name
		elseif cls_class ~= '' then title_pref = cls_class
		else title_pref = 'unknown' end
	end

	local base_hex_full = string.format('0x%08x', num)
	local base_hex      = string.format('0x%x', num)

	local combos = {
		base_hex_full .. ' ' .. title_pref,
		base_hex      .. ' ' .. title_pref,
		base_hex  -- bare id (last resort)
	}

	local seen, out = {}, {}
	for _, v in ipairs(combos) do
		if not seen[v] then
			seen[v] = true
			table.insert(out, v)
		end
	end
	return out
end

local function update_capture_to_active_window()
	if not selected_source_name or selected_source_name == '' then
		log_warn('No source selected. Ignoring hotkey.')
		return
	end

	local src = get_source_by_name(selected_source_name)
	if src == nil then
		log_error('Source not found: ' .. tostring(selected_source_name))
		return
	end

	if not is_xcomposite_source(src) then
		log_error('Source exists but is not a Window Capture (Xcomposite): ' .. selected_source_name)
		obs.obs_source_release(src)
		return
	end

	log_debug('Hotkey: updating source "' .. selected_source_name .. '"')

	-- Get current settings
	local settings = obs.obs_source_get_settings(src)

	-- Get focus chain
	local chain, err = x11_get_focus_chain()
	if not chain or #chain == 0 then
		log_error('Failed to get focus chain: ' .. tostring(err))
		obs.obs_data_release(settings)
		obs.obs_source_release(src)
		return
	end
	local win_id = tostring(chain[1].id)
	local win_title = chain[1].title or ''	
	
	-- Build possible candidate window list
	local candidates = {}
	for _, node in ipairs(chain) do
		local id_str = tostring(node.id)
		local cls_final = (node.cls_class and node.cls_class ~= '' and node.cls_class)
			or (node.cls_name and node.cls_name ~= '' and node.cls_name) or 'unknown'
		for _, c in ipairs(build_window_id_candidates(id_str, node.title, node.cls_name, node.cls_class)) do
			table.insert(candidates, { win_string = c, dec_id = id_str, title = node.title or '', class_name = cls_final })
		end
	end
	
	-- Reorder! Try candidates with an actual title so OBS first gets proppah metadata
	table.sort(candidates, function(a,b)
		local a_empty = (a.title == nil or a.title == '')
		local b_empty = (b.title == nil or b.title == '')
		if a_empty ~= b_empty then return not a_empty end
		return a.win_string < b.win_string
	end)
	if #candidates == 0 then
		log_error('No window id candidates produced.')
		obs.obs_data_release(settings)
		obs.obs_source_release(src)
		return
	end

	local concat_list = {}
	for i, c in ipairs(candidates) do concat_list[i] = c.win_string end
	log_debug('Candidate chain: ' .. table.concat(concat_list, ' || '))

	local applied = nil
	for _, cand in ipairs(candidates) do
		local class_name = cand.class_name or 'unknown'
		local title_line = (cand.title and cand.title ~= '' and cand.title) or class_name
		local capture_window_string = string.format('%s\n%s\n%s', cand.dec_id, title_line, class_name)
		obs.obs_data_set_string(settings, 'window',         cand.win_string)
		obs.obs_data_set_string(settings, 'capture_window', capture_window_string)
		obs.obs_data_set_string(settings, 'title',          title_line)
		obs.obs_data_set_string(settings, 'class',          class_name)
		obs.obs_source_update(src, settings)
		local verify_settings = obs.obs_source_get_settings(src)
		local readback = obs.obs_data_get_string(verify_settings, 'window') or ''
		obs.obs_data_release(verify_settings)
		if readback == cand.win_string then
			applied = cand
			break
		else
			log_debug('Reject ' .. cand.win_string .. ' (readback ' .. readback .. ')')
		end
	end
	
	if applied then
		log_info('Window updated: ' .. applied.win_string)
	else
		log_error('Failed to apply any candidate window (maybe compositor protection?).')
	end
	
	obs.obs_data_release(settings)
	obs.obs_source_release(src)
end

-- === OBS script lifecycle / GUI===============================================

local function on_change_hotkey(pressed)
	if not pressed then return end
	update_capture_to_active_window()
end

local function populate_source_list(list_prop)
	obs.obs_property_list_clear(list_prop)
	for _, name in ipairs(list_xcomposite_sources()) do
		obs.obs_property_list_add_string(list_prop, name, name)
	end
end

function script_properties()
	local props = obs.obs_properties_create()
	local list_prop = obs.obs_properties_add_list(props, 'source_name', 'Window Capture Source', obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
	populate_source_list(list_prop)
	obs.obs_properties_add_button(props, 'refresh_sources', 'Refresh List', function()
		populate_source_list(list_prop)
		log_info('Source list refreshed')
		return true
	end)
	obs.obs_properties_add_bool(props, 'debug_enabled', 'Debug Logging')
	return props
end

function script_update(settings)
	selected_source_name = obs.obs_data_get_string(settings, 'source_name') or ''
	debug_enabled = obs.obs_data_get_bool(settings, 'debug_enabled')
	log_debug('Settings updated: source=' .. selected_source_name .. ' debug=' .. tostring(debug_enabled))
end

function script_defaults(settings)
	obs.obs_data_set_default_bool(settings, 'debug_enabled', false)
end

function script_save(settings)
	local arr = obs.obs_hotkey_save(change_hotkey_id)
	obs.obs_data_set_array(settings, 'change_window_hotkey', arr)
	obs.obs_data_array_release(arr)
end

function script_load(settings)
	change_hotkey_id = obs.obs_hotkey_register_frontend('change_capture_window', 'Change Capture Window', on_change_hotkey)
	local arr = obs.obs_data_get_array(settings, 'change_window_hotkey')
	obs.obs_hotkey_load(change_hotkey_id, arr)
	obs.obs_data_array_release(arr)
end

function script_description()
	return ('Active Window Hotkey (Xcomposite)\nHotkey switches the selected Window Capture to the active window.\nVersion ' .. SCRIPT_VERSION)
end
