"""Property update callbacks triggered by UI changes."""

import bpy
from mathutils import Matrix

from ..animation.runtime import update_lyric_entrance_positions
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
