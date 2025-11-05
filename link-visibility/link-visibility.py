"""
Hezkore's OBS Link Visibility Helper

See README.md for configuration details and examples.
"""

import obspython as obs

SCRIPT_VERSION = "1.0.0"
settings_ref = None
# === Global State Managed Through The Script UI ===
main_source_name = ""
selected_source_name = ""
selected_child_name = ""
invert_children = False
linked_children = []
linked_lookup = {}
updating_ui = False
available_source_property = None
linked_children_property = None
LINKED_CHILDREN_KEY = "linked_children_serialized"


def rebuild_linked_lookup():
    global linked_lookup
    linked_lookup = {name: True for name in linked_children}


def source_exists(name):
    if not name:
        return False
    sources = obs.obs_enum_sources()
    if sources is None:
        return False
    found = False
    try:
        for src in sources:
            if obs.obs_source_get_name(src) == name:
                found = True
                break
    finally:
        obs.source_list_release(sources)
    return found


def populate_source_list(prop, exclude_main=False, exclude_linked=False, include_empty=False):
    # Keep this dropdown stocked with matching sources
    if prop is None:
        return
    obs.obs_property_list_clear(prop)
    if include_empty:
        obs.obs_property_list_add_string(prop, "-- Select --", "")
    sources = obs.obs_enum_sources()
    if sources is None:
        return
    try:
        for src in sources:
            name = obs.obs_source_get_name(src)
            if exclude_main and name == main_source_name:
                continue
            if exclude_linked and linked_lookup.get(name):
                continue
            obs.obs_property_list_add_string(prop, name, name)
    finally:
        obs.source_list_release(sources)


def update_setting_fields(target_settings=None):
    targets = []
    if settings_ref is not None:
        targets.append(settings_ref)
    if target_settings is not None and target_settings is not settings_ref:
        targets.append(target_settings)
    if not targets:
        return
    for data in targets:
        obs.obs_data_set_string(data, "main_source", main_source_name)
        obs.obs_data_set_string(data, "available_source", selected_source_name)
        obs.obs_data_set_string(data, "linked_children_list", selected_child_name)
        obs.obs_data_set_bool(data, "invert_mode", invert_children)


def save_linked_children(target_settings=None):
    targets = []
    if settings_ref is not None:
        targets.append(settings_ref)
    if target_settings is not None and target_settings is not settings_ref:
        targets.append(target_settings)
    if not targets:
        return

    serialized = "\n".join(linked_children)
    for data in targets:
        obs.obs_data_set_string(data, LINKED_CHILDREN_KEY, serialized)

    update_setting_fields(target_settings)


def sanitize_children(target_settings=None):
    global linked_children
    if not linked_children:
        rebuild_linked_lookup()
        if selected_child_name:
            set_selected_child("", target_settings)
        return

    seen = set()
    cleaned = []
    for name in linked_children:
        if not name or name == main_source_name or name in seen:
            continue
        seen.add(name)
        cleaned.append(name)

    linked_children = cleaned
    rebuild_linked_lookup()
    if linked_children:
        if selected_child_name not in linked_lookup:
            set_selected_child(linked_children[0], target_settings)
    elif selected_child_name:
        set_selected_child("", target_settings)

def populate_children_list(prop):
    if prop is None:
        return
    obs.obs_property_list_clear(prop)
    for name in linked_children:
        obs.obs_property_list_add_string(prop, name, name)


def refresh_properties_ui(props):
    # Rebuild the menus so new sources show up right away
    global updating_ui
    if props is None:
        return
    updating_ui = True
    try:
        main_prop = obs.obs_properties_get(props, "main_source")
        populate_source_list(main_prop, False, False, True)

        available_prop = obs.obs_properties_get(props, "available_source")
        if available_prop is None and hasattr(obs, "obs_property_group_content"):
            available_group = obs.obs_properties_get(props, "available_source_row")
            if available_group is not None:
                group_content = obs.obs_property_group_content(available_group)
                available_prop = obs.obs_properties_get(group_content, "available_source")
        if available_prop is None:
            available_prop = available_source_property
        populate_source_list(available_prop, True, True, True)

        children_prop = obs.obs_properties_get(props, "linked_children_list")
        if children_prop is None and hasattr(obs, "obs_property_group_content"):
            children_group = obs.obs_properties_get(props, "linked_children_row")
            if children_group is not None:
                group_content = obs.obs_property_group_content(children_group)
                children_prop = obs.obs_properties_get(group_content, "linked_children_list")
        if children_prop is None:
            children_prop = linked_children_property
        populate_children_list(children_prop)

        temp_settings = obs.obs_data_create()
        try:
            update_setting_fields(temp_settings)
            obs.obs_properties_apply_settings(props, temp_settings)
        finally:
            obs.obs_data_release(temp_settings)
    finally:
        updating_ui = False


def for_each_scene(callback):
    scenes = obs.obs_frontend_get_scenes()
    if scenes is None:
        return
    try:
        for scene_source in scenes:
            scene = obs.obs_scene_from_source(scene_source)
            if scene is not None:
                callback(scene_source, scene)
    finally:
        obs.source_list_release(scenes)


def apply_visibility_to_children(parent_visible_override=None):
    # Make every linked source copy the main one's visibility
    if not main_source_name or not linked_children:
        return

    visited = set()

    def apply_to_children(scene, target_visibility):
        if scene is None:
            return
        items = obs.obs_scene_enum_items(scene)
        if items is None:
            return
        try:
            for item in items:
                source = obs.obs_sceneitem_get_source(item)
                if source is None:
                    continue
                name = obs.obs_source_get_name(source)
                if linked_lookup.get(name):
                    obs.obs_sceneitem_set_visible(item, target_visibility)
        finally:
            obs.sceneitem_list_release(items)

    def process_scene(scene):
        scene_id = id(scene)
        if scene_id is None or scene_id in visited:
            return
        visited.add(scene_id)

        items = obs.obs_scene_enum_items(scene)
        if items is None:
            return
        try:
            for item in items:
                source = obs.obs_sceneitem_get_source(item)
                if source is None:
                    continue
                source_name = obs.obs_source_get_name(source)
                source_type = obs.obs_source_get_type(source)
                nested_scene = None

                if source_name == main_source_name:
                    visible_state = parent_visible_override
                    if visible_state is None:
                        visible_state = obs.obs_sceneitem_visible(item)
                    target_visibility = not visible_state if invert_children else visible_state
                    apply_to_children(scene, target_visibility)
                    if source_type == obs.OBS_SOURCE_TYPE_SCENE:
                        nested_scene = obs.obs_scene_from_source(source)
                        apply_to_children(nested_scene, target_visibility)

                if source_type == obs.OBS_SOURCE_TYPE_SCENE:
                    nested_scene = nested_scene or obs.obs_scene_from_source(source)
                    process_scene(nested_scene)
        finally:
            obs.sceneitem_list_release(items)

    def process_root(_, scene):
        process_scene(scene)

    for_each_scene(process_root)


def sync_children(parent_visible=None):
    apply_visibility_to_children(parent_visible)


def on_source_visibility(cd, visible):
    source = obs.calldata_source(cd, "source")
    if source is None:
        return
    if obs.obs_source_get_name(source) == main_source_name:
        sync_children(visible)


def on_source_destroy(cd):
    source = obs.calldata_source(cd, "source")
    if source is None:
        return
    name = obs.obs_source_get_name(source)

    removed = False
    if name == main_source_name:
        set_main_source("")
        removed = True
    if linked_lookup.get(name):
        if remove_child(name):
            set_selected_child("")
            save_linked_children()
            removed = True
    if removed:
        sync_children(None)


def handle_scene_change(event):
    if event == obs.OBS_FRONTEND_EVENT_SCENE_CHANGED:
        sync_children(None)


def on_source_show(cd):
    on_source_visibility(cd, True)


def on_source_hide(cd):
    on_source_visibility(cd, False)


def link_button_clicked(props, _):
    if settings_ref is not None:
        set_selected_source(obs.obs_data_get_string(settings_ref, "available_source"))
    if not selected_source_name or selected_source_name == main_source_name:
        refresh_properties_ui(props)
        return True
    if linked_lookup.get(selected_source_name):
        refresh_properties_ui(props)
        return True
    if not source_exists(selected_source_name):
        set_selected_source("")
        refresh_properties_ui(props)
        return True

    linked_children.append(selected_source_name)
    rebuild_linked_lookup()
    set_selected_child(selected_source_name)
    set_selected_source("")
    save_linked_children()
    refresh_properties_ui(props)
    sync_children(None)
    return True


def unlink_button_clicked(props, _):
    if settings_ref is not None:
        set_selected_child(obs.obs_data_get_string(settings_ref, "linked_children_list"))
    if not selected_child_name:
        refresh_properties_ui(props)
        return True
    if not remove_child(selected_child_name):
        set_selected_child("")
        refresh_properties_ui(props)
        return True
    set_selected_child("")
    save_linked_children()
    refresh_properties_ui(props)
    sync_children(None)
    return True


def clear_button_clicked(props, _):
    if not linked_children:
        refresh_properties_ui(props)
        return True
    linked_children.clear()
    rebuild_linked_lookup()
    set_selected_child("")
    save_linked_children()
    refresh_properties_ui(props)
    sync_children(None)
    return True


def invert_checkbox_modified(props, prop, settings):
    if updating_ui:
        return True
    set_invert_children(obs.obs_data_get_bool(settings, "invert_mode"), settings)
    sync_children(None)
    return True


def main_source_modified(props, prop, settings):
    if updating_ui:
        return True
    set_main_source(obs.obs_data_get_string(settings, "main_source"), settings)
    refresh_properties_ui(props)
    sync_children(None)
    return True


def available_source_modified(props, prop, settings):
    if updating_ui:
        return True
    set_selected_source(obs.obs_data_get_string(settings, "available_source"), settings)
    return True


def children_list_modified(props, prop, settings):
    if updating_ui:
        return True
    set_selected_child(obs.obs_data_get_string(settings, "linked_children_list"), settings)
    return True


def set_main_source(name, target_settings=None):
    global main_source_name
    main_source_name = name or ""
    sanitize_children(target_settings)
    save_linked_children(target_settings)


def set_selected_source(name, target_settings=None):
    global selected_source_name
    selected_source_name = name or ""
    if settings_ref is not None:
        obs.obs_data_set_string(settings_ref, "available_source", selected_source_name)
    if target_settings is not None and target_settings is not settings_ref:
        obs.obs_data_set_string(target_settings, "available_source", selected_source_name)


def set_selected_child(name, target_settings=None):
    global selected_child_name
    selected_child_name = name or ""
    if settings_ref is not None:
        obs.obs_data_set_string(settings_ref, "linked_children_list", selected_child_name)
    if target_settings is not None and target_settings is not settings_ref:
        obs.obs_data_set_string(target_settings, "linked_children_list", selected_child_name)


def set_invert_children(value, target_settings=None):
    global invert_children
    invert_children = bool(value)
    update_setting_fields(target_settings)


def remove_child(name):
    try:
        linked_children.remove(name)
        rebuild_linked_lookup()
        return True
    except ValueError:
        return False


def rebuild_children_from_settings(settings):
    global linked_children
    serialized = obs.obs_data_get_string(settings, LINKED_CHILDREN_KEY)
    if serialized:
        linked_children = [name for name in serialized.split("\n") if name]
    else:
        linked_children = []
        legacy_array = obs.obs_data_get_array(settings, "linked_children")
        if legacy_array is not None:
            count = obs.obs_data_array_count(legacy_array)
            for index in range(count):
                entry = obs.obs_data_array_item(legacy_array, index)
                name = obs.obs_data_get_string(entry, "name")
                if name:
                    linked_children.append(name)
                obs.obs_data_release(entry)
            obs.obs_data_array_release(legacy_array)
            if linked_children:
                save_linked_children(settings)
    rebuild_linked_lookup()


def script_description():
    return (
        "Link child sources to a main source and synchronize their visibility.\n"
        "Version: " + SCRIPT_VERSION
    )


def script_defaults(settings):
    obs.obs_data_set_default_string(settings, "main_source", "")
    obs.obs_data_set_default_string(settings, "available_source", "")
    obs.obs_data_set_default_string(settings, "linked_children_list", "")
    obs.obs_data_set_default_bool(settings, "invert_mode", False)


def script_properties():
    global available_source_property, linked_children_property
    props = obs.obs_properties_create()

    main_prop = obs.obs_properties_add_list(
        props,
        "main_source",
        "Main Source",
        obs.OBS_COMBO_TYPE_LIST,
        obs.OBS_COMBO_FORMAT_STRING,
    )
    obs.obs_property_set_modified_callback(main_prop, main_source_modified)
    invert_prop = obs.obs_properties_add_bool(props, "invert_mode", "Invert visibility")
    available_row = obs.obs_properties_create()
    available_prop = obs.obs_properties_add_list(
        available_row,
        "available_source",
        "Source to Link",
        obs.OBS_COMBO_TYPE_LIST,
        obs.OBS_COMBO_FORMAT_STRING,
    )
    available_source_property = available_prop
    obs.obs_property_set_modified_callback(available_prop, available_source_modified)
    obs.obs_properties_add_button(available_row, "link_button", "Link", link_button_clicked)
    available_group = obs.obs_properties_add_group(
        props,
        "available_source_row",
        "",
        obs.OBS_GROUP_NORMAL,
        available_row,
    )
    if hasattr(obs, "obs_property_set_group_layout"):
        if hasattr(obs, "OBS_GROUP_LAYOUT_FORM"):
            obs.obs_property_set_group_layout(available_group, obs.OBS_GROUP_LAYOUT_FORM)
        elif hasattr(obs, "OBS_GROUP_LAYOUT_HORIZONTAL"):
            obs.obs_property_set_group_layout(available_group, obs.OBS_GROUP_LAYOUT_HORIZONTAL)

    children_row = obs.obs_properties_create()
    children_prop = obs.obs_properties_add_list(
        children_row,
        "linked_children_list",
        "Linked Child",
        obs.OBS_COMBO_TYPE_LIST,
        obs.OBS_COMBO_FORMAT_STRING,
    )
    linked_children_property = children_prop
    obs.obs_property_set_modified_callback(children_prop, children_list_modified)
    obs.obs_properties_add_button(children_row, "unlink_button", "Unlink", unlink_button_clicked)
    obs.obs_properties_add_button(children_row, "clear_button", "Clear All", clear_button_clicked)
    children_group = obs.obs_properties_add_group(
        props,
        "linked_children_row",
        "",
        obs.OBS_GROUP_NORMAL,
        children_row,
    )
    if hasattr(obs, "obs_property_set_group_layout"):
        if hasattr(obs, "OBS_GROUP_LAYOUT_FORM"):
            obs.obs_property_set_group_layout(children_group, obs.OBS_GROUP_LAYOUT_FORM)
        elif hasattr(obs, "OBS_GROUP_LAYOUT_HORIZONTAL"):
            obs.obs_property_set_group_layout(children_group, obs.OBS_GROUP_LAYOUT_HORIZONTAL)

    
    
    obs.obs_property_set_modified_callback(invert_prop, invert_checkbox_modified)

    refresh_properties_ui(props)
    return props


def script_update(settings):
    global settings_ref, main_source_name, selected_source_name, selected_child_name, invert_children
    settings_ref = settings
    main_source_name = obs.obs_data_get_string(settings, "main_source") or ""
    selected_source_name = obs.obs_data_get_string(settings, "available_source") or ""
    selected_child_name = obs.obs_data_get_string(settings, "linked_children_list") or ""
    invert_children = obs.obs_data_get_bool(settings, "invert_mode")
    rebuild_children_from_settings(settings)
    sanitize_children()
    save_linked_children()
    update_setting_fields()
    sync_children(None)


def script_load(settings):
    global settings_ref
    settings_ref = settings
    signal_handler = obs.obs_get_signal_handler()
    obs.signal_handler_connect(signal_handler, "source_show", on_source_show)
    obs.signal_handler_connect(signal_handler, "source_hide", on_source_hide)
    obs.signal_handler_connect(signal_handler, "source_destroy", on_source_destroy)
    obs.obs_frontend_add_event_callback(handle_scene_change)
    rebuild_children_from_settings(settings)


def script_unload():
    obs.obs_frontend_remove_event_callback(handle_scene_change)


def script_save(settings):
    update_setting_fields(settings)
    save_linked_children(settings)
