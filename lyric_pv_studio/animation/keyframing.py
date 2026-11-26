"""Keyframe animation generation for scaling, rotation, and motion fx."""

import math

from ..core.layout import get_random_amount


def iter_action_fcurves(action):
    """Yield F-Curves from a Blender action across Blender 5.x layered and legacy APIs."""
    if action is None:
        return
    seen = set()
    layers = getattr(action, "layers", None)
    if layers:
        for layer in layers:
            for strip in getattr(layer, "strips", ()):
                for channelbag in getattr(strip, "channelbags", ()):
                    for fc in getattr(channelbag, "fcurves", ()):
                        fc_id = id(fc)
                        if fc_id not in seen:
                            seen.add(fc_id)
                            yield fc
    if not seen:
        for fc in getattr(action, "fcurves", ()):
            fc_id = id(fc)
            if fc_id not in seen:
                seen.add(fc_id)
                yield fc


def shift_action_keyframes(obj, delta_frames, seen_actions=None):
    """Shift all keyframes and Bezier handles of an object's action along the timeline."""
    delta = float(delta_frames)
    if abs(delta) < 1e-9:
        return False
    action = getattr(getattr(obj, "animation_data", None), "action", None)
    if action is None:
        return False
    if seen_actions is not None:
        action_key = action.as_pointer() if hasattr(action, "as_pointer") else id(action)
        if action_key in seen_actions:
            return False
        seen_actions.add(action_key)
    shifted = False
    for fc in iter_action_fcurves(action):
        for kp in getattr(fc, "keyframe_points", ()):
            kp.co.x += delta
            if hasattr(kp, "handle_left"):
                kp.handle_left.x += delta
            if hasattr(kp, "handle_right"):
                kp.handle_right.x += delta
            shifted = True
        if hasattr(fc, "update"):
            try:
                fc.update()
            except (AttributeError, RuntimeError):
                pass
    return shifted


def smooth_action_fcurves(obj, interpolation="BEZIER", handle_type="AUTO_CLAMPED"):
    """将物体当前动画动作的所有关键帧曲线统一设置为指定插值与手柄类型，防止过冲。"""
    action = getattr(getattr(obj, "animation_data", None), "action", None)
    if not action:
        return
    try:
        for fc in iter_action_fcurves(action):
            for key in fc.keyframe_points:
                if getattr(fc, "data_path", "") in {"hide_render", "hide_viewport"}:
                    key.interpolation = "CONSTANT"
                    continue
                key.interpolation = interpolation
                key.handle_left_type = handle_type
                key.handle_right_type = handle_type
    except (AttributeError, TypeError):
        pass


def key_object_scale(obj, frame_in, frame_out, fade, pop_enabled):
    """Insert Bezier scale keyframes for pop-in and fade-out."""
    base = obj.scale.copy()
    hidden = base * 0.001
    obj.scale = hidden if pop_enabled else base
    obj.keyframe_insert(data_path="scale", frame=frame_in)
    if pop_enabled:
        obj.scale = base
        obj.keyframe_insert(data_path="scale", frame=min(frame_in + max(2, fade), frame_out - 1))
    if fade > 0 and frame_out - fade > frame_in:
        obj.keyframe_insert(data_path="scale", frame=frame_out - fade)
        obj.scale = hidden
        obj.keyframe_insert(data_path="scale", frame=frame_out)
    else:
        obj.scale = base
        obj.keyframe_insert(data_path="scale", frame=frame_out)
    smooth_action_fcurves(obj)


def key_glyph_reveal(obj, frame_in, pop_y=0.0, pop_z=0.0, pop_frames=4):
    """Reveal one glyph on its own timing without scaling the glyph independently."""
    frame_in = int(frame_in)
    first_frame = frame_in - 1
    obj.hide_render = True
    obj.hide_viewport = True
    obj.keyframe_insert(data_path="hide_render", frame=first_frame)
    obj.keyframe_insert(data_path="hide_viewport", frame=first_frame)
    obj.hide_render = False
    obj.hide_viewport = False
    obj.keyframe_insert(data_path="hide_render", frame=frame_in)
    obj.keyframe_insert(data_path="hide_viewport", frame=frame_in)

    if abs(float(pop_y)) > 1e-8 or abs(float(pop_z)) > 1e-8:
        base = obj.location.copy()
        obj.location = (base.x, base.y + float(pop_y), base.z + float(pop_z))
        obj.keyframe_insert(data_path="location", frame=frame_in)
        obj.location = base
        obj.keyframe_insert(
            data_path="location",
            frame=frame_in + max(2, int(pop_frames)),
        )

    action = getattr(getattr(obj, "animation_data", None), "action", None)
    if action:
        try:
            for curve in iter_action_fcurves(action):
                if curve.data_path in {"hide_render", "hide_viewport"}:
                    for key in curve.keyframe_points:
                        key.interpolation = "CONSTANT"
                elif curve.data_path == "location":
                    for key in curve.keyframe_points:
                        key.interpolation = "BEZIER"
                        key.handle_left_type = "AUTO_CLAMPED"
                        key.handle_right_type = "AUTO_CLAMPED"
        except (AttributeError, TypeError):
            pass


def apply_text_animation(obj, record, frame_in, frame_out, props, rng):
    """Apply motion and rotation keyframes based on the selected animation scheme."""
    mode = record.get("animation", "SLIDE")
    strength = max(0.0, min(1.0, float(props.animation_intensity) / 100.0)) * get_random_amount(props)
    base_scale = obj.scale.copy()
    base_rotation = obj.rotation_euler.copy()
    reveal = max(2, min(12, int((frame_out - frame_in) * 0.12)))
    end_in = min(frame_out, frame_in + reveal)
    if mode in {"ROTATE", "BOUNCE", "FLOAT", "GLITCH"}:
        obj.rotation_euler.z = base_rotation.z + math.radians((18.0 if rng.random() > 0.5 else -18.0) * strength)
        obj.keyframe_insert(data_path="rotation_euler", frame=frame_in)
        obj.rotation_euler = base_rotation
        obj.keyframe_insert(data_path="rotation_euler", frame=end_in)
    if mode == "BOUNCE":
        obj.rotation_euler.z = base_rotation.z + math.radians(3.0 * strength)
        obj.keyframe_insert(data_path="rotation_euler", frame=min(frame_in + max(2, reveal // 2), frame_out))
        obj.rotation_euler = base_rotation
        obj.keyframe_insert(data_path="rotation_euler", frame=end_in)
    if mode == "FLOAT":
        mid = min(frame_out - 1, frame_in + max(3, (frame_out - frame_in) // 2))
        obj.rotation_euler.z = base_rotation.z + math.radians(1.5 * strength)
        obj.keyframe_insert(data_path="rotation_euler", frame=mid)
        obj.rotation_euler = base_rotation
        obj.keyframe_insert(data_path="rotation_euler", frame=frame_out)
    smooth_action_fcurves(obj)
