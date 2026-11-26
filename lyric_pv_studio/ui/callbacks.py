"""Property update callbacks triggered by UI changes."""

import bpy
from mathutils import Matrix

from ..animation.keyframing import shift_action_keyframes
from ..animation.runtime import invalidate_entrance_cache, update_lyric_entrance_positions
from ..blender.geometry_nodes import (
    LYRIC_SOLIDIFY_GROUP_NAME,
    SOCKET_FRAME_OFFSET,
    set_lyric_solidify_inputs,
    set_lyric_solidify_socket_default,
)
from ..blender.materials import (
    TEXT_MATERIAL_NAME,
    sync_three_state_material_groups,
    update_stage_group_basic_params,
)
from ..constants import PV_ROOT_NAME, PV_TAG
from ..core.spatial import camera_frame_bounds, get_occlusion_safe_distance


def update_lyric_viewport_visibility(self, context):
    """Toggle visibility of lyric objects in the active 3D view layer."""
    collection = bpy.data.collections.get(PV_ROOT_NAME)
    if collection is None:
        return
    hide_lyrics = bool(self.hide_lyrics_in_viewport)
    view_layer = context.view_layer if context else None
    for obj in collection.all_objects:
        if obj.get(PV_TAG, False):
            obj.hide_set(hide_lyrics, view_layer=view_layer)


def update_lyric_font_size(self, context):
    """Update font size across all generated FONT curve objects in real time."""
    collection = bpy.data.collections.get(PV_ROOT_NAME)
    if collection is None:
        return
    size = float(self.font_size)
    for obj in collection.all_objects:
        if obj.get(PV_TAG, False) and obj.type == "FONT" and obj.data:
            multiplier = float(obj.get("lyric_font_multiplier", 1.0))
            obj.data.size = size * multiplier


def update_lyric_positions(self, context):
    """Recompute empty controller placement based on camera bounds, depth, and occlusion."""
    scene = context.scene if context else bpy.context.scene
    if scene is None:
        return
    collection = bpy.data.collections.get(PV_ROOT_NAME)
    if collection is None:
        return
    props = getattr(scene, "lyric_pv_props", None)
    if props is None:
        return
    controller = next(
        (
            obj
            for obj in collection.all_objects
            if obj.get(PV_TAG, False) and obj.get("lyric_pv_controller", False)
        ),
        None,
    )
    if controller is None:
        return
    camera = controller.parent
    if camera is None or camera.type != "CAMERA":
        camera = props.target_camera or scene.camera
    if camera is None or camera.type != "CAMERA":
        return
    distance = get_occlusion_safe_distance(scene, camera, props)
    min_x, max_x, min_y, max_y = camera_frame_bounds(scene, camera, distance)
    frame_width = max(1e-6, max_x - min_x)
    frame_height = max(1e-6, max_y - min_y)
    base_distance = max(1e-4, float(controller.get("lyric_base_distance", distance)))
    depth_ratio = max(0.25, min(4.0, float(distance) / base_distance))

    x = min_x + frame_width * (float(props.display_x) + 0.5)
    y = min_y + frame_height * (float(props.display_y) + 0.5)
    if controller.parent != camera:
        controller.parent = camera
        controller.matrix_parent_inverse = Matrix.Identity(4)
    controller.location = (x, y, -distance)
    controller.rotation_euler = (0.0, 0.0, 0.0)
    controller.scale = (depth_ratio, depth_ratio, depth_ratio)

    # Keep each sentence/line inside the camera independently. This preserves
    # the designed spread of multiple lyrics while preventing edge lines from
    # being pushed out of frame by the global display offset.
    margin_x = frame_width * 0.035
    margin_y = frame_height * 0.035
    for obj in collection.all_objects:
        if not obj.get(PV_TAG, False):
            continue
        is_sentence = obj.type == "EMPTY" and obj.get("lyric_sentence_group", False)
        is_line = obj.type == "FONT" and obj.get("lyric_entrance_enabled", False)
        if not (is_sentence or is_line):
            continue
        local_bounds = obj.get("lyric_local_bounds", None)
        if local_bounds is None or len(local_bounds) != 4:
            continue
        local_min_x, local_max_x, local_min_y, local_max_y = (
            float(value) for value in local_bounds
        )
        low_x = (min_x + margin_x - x) / depth_ratio - local_min_x
        high_x = (max_x - margin_x - x) / depth_ratio - local_max_x
        low_y = (min_y + margin_y - y) / depth_ratio - local_min_y
        high_y = (max_y - margin_y - y) / depth_ratio - local_max_y

        layout_x = float(obj.get("lyric_layout_x", obj.get("lyric_base_x", obj.location.x)))
        layout_y = float(obj.get("lyric_layout_y", obj.get("lyric_base_y", obj.location.y)))
        if low_x <= high_x:
            adjusted_x = max(low_x, min(high_x, layout_x))
        else:
            adjusted_x = ((min_x + max_x) * 0.5 - x) / depth_ratio - (local_min_x + local_max_x) * 0.5
        if low_y <= high_y:
            adjusted_y = max(low_y, min(high_y, layout_y))
        else:
            adjusted_y = ((min_y + max_y) * 0.5 - y) / depth_ratio - (local_min_y + local_max_y) * 0.5

        obj["lyric_base_x"] = float(adjusted_x)
        obj["lyric_base_y"] = float(adjusted_y)
        obj.location.x = adjusted_x
        obj.location.y = adjusted_y



def update_lyric_entrance_settings(self, context):
    """Notify active scene to re-evaluate entrance positions."""
    scene = context.scene if context else bpy.context.scene
    update_lyric_entrance_positions(scene)


def update_lyric_per_char_material(self, context):
    """Sync the UI per-char material toggle and transition frames to all lyc_solidify modifiers."""
    collection = bpy.data.collections.get(PV_ROOT_NAME)
    if collection is None:
        return
    enabled = bool(self.per_char_material_enabled)
    transition = max(0.0, float(self.material_transition_frames))
    for obj in collection.all_objects:
        if not obj.get(PV_TAG, False) or obj.type != "FONT":
            continue
        mod = obj.modifiers.get(LYRIC_SOLIDIFY_GROUP_NAME)
        if mod is not None and mod.type == "NODES":
            set_lyric_solidify_inputs(
                mod,
                per_char_enabled=enabled,
                transition_frames=transition,
            )
            obj.update_tag()


def update_lyric_frame_offset(self, context):
    """Live-sync the UI frame offset to lyc_solidify group inputs, keyframes, and entrance motion."""
    scene = context.scene if context else bpy.context.scene
    new_offset = int(self.frame_offset)
    set_lyric_solidify_socket_default(SOCKET_FRAME_OFFSET, float(new_offset))

    collection = bpy.data.collections.get(PV_ROOT_NAME)
    if collection is not None:
        seen_actions = set()
        for obj in collection.all_objects:
            if not obj.get(PV_TAG, False):
                continue
            touched = False
            if obj.type == "FONT":
                mod = obj.modifiers.get(LYRIC_SOLIDIFY_GROUP_NAME)
                if mod is not None and mod.type == "NODES":
                    set_lyric_solidify_inputs(mod, frame_offset=new_offset)
                    touched = True
            if getattr(getattr(obj, "animation_data", None), "action", None) is not None:
                old_offset = int(obj.get("lyric_applied_frame_offset", 0))
                delta = new_offset - old_offset
                if delta != 0:
                    shift_action_keyframes(obj, delta, seen_actions=seen_actions)
                    obj["lyric_applied_frame_offset"] = new_offset
                    touched = True
            if touched:
                obj.update_tag()

    invalidate_entrance_cache()
    if scene is not None:
        try:
            scene.frame_set(scene.frame_current, subframe=scene.frame_subframe)
        except Exception:
            update_lyric_entrance_positions(scene)


def update_lyric_stage_shaders(self, context):
    """Live-sync user-selected before/singing/after shader groups into LPV_Text_Material."""
    mat = next(
        (
            item
            for item in bpy.data.materials
            if item.get(PV_TAG, False) and item.name.startswith(TEXT_MATERIAL_NAME)
        ),
        None,
    )
    if mat is None:
        return
    sync_three_state_material_groups(
        mat,
        self.shader_group_before,
        self.shader_group_singing,
        self.shader_group_after,
    )


def update_lyric_after_appearance(self, context):
    """Update default RGB/Emission Strength on the after shader group when tweaked in sidebar."""
    update_stage_group_basic_params(
        self.shader_group_after,
        color=self.text_color,
        glow_strength=self.glow_strength,
    )
