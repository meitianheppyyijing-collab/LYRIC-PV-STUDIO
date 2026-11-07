"""Blender Operators for importing, generating, rerolling, and clearing lyrics."""

import json
import math
import random

import bpy
from bpy.types import Operator

from ..animation.keyframing import apply_text_animation, key_glyph_reveal, key_object_scale
from ..animation.runtime import invalidate_entrance_cache, update_lyric_entrance_positions
from .callbacks import update_lyric_positions
from ..blender.collections import (
    get_or_create_collection,
    remove_generated_collection,
    remove_legacy_generated_background,
)
from ..blender.materials import make_text_material
from ..constants import PV_ROOT_NAME, PV_TAG
from ..core.layout import load_layout_records, reroll_layout_records
from ..core.parser import (
    estimate_lyric_unit_advance,
    lyric_display_units,
    parse_lrc_text,
    parse_yrc_text,
    read_lyric_file,
    yrc_character_frame_map,
)
from ..core.spatial import (
    camera_frame_bounds,
    fit_lyric_object_to_camera,
    get_occlusion_safe_distance,
    nudge_lyric_away_from_character,
)


class LYRICPV_OT_import_lrc(Operator):
    bl_idname = "lyric_pv.import_lrc"
    bl_label = "导入 LRC"
    bl_description = "单独导入普通 LRC 整句时间歌词"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.lyric_pv_props
        path = bpy.path.abspath(props.lrc_path)
        if not path or not path.lower().endswith(".lrc"):
            self.report({"ERROR"}, "请选择 .lrc 文件。")
            return {"CANCELLED"}
        try:
            content = read_lyric_file(path)
            entries, offset_ms = parse_lrc_text(content)
        except Exception as exc:
            self.report({"ERROR"}, f"无法读取 LRC 文件：{exc}")
            return {"CANCELLED"}
        if not entries:
            self.report({"ERROR"}, "没有找到带时间戳的 LRC 歌词。")
            return {"CANCELLED"}
        scene = context.scene
        scene["lyric_pv_entries"] = json.dumps([[float(t), lyric] for t, lyric in entries], ensure_ascii=False)
        scene["lyric_pv_yrc_entries"] = "[]"
        scene["lyric_pv_source"] = path
        scene["lyric_pv_source_format"] = "LRC"
        scene["lyric_pv_file_offset_ms"] = int(offset_ms)
        props.generated_count = len(entries)
        self.report({"INFO"}, f"已导入 {len(entries)} 句 LRC 歌词。")
        return {"FINISHED"}


class LYRICPV_OT_import_yrc(Operator):
    bl_idname = "lyric_pv.import_yrc"
    bl_label = "导入 YRC"
    bl_description = "导入 YRC 歌词并保留逐字时间信息"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.lyric_pv_props
        path = bpy.path.abspath(props.yrc_path)
        if not path or not path.lower().endswith(".yrc"):
            self.report({"ERROR"}, "请选择 .yrc 文件。")
            return {"CANCELLED"}
        try:
            content = read_lyric_file(path)
            entries, timed_entries = parse_yrc_text(content)
        except Exception as exc:
            self.report({"ERROR"}, f"无法读取 YRC 文件：{exc}")
            return {"CANCELLED"}
        if not entries:
            self.report({"ERROR"}, "没有识别到此格式的 YRC 歌词。")
            return {"CANCELLED"}
        scene = context.scene
        scene["lyric_pv_entries"] = json.dumps([[float(t), lyric] for t, lyric in entries], ensure_ascii=False)
        scene["lyric_pv_yrc_entries"] = json.dumps(timed_entries, ensure_ascii=False)
        scene["lyric_pv_source"] = path
        scene["lyric_pv_source_format"] = "YRC"
        scene["lyric_pv_file_offset_ms"] = 0
        props.generated_count = len(entries)
        token_count = sum(len(item["tokens"]) for item in timed_entries)
        self.report({"INFO"}, f"已导入 {len(entries)} 句 YRC 歌词，保留 {token_count} 段逐字时间。")
        return {"FINISHED"}


class LYRICPV_OT_generate(Operator):
    bl_idname = "lyric_pv.generate"
    bl_label = "生成歌词 PV"
    bl_description = "生成逐字排版、弹入、淡入淡出与空间入场动画"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        props = scene.lyric_pv_props
        raw_entries = scene.get("lyric_pv_entries", "")
        if not raw_entries:
            self.report({"ERROR"}, "请先导入 LRC 歌词文件。")
            return {"CANCELLED"}
        try:
            decoded = json.loads(raw_entries) if isinstance(raw_entries, str) else raw_entries
            entries = [(float(item[0]), str(item[1])) for item in decoded]
        except (TypeError, ValueError, IndexError, json.JSONDecodeError) as exc:
            self.report({"ERROR"}, f"歌词数据无效，请重新导入 LRC：{exc}")
            return {"CANCELLED"}
        if not entries:
            self.report({"ERROR"}, "没有可用的歌词，请重新导入 LRC。")
            return {"CANCELLED"}
        camera = props.target_camera or scene.camera
        if camera is None or camera.type != "CAMERA" or camera.name not in scene.objects:
            self.report({"ERROR"}, "请选择当前场景中的有效摄像机。")
            return {"CANCELLED"}

        entries.sort(key=lambda item: item[0])
        source_format = str(scene.get("lyric_pv_source_format", "LRC")).upper()
        try:
            yrc_timed_entries = json.loads(scene.get("lyric_pv_yrc_entries", "[]")) if source_format == "YRC" else []
        except (TypeError, ValueError, json.JSONDecodeError):
            yrc_timed_entries = []
        # Match YRC records to sentence order; LRC keeps its original sentence timing.
        yrc_timing_by_text = {}
        if source_format == "YRC":
            for timed in yrc_timed_entries:
                if isinstance(timed, dict):
                    yrc_timing_by_text.setdefault(str(timed.get("text", "")), []).append(timed)
        layouts = load_layout_records(scene, entries, props)
        remove_generated_collection()
        remove_legacy_generated_background()
        collection = get_or_create_collection(scene)
        material = make_text_material("LPV_Text_Material", props.text_color, props.glow_strength)

        glitch_mats = {}
        if props.glitch_enabled:
            glitch_mats["C"] = make_text_material("LPV_Glitch_Mat_C", (0.1, 0.85, 1.0, 1.0), max(0.6, props.glow_strength))
            glitch_mats["M"] = make_text_material("LPV_Glitch_Mat_M", (1.0, 0.12, 0.48, 1.0), max(0.6, props.glow_strength))

        font = None
        if props.font_path:
            try:
                font = bpy.data.fonts.load(bpy.path.abspath(props.font_path), check_existing=True)
            except Exception as exc:
                self.report({"WARNING"}, f"字体加载失败，改用默认字体：{exc}")

        fps = scene.render.fps / scene.render.fps_base
        start_frame = scene.frame_start
        distance = get_occlusion_safe_distance(scene, camera, props)
        min_x, max_x, min_y, max_y = camera_frame_bounds(scene, camera, distance)
        frame_width, frame_height = max_x - min_x, max_y - min_y
        controller = bpy.data.objects.new("LPV_字幕位置控制器", None)
        collection.objects.link(controller)
        controller.empty_display_type = "PLAIN_AXES"
        controller.empty_display_size = 0.12
        controller.parent = camera
        controller.location = (min_x + frame_width * (props.display_x + 0.5), min_y + frame_height * (props.display_y + 0.5), -distance)
        controller.scale = (1.0, 1.0, 1.0)
        controller["lyric_base_distance"] = float(distance)
        controller[PV_TAG] = True
        controller["lyric_pv_controller"] = True
        controller.hide_render = True
        if props.hide_lyrics_in_viewport:
            controller.hide_set(True, view_layer=context.view_layer)

        created = 0
        content_bounds = [float('inf'), float('-inf'), float('inf'), float('-inf')]
        for index, (seconds, lyric) in enumerate(entries):
            if not lyric.strip():
                continue
            record = layouts[str(index)]
            next_seconds = entries[index + 1][0] if index + 1 < len(entries) else seconds + props.hold_gap
            start_seconds = max(0.0, seconds + props.time_offset)
            end_seconds = max(start_seconds + 0.05, next_seconds + props.time_offset)
            frame_in = start_frame + round(start_seconds * fps)
            frame_out = max(frame_in + 1, start_frame + round(end_seconds * fps))
            fade = min(props.fade_frames, max(0, (frame_out - frame_in) // 2))
            style = record["style"]
            center_aligned_styles = {"CLEAN_CENTER", "VERTICAL", "DIAGONAL", "WIDE_SPACING", "PER_CHARACTER", "EMPHASIS"}
            if props.layout_alignment == "CENTER" and style in center_aligned_styles:
                record = dict(record)
                record["x"] = 0.0
                record["rotation"] = 0.0
            # PV-style placement: each lyric line gets a deterministic, varied
            # camera-local position. Keep a generous safe margin; final text-fit
            # and character-occlusion checks below still clamp/nudge the result.
            # This applies identically to LRC and YRC because both use this generator.
            if props.random_layout_enabled:
                record = dict(record)
                pos_rng = random.Random(int(props.random_seed) + index * 104729 + 31)
                # Avoid repeatedly pinning every line to the exact screen centre.
                x_choices = (-0.34, -0.22, 0.22, 0.34)
                y_choices = (-0.27, -0.16, 0.16, 0.27)
                record["x"] = pos_rng.choice(x_choices) * frame_width
                record["y"] = pos_rng.choice(y_choices) * frame_height
                # Small per-line variation makes consecutive lines feel less templated.
                record["x"] += pos_rng.uniform(-0.035, 0.035) * frame_width
                record["y"] += pos_rng.uniform(-0.025, 0.025) * frame_height
            # 副歌/段落位置交替（可选）：position_cycle > 0 时每 N 句上下交替
            cycle = int(props.position_cycle)
            extra_y = 0.0
            if cycle > 0 and (index // cycle) % 2 == 1:
                extra_y += float(props.chorus_y_offset)
            multiplier = float(record["font_multiplier"])
            base_size = float(props.font_size) * multiplier
            effective_spacing = max(1.05, min(1.35, float(record.get("spacing", 1.0))))
            direction = "NONE" if record["animation"] == "FADE" else record["entrance"]
            reveal_enabled = bool(props.character_pop or record["animation"] in {"POP", "FADE"})
            pop_motion = bool(props.character_pop or record["animation"] == "POP")
            # LRC and YRC share the same layout/animation controls. YRC timing
            # only drives per-character reveal when the selected layout is per-character;
            # ordinary layouts keep the entire sentence in one FONT object.
            per_char = style in {"PER_CHARACTER", "EMPHASIS"}
            yrc_timing = None
            if source_format == "YRC":
                candidates = yrc_timing_by_text.get(lyric, [])
                if candidates:
                    yrc_timing = candidates.pop(0)
            yrc_char_frames = yrc_character_frame_map(yrc_timing, fps, start_frame, props.time_offset) if yrc_timing else []
            glyphs = []
            line_fit = 1.0
            if per_char:
                display_units = lyric_display_units(lyric)
                # The sentence group owns whole-line scale and camera entrance;
                # glyphs keep their own timing, visibility, and rotation animation.
                sentence_group = bpy.data.objects.new(
                    f"LPV_Lyric_{index+1:03d}_Sentence",
                    None,
                )
                collection.objects.link(sentence_group)
                sentence_group.empty_display_type = "PLAIN_AXES"
                sentence_group.empty_display_size = 0.01
                sentence_group.parent = controller
                sentence_group.location = (0.0, 0.0, 0.0)
                sentence_group.scale = (1.0, 1.0, 1.0)
                sentence_group[PV_TAG] = True
                sentence_group["lyric_sentence_group"] = True
                sentence_group["lyric_index"] = index
                # Create all glyph objects first, then evaluate the view layer once.
                for ci, (unit_text, source_char_index) in enumerate(display_units):
                    cu = bpy.data.curves.new(f"LPV_Lyric_{index+1:03d}_{ci+1:03d}_Curve", type="FONT")
                    cu.body = unit_text if unit_text.strip() else " "
                    cu.size = base_size
                    cu.align_x = "LEFT"
                    cu.align_y = "CENTER"
                    cu.extrude = props.text_extrude
                    cu.bevel_depth = props.text_bevel
                    cu.space_character = effective_spacing
                    if font:
                        cu.font = font
                    ob = bpy.data.objects.new(f"LPV_Lyric_{index+1:03d}_Glyph_{ci+1:03d}", cu)
                    collection.objects.link(ob)
                    ob.parent = sentence_group
                    ob.data.materials.append(material)
                    ob[PV_TAG] = True
                    glyphs.append((ob, 0.0, ci, 0.0))
                bpy.context.view_layer.update()
                cursor = 0.0
                measured_glyphs = []
                depsgraph = context.evaluated_depsgraph_get()
                for ob, _cursor_x, ci, _width in glyphs:
                    unit_text = display_units[ci][0]
                    try:
                        evaluated = ob.evaluated_get(depsgraph)
                        measured_width = float(evaluated.dimensions.x)
                    except Exception:
                        measured_width = 0.0
                    estimated_width = estimate_lyric_unit_advance(unit_text, base_size)
                    minimum_width = estimated_width * 0.72
                    width = measured_width if measured_width >= minimum_width else estimated_width
                    width = max(width, base_size * 0.18)
                    measured_glyphs.append((ob, cursor, ci, width, display_units[ci][1]))
                    lrc_emphasis_scale = 1.35 if source_format == "LRC" and style == "EMPHASIS" and ci == 0 else 1.0
                    advance_width = width * lrc_emphasis_scale
                    gap = max(base_size * 0.075, advance_width * 0.10) * effective_spacing
                    current_is_space = display_units[ci][0].isspace()
                    next_is_space = (ci + 1 < len(display_units) and display_units[ci + 1][0].isspace())
                    has_space = current_is_space or next_is_space
                    cursor += advance_width + (gap if ci < len(display_units) - 1 and not has_space else 0.0)
                glyphs = measured_glyphs
                total_width = cursor
                animation_peak = 1.18 if record.get("animation") in {"POP", "BOUNCE"} else 1.04 if record.get("animation") == "GLITCH" else 1.0
                emphasis_peak = 1.35 if style == "EMPHASIS" else 1.0
                peak_scale = animation_peak * emphasis_peak
                fit = min(1.0, (frame_width * 0.84) / (max(total_width, 1e-6) * peak_scale), (frame_height * 0.76) / (max(base_size, 1e-6) * peak_scale))
                line_fit = fit
                start_x = -total_width * fit * 0.5
                for ob, cursor_x, ci, width, source_char_index in glyphs:
                    bx = start_x + cursor_x * fit
                    scale_factor = 1.35 if style == "EMPHASIS" and ci == 0 else 1.0
                    ob.scale = (fit * scale_factor, fit * scale_factor, fit * scale_factor)
                    ob.location = (bx, 0.0, 0.0)
                    ob.rotation_euler.z = math.radians(float(record["rotation"]))
                    ob["lyric_font_multiplier"] = multiplier
                    ob["lyric_index"] = index
                    ob["lyric_text"] = lyric
                    if yrc_char_frames and source_char_index < len(yrc_char_frames):
                        char_frame_in = max(frame_in, min(frame_out - 1, int(yrc_char_frames[source_char_index])))
                    else:
                        char_frame_in = int(frame_in + (ci * props.character_stagger if reveal_enabled else 0))
                    ob["lyric_character_frame_in"] = char_frame_in
                    char_start = int(char_frame_in)
                    key_glyph_reveal(
                        ob,
                        char_start,
                        pop_y=-base_size * 0.22 if pop_motion else 0.0,
                        pop_z=props.spatial_depth if pop_motion else 0.0,
                        pop_frames=max(2, fade),
                    )
                    apply_text_animation(ob, record, char_start, frame_out, props, random.Random(int(props.random_seed) + index * 997 + ci))
                    created += 1
                group_center_x = float(record["x"])
                max_center_x = max(0.0, frame_width * 0.5 - total_width * fit * 0.5 - frame_width * 0.06)
                group_center_x = max(-max_center_x, min(max_center_x, group_center_x))
                group_y = max(-frame_height * 0.18, min(frame_height * 0.18, float(record["y"]) + extra_y))
                group_center_x, group_y = nudge_lyric_away_from_character(
                    scene, camera, props,
                    min_x + frame_width * 0.5 + group_center_x,
                    min_y + frame_height * 0.5 + group_y,
                    total_width * fit, base_size * fit, distance,
                    (min_x, max_x, min_y, max_y),
                )
                group_center_x -= min_x + frame_width * 0.5
                group_y -= min_y + frame_height * 0.5
                sentence_group.location = (group_center_x, group_y, 0.0)
                bound_w = total_width * fit
                bound_h = base_size * fit * 1.25
                angle = math.radians(float(record["rotation"]))
                rotated_w = abs(bound_w * math.cos(angle)) + abs(bound_h * math.sin(angle))
                rotated_h = abs(bound_w * math.sin(angle)) + abs(bound_h * math.cos(angle))
                content_bounds[0] = min(content_bounds[0], group_center_x - rotated_w * 0.5)
                content_bounds[1] = max(content_bounds[1], group_center_x + rotated_w * 0.5)
                content_bounds[2] = min(content_bounds[2], group_y - rotated_h * 0.5)
                content_bounds[3] = max(content_bounds[3], group_y + rotated_h * 0.5)
                sentence_group["lyric_base_x"] = float(group_center_x)
                sentence_group["lyric_base_y"] = float(group_y)
                sentence_group["lyric_base_z"] = 0.0
                sentence_group["lyric_entrance_enabled"] = True
                sentence_group["lyric_entrance_direction"] = direction
                sentence_group["lyric_frame_in"] = int(frame_in)
                sentence_group["lyric_frame_out"] = int(frame_out)
                sentence_group["lyric_fade_frames"] = int(fade)
                sentence_group["lyric_pop_enabled"] = False
                key_object_scale(sentence_group, frame_in, frame_out, fade, reveal_enabled)
                for ob, cursor_x, ci, width, source_char_index in glyphs:
                    ob.location.x = start_x + cursor_x * fit
                    ob.location.y = 0.0
            else:
                cu = bpy.data.curves.new(f"LPV_Lyric_{index+1:03d}_Curve", type="FONT")
                cu.body = lyric
                cu.size = base_size
                cu.align_x = {
                    "CLEAN_CENTER": "CENTER",
                    "LEFT_TITLE": "LEFT",
                    "RIGHT_TITLE": "RIGHT",
                    "VERTICAL": "CENTER",
                    "DIAGONAL": "CENTER",
                    "WIDE_SPACING": "CENTER",
                }.get(style, props.layout_alignment)
                cu.align_y = "CENTER"
                cu.extrude = props.text_extrude
                cu.bevel_depth = props.text_bevel
                cu.space_character = effective_spacing
                if style == "VERTICAL":
                    cu.body = "\n".join(list(lyric))
                if font:
                    cu.font = font
                ob = bpy.data.objects.new(f"LPV_Lyric_{index+1:03d}_Line", cu)
                collection.objects.link(ob)
                ob.parent = controller
                ob.data.materials.append(material)
                ob[PV_TAG] = True
                ob["lyric_index"] = index
                ob["lyric_text"] = lyric
                ob["lyric_font_multiplier"] = multiplier
                ob["lyric_base_x"] = float(record["x"])
                ob["lyric_base_y"] = float(record["y"]) + extra_y
                ob["lyric_base_z"] = 0.0
                safe_x = max(-frame_width * 0.16, min(frame_width * 0.16, float(record["x"])))
                safe_y = max(-frame_height * 0.16, min(frame_height * 0.16, float(record["y"]) + extra_y))
                ob.location = (safe_x, safe_y, 0.0)
                ob.rotation_euler.z = math.radians(float(record["rotation"]))
                animation_peak = 1.18 if record.get("animation") in {"POP", "BOUNCE"} else 1.04 if record.get("animation") == "GLITCH" else 1.0
                line_fit = fit_lyric_object_to_camera(ob, frame_width, frame_height, max_animation_scale=animation_peak)
                abs_x, abs_y = nudge_lyric_away_from_character(
                    scene, camera, props,
                    min_x + frame_width * 0.5 + float(ob.location.x),
                    min_y + frame_height * 0.5 + float(ob.location.y),
                    max(float(ob.dimensions.x), base_size * 0.12),
                    max(float(ob.dimensions.y), base_size * 0.12),
                    distance, (min_x, max_x, min_y, max_y),
                )
                ob.location.x = abs_x - (min_x + frame_width * 0.5)
                ob.location.y = abs_y - (min_y + frame_height * 0.5)
                ob["lyric_base_x"] = float(ob.location.x)
                half_w = max(float(ob.dimensions.x), base_size * 0.12) * 0.5
                half_h = max(float(ob.dimensions.y), base_size * 0.12) * 0.5
                content_bounds[0] = min(content_bounds[0], float(ob.location.x) - half_w)
                content_bounds[1] = max(content_bounds[1], float(ob.location.x) + half_w)
                content_bounds[2] = min(content_bounds[2], float(ob.location.y) - half_h)
                content_bounds[3] = max(content_bounds[3], float(ob.location.y) + half_h)
                ob["lyric_entrance_enabled"] = True
                ob["lyric_entrance_direction"] = direction
                ob["lyric_frame_in"] = int(frame_in)
                ob["lyric_frame_out"] = int(frame_out)
                ob["lyric_fade_frames"] = int(fade)
                ob["lyric_pop_enabled"] = reveal_enabled
                ob["lyric_pop_frames"] = max(2, fade)
                ob["lyric_pop_y"] = -base_size * 0.22 if pop_motion else 0.0
                ob["lyric_pop_z"] = props.spatial_depth if pop_motion else 0.0
                key_object_scale(ob, frame_in, frame_out, fade, reveal_enabled)
                line_rng = random.Random(int(props.random_seed) + index * 997)
                apply_text_animation(ob, record, frame_in, frame_out, props, line_rng)
                created += 1
            if props.glitch_enabled:
                for suffix, color, sign in (("C", (0.1, 0.85, 1.0, 1.0), -1.0), ("M", (1.0, 0.12, 0.48, 1.0), 1.0)):
                    gc = bpy.data.curves.new(f"LPV_Glitch_{index+1:03d}_{suffix}_Curve", type="FONT")
                    gc.body = lyric
                    gc.size = base_size
                    gc.align_x = "CENTER"
                    gc.align_y = "CENTER"
                    if font:
                        gc.font = font
                    go = bpy.data.objects.new(f"LPV_Glitch_{index+1:03d}_{suffix}", gc)
                    collection.objects.link(go)
                    go.parent = controller
                    go.data.materials.append(glitch_mats[suffix])
                    go.location = (float(record["x"]) + sign * props.glitch_strength, float(record["y"]) + extra_y, -0.002)
                    go.scale = (0.001, 0.001, 0.001)
                    go[PV_TAG] = True
                    go["lyric_glitch_overlay"] = True
                    go.keyframe_insert(data_path="scale", frame=max(frame_in - 1, scene.frame_start))
                    go.scale = (line_fit, line_fit, line_fit)
                    go.keyframe_insert(data_path="scale", frame=frame_in)
                    go.keyframe_insert(data_path="scale", frame=min(frame_in + 2, frame_out))
                    go.scale = (0.001, 0.001, 0.001)
                    go.keyframe_insert(data_path="scale", frame=min(frame_in + 3, frame_out))
                    created += 1
        if all(math.isfinite(value) for value in content_bounds):
            controller["lyric_content_bounds"] = [float(value) for value in content_bounds]
        props.generated_count = len(entries)
        invalidate_entrance_cache()
        update_lyric_positions(props, context)
        update_lyric_entrance_positions(scene)
        scene["lyric_pv_layouts"] = json.dumps(layouts, ensure_ascii=False, sort_keys=True)
        self.report({"INFO"}, f"已生成 {len(entries)} 句歌词（{created} 个文字对象），集合：{PV_ROOT_NAME}。")
        return {"FINISHED"}


class LYRICPV_OT_reroll_all(Operator):
    bl_idname = "lyric_pv.reroll_all"
    bl_label = "重抽未锁定歌词排版"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        props = scene.lyric_pv_props
        if not scene.get("lyric_pv_entries"):
            self.report({"WARNING"}, "请先导入歌词并生成一次排版。")
            return {"CANCELLED"}
        reroll_layout_records(scene, props)
        bpy.ops.lyric_pv.generate()
        return {"FINISHED"}


class LYRICPV_OT_reroll_one(Operator):
    bl_idname = "lyric_pv.reroll_one"
    bl_label = "重抽指定句"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        props = scene.lyric_pv_props
        idx = int(props.layout_line_index) - 1
        try:
            records = json.loads(scene.get("lyric_pv_layouts", "{}"))
        except Exception:
            records = {}
        if str(idx) not in records:
            self.report({"WARNING"}, "该句尚无排版记录，请先生成一次。")
            return {"CANCELLED"}
        if records[str(idx)].get("locked", False):
            self.report({"WARNING"}, "该句已锁定，请先解锁。")
            return {"CANCELLED"}
        reroll_layout_records(scene, props, [idx])
        bpy.ops.lyric_pv.generate()
        return {"FINISHED"}


class LYRICPV_OT_toggle_lock(Operator):
    bl_idname = "lyric_pv.toggle_lock"
    bl_label = "锁定/解锁指定句"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        idx = int(scene.lyric_pv_props.layout_line_index) - 1
        try:
            records = json.loads(scene.get("lyric_pv_layouts", "{}"))
        except Exception:
            records = {}
        rec = records.get(str(idx))
        if rec is None:
            self.report({"WARNING"}, "该句尚无排版记录，请先生成一次。")
            return {"CANCELLED"}
        rec["locked"] = not bool(rec.get("locked", False))
        scene["lyric_pv_layouts"] = json.dumps(records, ensure_ascii=False, sort_keys=True)
        self.report({"INFO"}, "已锁定该句。" if rec["locked"] else "已解锁该句。")
        return {"FINISHED"}


class LYRICPV_OT_clear(Operator):
    bl_idname = "lyric_pv.clear"
    bl_label = "清除已生成内容"
    bl_description = "仅删除 LYRIC PV STUDIO 创建的对象和数据"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        props = scene.lyric_pv_props

        # Remove generated scene objects and legacy generated background.
        removed = remove_generated_collection()
        legacy_background_removed = remove_legacy_generated_background()

        # Clear imported lyric payload and all per-import layout/source metadata.
        lyric_keys = (
            "lyric_pv_entries",
            "lyric_pv_yrc_entries",
            "lyric_pv_source",
            "lyric_pv_source_format",
            "lyric_pv_file_offset_ms",
            "lyric_pv_layouts",
            "lyric_pv_reroll",
        )
        cleared = 0
        for key in lyric_keys:
            if key in scene:
                del scene[key]
                cleared += 1

        # Reset file selectors and visible counters as well.
        props.lrc_path = ""
        props.yrc_path = ""
        props.generated_count = 0

        # Drop cached object references so a later generation cannot reuse stale data.
        invalidate_entrance_cache()
        if removed or legacy_background_removed or cleared:
            self.report({"INFO"}, "已彻底清理：生成内容、LRC/YRC 歌词、逐字时间、排版记录和导入路径。")
        else:
            self.report({"INFO"}, "歌词项目已经是空的，无需清理。")
        return {"FINISHED"}
