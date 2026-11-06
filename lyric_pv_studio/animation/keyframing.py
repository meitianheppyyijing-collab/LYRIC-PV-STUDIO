"""Keyframe animation generation for scaling, rotation, and motion fx."""

import math

from ..core.layout import _random_amount


def _key_object_scale(obj, frame_in, frame_out, fade, pop_enabled):
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
    action = obj.animation_data.action if obj.animation_data else None
    if action:
        try:
            for fc in action.fcurves:
                for key in fc.keyframe_points:
                    key.interpolation = "BEZIER"
                    key.handle_left_type = "AUTO_CLAMPED"
                    key.handle_right_type = "AUTO_CLAMPED"
        except (AttributeError, TypeError):
            pass


def apply_text_animation(obj, record, frame_in, frame_out, props, rng):
    """Apply motion and rotation keyframes based on the selected animation scheme."""
    mode = record.get("animation", "SLIDE")
    strength = max(0.0, min(1.0, float(props.animation_intensity) / 100.0)) * _random_amount(props)
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
    # ELECTRIC 已移除：不再每句复制材质做发光脉冲
    action = obj.animation_data.action if obj.animation_data else None
    if action:
        try:
            for fc in action.fcurves:
                for key in fc.keyframe_points:
                    key.interpolation = "BEZIER"
                    key.handle_left_type = "AUTO_CLAMPED"
                    key.handle_right_type = "AUTO_CLAMPED"
        except (AttributeError, TypeError):
            pass
