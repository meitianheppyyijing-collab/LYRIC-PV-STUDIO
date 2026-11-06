"""Runtime frame handler, entrance motion evaluation, and caching."""

import bpy
from bpy.app.handlers import persistent

from ..constants import PV_ROOT_NAME, PV_TAG
from ..core.spatial import camera_frame_bounds

_ENTRANCE_CACHE = {}
_CONTROLLER_CACHE = {}


def invalidate_entrance_cache():
    """Invalidate per-scene entrance indexes after generated objects change."""
    _ENTRANCE_CACHE.clear()
    _CONTROLLER_CACHE.clear()


def _build_entrance_index(scene, collection, cache_key, current_frame):
    """Build an event index once; sequential frames then update only changed objects."""
    events = {}
    objects = []
    for obj in collection.all_objects:
        try:
            if not (
                obj.get(PV_TAG, False)
                and obj.type == "FONT"
                and obj.get("lyric_entrance_enabled", False)
            ):
                continue
            frame_in = int(float(obj.get("lyric_frame_in", 1.0)))
            frame_out = int(float(obj.get("lyric_frame_out", frame_in + 2)))
            first = frame_in - 1
            last_exclusive = frame_out + 2
            events.setdefault(first, [[], []])[0].append(obj)
            events.setdefault(last_exclusive, [[], []])[1].append(obj)
            objects.append(obj)
        except (ReferenceError, TypeError, ValueError):
            continue
    active = set()
    for frame, (added, removed) in events.items():
        if frame <= current_frame:
            active.difference_update(removed)
            active.update(added)
    _ENTRANCE_CACHE[cache_key] = {
        "events": events,
        "active": active,
        "frame": int(current_frame),
        "objects": tuple(objects),
    }
    return _ENTRANCE_CACHE[cache_key]


def update_lyric_entrance_positions(scene):
    """Evaluate and update entrance/exit and pop motion on active lyrics for the current frame."""
    if scene is None:
        return
    collection = bpy.data.collections.get(PV_ROOT_NAME)
    props = getattr(scene, "lyric_pv_props", None)
    if collection is None or props is None:
        return
    try:
        cache_key = (scene.as_pointer(), collection.as_pointer())
        controller = _CONTROLLER_CACHE.get(cache_key)
        if controller is None or controller.name not in bpy.data.objects:
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
            _CONTROLLER_CACHE[cache_key] = controller
        camera = controller.parent
        if camera is None or camera.type != "CAMERA":
            camera = props.target_camera or scene.camera
        if camera is None or camera.type != "CAMERA":
            return
        depth = abs(float(controller.location.z))
        if depth < 1e-6:
            depth = float(props.camera_distance)
        min_x, max_x, min_y, max_y = camera_frame_bounds(scene, camera, depth)
        frame_width = max(1e-6, max_x - min_x)
        frame_height = max(1e-6, max_y - min_y)
        slide_frames = max(1, int(props.slide_frames))
        distance_factor = max(1.0, float(props.entrance_distance))
        current_frame = int(scene.frame_current)
        index = _ENTRANCE_CACHE.get(cache_key)
        if index is None or current_frame != index["frame"] + 1:
            index = _build_entrance_index(scene, collection, cache_key, current_frame)
        else:
            # Sequential playback/render: process only events at this frame.
            added, removed = index["events"].get(current_frame, ((), ()))
            index["active"].difference_update(removed)
            index["active"].update(added)
            index["frame"] = current_frame
        for obj in index["active"]:
            try:
                frame_in = float(obj.get("lyric_frame_in", 1.0))
                frame_out = float(obj.get("lyric_frame_out", frame_in + slide_frames + 1.0))
                fade_frames = int(obj.get("lyric_fade_frames", 0))
                direction = str(obj.get("lyric_entrance_direction", "LEFT"))
                line_limit = max(1, int(frame_out - frame_in - fade_frames))
                effective_slide = min(slide_frames, line_limit)
                elapsed = current_frame - frame_in
                t = max(0.0, min(1.0, elapsed / effective_slide))
                eased = 1.0 - (1.0 - t) ** 3
                if direction == "NONE":
                    start_offset = (0.0, 0.0, 0.0)
                elif direction == "LEFT":
                    start_offset = (-frame_width * distance_factor, 0.0, 0.0)
                elif direction == "RIGHT":
                    start_offset = (frame_width * distance_factor, 0.0, 0.0)
                elif direction == "TOP":
                    start_offset = (0.0, frame_height * distance_factor, 0.0)
                else:
                    start_offset = (0.0, -frame_height * distance_factor, 0.0)
                if fade_frames > 0 and current_frame > frame_out - fade_frames:
                    exit_t = max(0.0, min(1.0, (current_frame - (frame_out - fade_frames)) / max(1, fade_frames)))
                    exit_eased = exit_t * exit_t * (3.0 - 2.0 * exit_t)
                    motion_x = -start_offset[0] * exit_eased
                    motion_y = -start_offset[1] * exit_eased
                else:
                    motion_x = start_offset[0] * (1.0 - eased)
                    motion_y = start_offset[1] * (1.0 - eased)
                base_x = float(obj.get("lyric_base_x", 0.0))
                base_y = float(obj.get("lyric_base_y", 0.0))
                base_z = float(obj.get("lyric_base_z", 0.0))
                pop_enabled = bool(obj.get("lyric_pop_enabled", False))
                pop_frames = max(1, int(obj.get("lyric_pop_frames", 4)))
                pop_t = max(0.0, min(1.0, (current_frame - frame_in) / pop_frames)) if pop_enabled else 1.0
                pop_eased = 1.0 - (1.0 - pop_t) ** 3
                pop_y = float(obj.get("lyric_pop_y", 0.0)) * (1.0 - pop_eased)
                pop_z = float(obj.get("lyric_pop_z", 0.0)) * (1.0 - pop_eased)
                obj.location = (base_x + motion_x, base_y + motion_y + pop_y, base_z + pop_z)
            except (ReferenceError, TypeError, ValueError):
                continue
    except (ReferenceError, RuntimeError, TypeError, ValueError):
        invalidate_entrance_cache()
        return


@persistent
def lyric_pv_frame_change_handler(scene, depsgraph=None):
    """Blender frame change post-handler for real-time entrance updates."""
    update_lyric_entrance_positions(scene)
