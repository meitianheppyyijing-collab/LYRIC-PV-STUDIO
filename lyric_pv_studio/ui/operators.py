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
from ..blender.geometry_nodes import (
    attach_lyric_solidify_modifier,
    get_or_create_lyric_solidify_node_group,
)
from ..blender.materials import (
    make_outline_material,
    make_text_material,
    make_three_state_text_material,
)
from ..constants import PV_ROOT_NAME, PV_TAG
from ..core.document import (
    LyricDocument,
    clear_lyric_document,
    get_lyric_document,
    save_lyric_document,
)
from ..core.layout import load_layout_records, reroll_layout_records
from ..core.parser import (
    detect_lyric_format,
    estimate_lyric_unit_advance,
    parse_lrc_text,
    parse_srt_text,
    parse_yrc_text,
    read_lyric_file,
)
from ..core.spatial import (
    camera_frame_bounds,
    get_occlusion_safe_distance,
    nudge_lyric_away_from_character,
)


def _hex_to_rgba(hex_color):
    raw = str(hex_color or "").lstrip("#")
    if len(raw) != 6:
        return (1.0, 1.0, 1.0, 1.0)
    try:
        return (
            int(raw[0:2], 16) / 255.0,
            int(raw[2:4], 16) / 255.0,
            int(raw[4:6], 16) / 255.0,
            1.0,
        )
    except ValueError:
        return (1.0, 1.0, 1.0, 1.0)


def _apply_font_formatting(curve, line):
    if line.italic:
        curve.shear = 0.2
    if not (line.bold or line.italic or line.underline):
        return
    for char_fmt in getattr(curve, "body_format", ()):
        if line.bold:
            char_fmt.use_bold = True
        if line.italic:
            char_fmt.use_italic = True
        if line.underline:
            char_fmt.use_underline = True


class LYRICPV_OT_import_lyric(Operator):
    bl_idname = "lyric_pv.import_lyric"
    bl_label = "导入歌词 / 字幕"
    bl_description = "自动识别并导入 .lrc、.yrc 或 .srt 文件"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.lyric_pv_props
        path = bpy.path.abspath(props.lyric_path)
        fmt = detect_lyric_format(path)
        if not path or fmt is None:
            self.report({"ERROR"}, "请选择 .lrc、.yrc 或 .srt 文件。")
            return {"CANCELLED"}
        try:
            content = read_lyric_file(path)
        except Exception as exc:
            self.report({"ERROR"}, f"无法读取 {fmt} 文件：{exc}")
            return {"CANCELLED"}

        scene = context.scene
        if fmt == "LRC":
            entries, offset_ms = parse_lrc_text(content)
            if not entries:
                self.report({"ERROR"}, "没有找到带时间戳的 LRC 歌词。")
                return {"CANCELLED"}
            doc = LyricDocument.from_lrc_entries(entries, source_path=path, file_offset_ms=offset_ms)
            save_lyric_document(scene, doc)
            props.generated_count = doc.line_count
            self.report({"INFO"}, f"已导入 {doc.line_count} 句 LRC 歌词。")
            return {"FINISHED"}

        if fmt == "YRC":
            entries, timed_entries = parse_yrc_text(content)
            if not entries:
                self.report({"ERROR"}, "没有识别到此格式的 YRC 歌词。")
                return {"CANCELLED"}
            doc = LyricDocument.from_yrc_entries(entries, timed_entries, source_path=path)
            save_lyric_document(scene, doc)
            props.per_char_material_enabled = True
            props.generated_count = doc.line_count
            token_count = sum(len(item["tokens"]) for item in timed_entries)
            self.report({"INFO"}, f"已导入 {doc.line_count} 句 YRC 歌词，保留 {token_count} 段逐字时间。")
            return {"FINISHED"}

        cues = parse_srt_text(content)
        if not cues:
            self.report({"ERROR"}, "没有找到带时间轴的 SRT 字幕。")
            return {"CANCELLED"}
        doc = LyricDocument.from_srt_entries(cues, source_path=path)
        save_lyric_document(scene, doc)
        props.generated_count = doc.line_count
        self.report({"INFO"}, f"已导入 {doc.line_count} 条 SRT 字幕。")
        return {"FINISHED"}


class LYRICPV_OT_generate(Operator):
    bl_idname = "lyric_pv.generate"
    bl_label = "生成歌词 PV"
    bl_description = "生成逐字排版、弹入、淡入淡出与空间入场动画"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        props = scene.lyric_pv_props
        doc = get_lyric_document(scene)
        if doc is None or not doc.lines:
            self.report({"ERROR"}, "请先导入 LRC、YRC 或 SRT 文件。")
            return {"CANCELLED"}
        camera = props.target_camera or scene.camera
        if camera is None or camera.type != "CAMERA" or camera.name not in scene.objects:
            self.report({"ERROR"}, "请选择当前场景中的有效摄像机。")
            return {"CANCELLED"}

        entries = doc.to_entries()
        source_format = doc.source_format
        layouts = load_layout_records(scene, entries, props)
        # Preserve user-edited materials and shader/geometry node groups across regenerations.
        remove_generated_collection(purge_resources=False)
        remove_legacy_generated_background()
        collection = get_or_create_collection(scene)
        material, (g_before, g_singing, g_after) = make_three_state_text_material(
            before_group=props.shader_group_before,
            singing_group=props.shader_group_singing,
            after_group=props.shader_group_after,
            after_color=props.text_color,
            after_glow=props.glow_strength,
        )
        if props.shader_group_before != g_before:
            props.shader_group_before = g_before
        if props.shader_group_singing != g_singing:
            props.shader_group_singing = g_singing
        if props.shader_group_after != g_after:
            props.shader_group_after = g_after
        outline_material = make_outline_material()
        solidify_group = get_or_create_lyric_solidify_node_group(outline_material)
        per_char_mat_enabled = bool(props.per_char_material_enabled)
        transition_frames = max(0.0, float(props.material_transition_frames))
        color_materials = {}

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

        timeline = doc.get_timeline(
            fps=fps,
            start_frame=start_frame,
            time_offset=props.time_offset,
            hold_gap=props.hold_gap,
            fade_frames=props.fade_frames,
        )
        created = 0
        for line, timing in zip(doc.lines, timeline):
            index = line.index
            lyric = line.text
            if not lyric.strip():
                continue
            record = layouts[str(index)]
            frame_in = timing.frame_in
            frame_out = timing.frame_out
            fade = timing.fade_frames
            style = record["style"]
            has_explicit_placement = line.has_explicit_placement
            is_multiline = "\n" in lyric
            center_aligned_styles = {"CLEAN_CENTER", "VERTICAL", "DIAGONAL", "WIDE_SPACING", "PER_CHARACTER", "EMPHASIS"}
            if props.layout_alignment == "CENTER" and style in center_aligned_styles:
                record = dict(record)
                record["x"] = 0.0
                record["rotation"] = 0.0
            # PV-style placement: each lyric line gets a deterministic, varied
            # camera-local position unless explicit subtitle placement formatting
            # (e.g. SRT {\an1..9}) dictates where the cue belongs.
            if props.random_layout_enabled and not has_explicit_placement:
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
            if has_explicit_placement:
                record = dict(record)
                record["rotation"] = 0.0
                if line.align == "LEFT":
                    record["x"] = -frame_width * 0.34
                elif line.align == "RIGHT":
                    record["x"] = frame_width * 0.34
                elif line.align == "CENTER":
                    record["x"] = 0.0
                if line.valign == "TOP":
                    record["y"] = frame_height * 0.30
                elif line.valign == "MIDDLE":
                    record["y"] = 0.0
                elif line.valign == "BOTTOM":
                    record["y"] = -frame_height * 0.30
            # 副歌/段落位置交替（可选）：position_cycle > 0 时每 N 句上下交替
            cycle = int(props.position_cycle)
            extra_y = 0.0
            if cycle > 0 and not has_explicit_placement and (index // cycle) % 2 == 1:
                extra_y += float(props.chorus_y_offset)
            multiplier = float(record["font_multiplier"])
            base_size = float(props.font_size) * multiplier
            effective_spacing = max(1.05, min(1.35, float(record.get("spacing", 1.0))))
            direction = "NONE" if record["animation"] == "FADE" else record["entrance"]
            reveal_enabled = bool(props.character_pop or record["animation"] in {"POP", "FADE"})
            pop_motion = bool(props.character_pop or record["animation"] == "POP")
            line_material = material
            if line.color:
                if line.color not in color_materials:
                    mat_name = f"LPV_Text_Mat_{line.color.lstrip('#')}"
                    color_materials[line.color] = make_text_material(
                        mat_name, _hex_to_rgba(line.color), props.glow_strength
                    )
                line_material = color_materials[line.color]
            # Every layout style generates per-character glyph objects under a sentence
            # group so every lyric data object carries full per-character timing and
            # 3-state (before / singing / after) lyc_solidify parameters.
            kinetic_per_char = (style in {"PER_CHARACTER", "EMPHASIS"}) and not has_explicit_placement
            is_vertical = (style == "VERTICAL") and not has_explicit_placement and not is_multiline
            unit_frames = timing.unit_frames
            display_units = line.units
            line_fit = 1.0

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
            sentence_group.rotation_euler.z = math.radians(float(record["rotation"]))
            sentence_group[PV_TAG] = True
            sentence_group["lyric_sentence_group"] = True
            sentence_group["lyric_index"] = index
            sentence_group["lyric_text"] = lyric
            sentence_group["lyric_has_word_timing"] = bool(line.has_word_timing)

            # Create all glyph objects grouped by explicit line breaks, then evaluate once.
            row_glyphs = [[]]
            for ci, unit in enumerate(display_units):
                if unit.text == "\n":
                    row_glyphs.append([])
                    continue
                if unit_frames and ci < len(unit_frames):
                    char_frame_in = int(unit_frames[ci].frame_in)
                    char_frame_out = int(unit_frames[ci].frame_out)
                else:
                    char_frame_in = int(frame_in)
                    char_frame_out = int(frame_out)
                cu = bpy.data.curves.new(f"LPV_Lyric_{index+1:03d}_{ci+1:03d}_Curve", type="FONT")
                cu.body = unit.text if unit.text.strip() else " "
                cu.size = base_size
                cu.align_x = "LEFT"
                cu.align_y = "CENTER"
                cu.extrude = props.text_extrude
                cu.bevel_depth = props.text_bevel
                cu.space_character = effective_spacing
                if font:
                    cu.font = font
                _apply_font_formatting(cu, line)
                ob = bpy.data.objects.new(f"LPV_Lyric_{index+1:03d}_Glyph_{ci+1:03d}", cu)
                collection.objects.link(ob)
                ob.parent = sentence_group
                ob.data.materials.append(line_material)
                attach_lyric_solidify_modifier(
                    ob,
                    solidify_group,
                    outline_material,
                    per_char_enabled=per_char_mat_enabled,
                    char_frame_in=char_frame_in,
                    char_frame_out=char_frame_out,
                    transition_frames=transition_frames,
                )
                ob[PV_TAG] = True
                row_glyphs[-1].append((ob, 0.0, ci, 0.0, char_frame_in, char_frame_out))
            row_glyphs = [row for row in row_glyphs if row]
            bpy.context.view_layer.update()
            depsgraph = context.evaluated_depsgraph_get()
            first_glyph_ci = row_glyphs[0][0][2] if row_glyphs else 0
            gap_mult = 1.8 if style == "WIDE_SPACING" and not has_explicit_placement else 1.0

            measured_rows = []
            for row in row_glyphs:
                cursor = 0.0
                row_measured = []
                for row_pos, (ob, _cursor_x, ci, _width, c_in, c_out) in enumerate(row):
                    unit = display_units[ci]
                    unit_text = unit.text
                    try:
                        evaluated = ob.evaluated_get(depsgraph)
                        measured_width = float(evaluated.dimensions.x)
                    except Exception:
                        measured_width = 0.0
                    estimated_width = estimate_lyric_unit_advance(unit_text, base_size)
                    minimum_width = estimated_width * 0.72
                    width = measured_width if measured_width >= minimum_width else estimated_width
                    width = max(width, base_size * 0.18)
                    row_measured.append((ob, cursor, ci, width, unit.char_index, c_in, c_out))
                    emphasis_scale = 1.35 if source_format != "YRC" and style == "EMPHASIS" and ci == first_glyph_ci else 1.0
                    advance_width = width * emphasis_scale
                    gap = max(base_size * 0.075, advance_width * 0.10) * effective_spacing * gap_mult
                    current_is_space = unit.is_space
                    next_is_space = (row_pos + 1 < len(row) and display_units[row[row_pos + 1][2]].is_space)
                    has_space = current_is_space or next_is_space
                    cursor += advance_width + (gap if row_pos < len(row) - 1 and not has_space else 0.0)
                measured_rows.append((row_measured, cursor))

            if is_vertical:
                flat_glyphs = [item for row_m, _rw in measured_rows for item in row_m]
                total_width = max((item[3] for item in flat_glyphs), default=base_size)
                step_y = base_size * 1.15 * effective_spacing
                num_items = max(1, len(flat_glyphs))
                total_height = max(base_size, step_y * num_items)
            else:
                total_width = max((row_w for _, row_w in measured_rows), default=base_size)
                line_height = base_size * 1.25
                num_rows = max(1, len(measured_rows))
                total_height = max(base_size, line_height * num_rows)

            animation_peak = 1.18 if record.get("animation") in {"POP", "BOUNCE"} else 1.04 if record.get("animation") == "GLITCH" else 1.0
            emphasis_peak = 1.35 if style == "EMPHASIS" and not has_explicit_placement else 1.0
            peak_scale = animation_peak * emphasis_peak
            fit = min(
                1.0,
                (frame_width * 0.84) / (max(total_width, 1e-6) * peak_scale),
                (frame_height * 0.76) / (max(total_height, 1e-6) * peak_scale),
            )
            line_fit = fit

            if line.align:
                row_align = line.align
            else:
                row_align = {
                    "LEFT_TITLE": "LEFT",
                    "RIGHT_TITLE": "RIGHT",
                    "CLEAN_CENTER": "CENTER",
                    "DIAGONAL": "CENTER",
                    "WIDE_SPACING": "CENTER",
                }.get(style, props.layout_alignment)

            placed_glyphs = []
            glyph_order = 0
            if is_vertical:
                num_items = max(1, len(flat_glyphs))
                for pos_idx, (ob, _cursor_x, ci, width, _source_char_index, c_in, c_out) in enumerate(flat_glyphs):
                    bx = -width * fit * 0.5
                    by = ((num_items - 1) * 0.5 - pos_idx) * step_y * fit
                    ob.scale = (fit, fit, fit)
                    ob.location = (bx, by, 0.0)
                    ob.rotation_euler.z = 0.0
                    ob["lyric_font_multiplier"] = multiplier
                    ob["lyric_index"] = index
                    ob["lyric_text"] = lyric
                    ob["lyric_character_index"] = glyph_order
                    ob["lyric_character_text"] = display_units[ci].text
                    ob["lyric_character_frame_in"] = c_in
                    ob["lyric_character_frame_out"] = c_out
                    ob["lyric_has_word_timing"] = bool(line.has_word_timing)
                    placed_glyphs.append((ob, bx, by, ci, width))
                    glyph_order += 1
                    created += 1
            else:
                for row_idx, (row_measured, row_width) in enumerate(measured_rows):
                    if row_align == "LEFT":
                        row_start_x = -total_width * fit * 0.5
                    elif row_align == "RIGHT":
                        row_start_x = total_width * fit * 0.5 - row_width * fit
                    else:
                        row_start_x = -row_width * fit * 0.5
                    row_y = ((num_rows - 1) * 0.5 - row_idx) * line_height * fit
                    for ob, cursor_x, ci, width, _source_char_index, c_in, c_out in row_measured:
                        bx = row_start_x + cursor_x * fit
                        scale_factor = 1.35 if style == "EMPHASIS" and not has_explicit_placement and ci == first_glyph_ci else 1.0
                        ob.scale = (fit * scale_factor, fit * scale_factor, fit * scale_factor)
                        ob.location = (bx, row_y, 0.0)
                        ob.rotation_euler.z = 0.0
                        ob["lyric_font_multiplier"] = multiplier
                        ob["lyric_index"] = index
                        ob["lyric_text"] = lyric
                        ob["lyric_character_index"] = glyph_order
                        ob["lyric_character_text"] = display_units[ci].text
                        ob["lyric_character_frame_in"] = c_in
                        ob["lyric_character_frame_out"] = c_out
                        ob["lyric_has_word_timing"] = bool(line.has_word_timing)
                        if kinetic_per_char:
                            stagger_frame = int(frame_in + (glyph_order * props.character_stagger if reveal_enabled else 0))
                            reveal_frame = min(int(c_in), stagger_frame)
                            key_glyph_reveal(
                                ob,
                                reveal_frame,
                                pop_y=-base_size * 0.22 if pop_motion else 0.0,
                                pop_z=props.spatial_depth if pop_motion else 0.0,
                                pop_frames=max(2, fade),
                            )
                            apply_text_animation(
                                ob,
                                record,
                                reveal_frame,
                                frame_out,
                                props,
                                random.Random(int(props.random_seed) + index * 997 + ci),
                            )
                        placed_glyphs.append((ob, bx, row_y, ci, width))
                        glyph_order += 1
                        created += 1

            group_center_x = float(record["x"])
            max_center_x = max(0.0, frame_width * 0.5 - total_width * fit * 0.5 - frame_width * 0.06)
            group_center_x = max(-max_center_x, min(max_center_x, group_center_x))
            y_limit = frame_height * (0.34 if has_explicit_placement else 0.18)
            group_y = max(-y_limit, min(y_limit, float(record["y"]) + extra_y))
            group_center_x, group_y = nudge_lyric_away_from_character(
                scene, camera, props,
                min_x + frame_width * 0.5 + group_center_x,
                min_y + frame_height * 0.5 + group_y,
                total_width * fit, total_height * fit, distance,
                (min_x, max_x, min_y, max_y),
            )
            group_center_x -= min_x + frame_width * 0.5
            group_y -= min_y + frame_height * 0.5
            sentence_group.location = (group_center_x, group_y, 0.0)
            bound_w = total_width * fit
            if style == "EMPHASIS" and not has_explicit_placement and source_format == "YRC" and placed_glyphs:
                first_glyph_width = next((item[4] for item in placed_glyphs if item[3] == first_glyph_ci), 0.0)
                bound_w += first_glyph_width * fit * 0.35
            bound_h = total_height * fit * (1.4 if style == "EMPHASIS" and not has_explicit_placement else 1.25)
            angle = math.radians(float(record["rotation"]))
            rotated_w = abs(bound_w * math.cos(angle)) + abs(bound_h * math.sin(angle))
            rotated_h = abs(bound_w * math.sin(angle)) + abs(bound_h * math.cos(angle))
            sentence_group["lyric_local_bounds"] = [
                -rotated_w * 0.5, rotated_w * 0.5,
                -rotated_h * 0.5, rotated_h * 0.5,
            ]
            sentence_group["lyric_layout_x"] = float(group_center_x)
            sentence_group["lyric_layout_y"] = float(group_y)
            sentence_group["lyric_base_x"] = float(group_center_x)
            sentence_group["lyric_base_y"] = float(group_y)
            sentence_group["lyric_base_z"] = 0.0
            sentence_group["lyric_entrance_enabled"] = True
            sentence_group["lyric_entrance_direction"] = direction
            sentence_group["lyric_frame_in"] = int(frame_in)
            sentence_group["lyric_frame_out"] = int(frame_out)
            sentence_group["lyric_fade_frames"] = int(fade)
            if kinetic_per_char:
                sentence_group["lyric_pop_enabled"] = False
            else:
                sentence_group["lyric_pop_enabled"] = reveal_enabled
                sentence_group["lyric_pop_frames"] = max(2, fade)
                sentence_group["lyric_pop_y"] = -base_size * 0.22 if pop_motion else 0.0
                sentence_group["lyric_pop_z"] = props.spatial_depth if pop_motion else 0.0
                apply_text_animation(
                    sentence_group,
                    record,
                    frame_in,
                    frame_out,
                    props,
                    random.Random(int(props.random_seed) + index * 997),
                )
            key_object_scale(sentence_group, frame_in, frame_out, fade, reveal_enabled)
            for ob, bx, row_y, _ci, _width in placed_glyphs:
                ob.location.x = bx
                ob.location.y = row_y
            if props.glitch_enabled:
                for suffix, color, sign in (("C", (0.1, 0.85, 1.0, 1.0), -1.0), ("M", (1.0, 0.12, 0.48, 1.0), 1.0)):
                    gc = bpy.data.curves.new(f"LPV_Glitch_{index+1:03d}_{suffix}_Curve", type="FONT")
                    gc.body = lyric
                    gc.size = base_size
                    gc.align_x = line.align or "CENTER"
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
        props.generated_count = doc.line_count
        invalidate_entrance_cache()
        update_lyric_positions(props, context)
        update_lyric_entrance_positions(scene)
        scene["lyric_pv_layouts"] = json.dumps(layouts, ensure_ascii=False, sort_keys=True)
        self.report({"INFO"}, f"已生成 {doc.line_count} 句歌词（{created} 个文字对象），集合：{PV_ROOT_NAME}。")
        return {"FINISHED"}


class LYRICPV_OT_reroll_all(Operator):
    bl_idname = "lyric_pv.reroll_all"
    bl_label = "重抽未锁定歌词排版"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        props = scene.lyric_pv_props
        if get_lyric_document(scene) is None:
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


class LYRICPV_OT_reset_materials(Operator):
    bl_idname = "lyric_pv.reset_materials"
    bl_label = "初始化 / 重置默认三态材质"
    bl_description = "创建或恢复唱前、唱中、唱后三个默认着色器节点组以及主材质与描边材质"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.lyric_pv_props
        _mat, (g_before, g_singing, g_after) = make_three_state_text_material(
            after_color=props.text_color,
            after_glow=props.glow_strength,
            reset=True,
        )
        make_outline_material(reset=True)
        props.shader_group_before = g_before
        props.shader_group_singing = g_singing
        props.shader_group_after = g_after
        self.report({"INFO"}, "已初始化/重置唱前、唱中、唱后默认三态着色器节点组。")
        return {"FINISHED"}


class LYRICPV_OT_clear(Operator):
    bl_idname = "lyric_pv.clear"
    bl_label = "清除已生成内容"
    bl_description = "仅删除 LYRIC PV STUDIO 创建的对象和数据"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        props = scene.lyric_pv_props

        # Release shader group pointers first so orphan tagged node groups can be purged cleanly.
        props.shader_group_before = None
        props.shader_group_singing = None
        props.shader_group_after = None

        # Remove generated scene objects and legacy generated background.
        removed = remove_generated_collection(purge_resources=True)
        legacy_background_removed = remove_legacy_generated_background()

        # Clear imported lyric payload, in-memory cache, and layout metadata.
        cleared = clear_lyric_document(scene)
        for key in ("lyric_pv_layouts", "lyric_pv_reroll"):
            if key in scene:
                del scene[key]
                cleared += 1

        # Reset file selector and visible counters as well.
        props.lyric_path = ""
        props.generated_count = 0

        # Drop cached object references so a later generation cannot reuse stale data.
        invalidate_entrance_cache()
        if removed or legacy_background_removed or cleared:
            self.report({"INFO"}, "已彻底清理：生成内容、LRC/YRC/SRT 数据、逐字时间、排版记录和导入路径。")
        else:
            self.report({"INFO"}, "歌词项目已经是空的，无需清理。")
        return {"FINISHED"}
