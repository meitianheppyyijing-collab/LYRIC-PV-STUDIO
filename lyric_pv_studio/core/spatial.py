"""Camera projection bounds, safe distance, occlusion analysis, and character avoidance."""

import bpy
from mathutils import Vector


def camera_frame_bounds(scene, camera, distance):
    """Calculate the viewport bounding limits at a specific camera distance."""
    frame = camera.data.view_frame(scene=scene)
    zs = [abs(v.z) for v in frame if abs(v.z) > 1e-8]
    reference_depth = sum(zs) / len(zs) if zs else 1.0
    xs = [v.x * distance / reference_depth for v in frame]
    ys = [v.y * distance / reference_depth for v in frame]
    return min(xs), max(xs), min(ys), max(ys)


def get_occlusion_safe_distance(scene, camera, props):
    """Determine the safe depth plane behind an occlusion character target."""
    base_distance = float(props.camera_distance)
    target = getattr(props, "occlusion_target", None)
    if not getattr(props, "keep_behind_target", False) or target is None:
        return base_distance
    if target.type == "MESH":
        candidates = [target]
    elif target.type == "ARMATURE":
        candidates = []
        for obj in scene.objects:
            if obj.type != "MESH":
                continue
            driven = any(mod.type == "ARMATURE" and mod.object == target for mod in obj.modifiers)
            parent = obj.parent
            parented = False
            while parent is not None:
                if parent == target:
                    parented = True
                    break
                parent = parent.parent
            if driven or parented:
                candidates.append(obj)
    else:
        candidates = []
    if not candidates:
        return base_distance
    try:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        camera_inverse = camera.matrix_world.inverted_safe()
    except Exception:
        return base_distance
    farthest_depth = None
    for source in candidates:
        try:
            evaluated = source.evaluated_get(depsgraph)
            for corner in evaluated.bound_box:
                camera_corner = camera_inverse @ (evaluated.matrix_world @ Vector(corner))
                depth = -camera_corner.z
                if depth > 0.0:
                    farthest_depth = depth if farthest_depth is None else max(farthest_depth, depth)
        except Exception:
            continue
    if farthest_depth is None:
        return base_distance
    return max(base_distance, farthest_depth + float(props.occlusion_margin))


def get_character_screen_bounds(scene, camera, target, distance):
    """Calculate the 2D bounding box of the target character on the camera plane."""
    if target is None:
        return None
    if target.type == "MESH":
        candidates = [target]
    elif target.type == "ARMATURE":
        candidates = []
        for obj in scene.objects:
            if obj.type != "MESH":
                continue
            driven = any(mod.type == "ARMATURE" and mod.object == target for mod in obj.modifiers)
            parent = obj.parent
            parented = False
            while parent is not None:
                if parent == target:
                    parented = True
                    break
                parent = parent.parent
            if driven or parented:
                candidates.append(obj)
    else:
        return None
    if not candidates:
        return None
    try:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        camera_inverse = camera.matrix_world.inverted_safe()
    except Exception:
        return None
    points = []
    for source in candidates:
        try:
            evaluated = source.evaluated_get(depsgraph)
            for corner in evaluated.bound_box:
                co = camera_inverse @ (evaluated.matrix_world @ Vector(corner))
                if co.z < -1e-5:
                    scale = distance / max(-co.z, 1e-5)
                    points.append((co.x * scale, co.y * scale))
        except Exception:
            continue
    if not points:
        return None
    return (
        min(v[0] for v in points),
        max(v[0] for v in points),
        min(v[1] for v in points),
        max(v[1] for v in points),
    )


def nudge_lyric_away_from_character(scene, camera, props, x, y, width, height, distance, frame_bounds):
    """Nudge lyric placement to resolve 2D overlap with character screen bounds."""
    target = getattr(props, "occlusion_target", None)
    if target is None:
        return x, y
    char_bounds = get_character_screen_bounds(scene, camera, target, distance)
    if char_bounds is None:
        return x, y
    min_x, max_x, min_y, max_y = frame_bounds
    fw, fh = max_x - min_x, max_y - min_y
    half_w, half_h = max(width, fw * 0.025) * 0.5, max(height, fh * 0.018) * 0.5

    def overlap(cx, cy):
        a0, a1 = cx - half_w, cx + half_w
        b0, b1 = cy - half_h, cy + half_h
        ix = max(0.0, min(a1, char_bounds[1]) - max(a0, char_bounds[0]))
        iy = max(0.0, min(b1, char_bounds[3]) - max(b0, char_bounds[2]))
        return ix * iy

    if overlap(x, y) <= 1e-8:
        return x, y
    dx, dy = fw * 0.045, fh * 0.045
    candidates = [
        (x - dx, y), (x + dx, y), (x, y - dy), (x, y + dy),
        (x - dx, y - dy), (x + dx, y - dy), (x - dx, y + dy), (x + dx, y + dy),
    ]
    safe_min_x, safe_max_x = min_x + half_w + fw * 0.015, max_x - half_w - fw * 0.015
    safe_min_y, safe_max_y = min_y + half_h + fh * 0.015, max_y - half_h - fh * 0.015
    ranked = []
    for cx, cy in candidates:
        cx = max(safe_min_x, min(safe_max_x, cx))
        cy = max(safe_min_y, min(safe_max_y, cy))
        ranked.append((overlap(cx, cy), (cx - x) ** 2 + (cy - y) ** 2, cx, cy))
    best = min(ranked, key=lambda item: (item[0], item[1]))
    return best[2], best[3]


def fit_lyric_object_to_camera(obj, frame_width, frame_height, safe_width=0.84, safe_height=0.76, max_animation_scale=1.22):
    """Scale and clamp lyric object to stay comfortably within camera bounds."""
    bpy.context.view_layer.update()
    dims = obj.dimensions
    width = max(float(dims.x), 1e-6)
    height = max(float(dims.y), 1e-6)
    anim_guard = max(1.0, float(max_animation_scale))
    limit_w = max(1e-5, float(frame_width) * safe_width / anim_guard)
    limit_h = max(1e-5, float(frame_height) * safe_height / anim_guard)
    factor = min(1.0, limit_w / width, limit_h / height)
    if factor < 1.0:
        obj.scale = obj.scale * factor
        bpy.context.view_layer.update()
    half_w = max(0.0, float(frame_width) * 0.5 - float(obj.dimensions.x) * 0.5)
    half_h = max(0.0, float(frame_height) * 0.5 - float(obj.dimensions.y) * 0.5)
    loc = obj.location.copy()
    loc.x = max(-half_w, min(half_w, loc.x))
    loc.y = max(-half_h, min(half_h, loc.y))
    obj.location = loc
    return factor
