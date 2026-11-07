"""Sidebar Panel in 3D Viewport for LYRIC PV STUDIO."""

import json

from bpy.types import Panel


class LYRICPV_PT_main(Panel):
    bl_label = "LYRIC PV STUDIO"
    bl_idname = "LYRICPV_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "歌词PV"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = scene.lyric_pv_props

        layout.label(text="歌词项目")
        lrc_box = layout.box()
        lrc_box.label(text="普通歌词（整句时间）")
        lrc_box.prop(props, "lrc_path", text="LRC 文件")
        lrc_box.operator("lyric_pv.import_lrc", text="导入 LRC", icon="FILE_TEXT")

        yrc_box = layout.box()
        yrc_box.label(text="逐字歌词（保留字级时间）")
        yrc_box.prop(props, "yrc_path", text="YRC 文件")
        yrc_box.operator("lyric_pv.import_yrc", text="导入 YRC", icon="FILE_TEXT")

        stored_entries = scene.get("lyric_pv_entries", "")
        try:
            loaded_count = len(json.loads(stored_entries)) if stored_entries else 0
        except (TypeError, ValueError, json.JSONDecodeError):
            loaded_count = 0

        if loaded_count:
            layout.label(text=f"已导入歌词：{loaded_count} 句")
        else:
            layout.label(text="尚未导入歌词")

        layout.separator()
        layout.label(text="场景识别")
        layout.prop(props, "target_camera")
        if props.target_camera is None and scene.camera:
            layout.label(text=f"当前使用场景摄像机：{scene.camera.name}")
        layout.prop(props, "occlusion_target")
        layout.prop(props, "keep_behind_target", toggle=True)
        if props.keep_behind_target and props.occlusion_target:
            layout.prop(props, "occlusion_margin")

        layout.separator()
        layout.label(text="字幕外观与位置")
        layout.prop(props, "font_path")
        layout.prop(props, "font_size")
        layout.separator()
        layout.label(text="随机歌词排版")
        layout.prop(props, "random_layout_enabled")
        if props.random_layout_enabled:
            layout.prop(props, "random_seed")
            layout.prop(props, "random_amount", slider=True)
            layout.prop(props, "layout_mode")
            layout.prop(props, "layout_pool")
            layout.prop(props, "layout_line_index")
            layout.prop(props, "animation_random_enabled")
            layout.prop(props, "animation_random_mode")
            layout.prop(props, "animation_intensity")
            row = layout.row(align=True)
            row.operator("lyric_pv.reroll_all", text="重抽未锁定")
            row.operator("lyric_pv.reroll_one", text="只重抽此句")
            layout.operator("lyric_pv.toggle_lock", text="锁定/解锁此句")
        layout.prop(props, "layout_alignment", expand=True)
        layout.prop(props, "text_extrude")
        layout.prop(props, "text_bevel")
        layout.prop(props, "glow_strength")
        layout.prop(props, "display_x", slider=True)
        layout.prop(props, "display_y", slider=True)
        layout.prop(props, "position_cycle")
        if props.position_cycle > 0:
            layout.prop(props, "chorus_y_offset")
        layout.prop(props, "text_color")

        layout.separator()
        layout.label(text="时间与动画")
        layout.prop(props, "camera_distance")
        layout.label(text="自动随机镜头外入场")
        layout.prop(props, "slide_frames", slider=True)
        layout.prop(props, "entrance_distance", slider=True)
        layout.prop(props, "fade_frames")
        layout.prop(props, "character_pop")
        if props.character_pop:
            layout.prop(props, "character_stagger")
            layout.prop(props, "spatial_depth")
        layout.prop(props, "glitch_enabled")
        if props.glitch_enabled:
            layout.prop(props, "glitch_strength")
        layout.prop(props, "hold_gap")
        layout.prop(props, "time_offset")

        layout.separator()
        layout.label(text="视口显示")
        layout.prop(props, "hide_lyrics_in_viewport", toggle=True)
        layout.separator()
        layout.operator("lyric_pv.generate", text="生成歌词排版与动画", icon="FONT_DATA")
        layout.operator("lyric_pv.clear", text="彻底清理歌词项目", icon="TRASH")
        layout.label(text=f"已生成字幕：{props.generated_count} 条")
