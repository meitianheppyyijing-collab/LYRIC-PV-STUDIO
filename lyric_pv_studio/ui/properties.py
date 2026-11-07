"""Blender PropertyGroup definition for LYRIC PV STUDIO."""

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import PropertyGroup

from .callbacks import (
    update_lyric_entrance_settings,
    update_lyric_font_size,
    update_lyric_positions,
    update_lyric_viewport_visibility,
)


class LYRICPV_Properties(PropertyGroup):
    lrc_path: StringProperty(
        name="LRC 文件",
        description="选择要导入的 .lrc 歌词文件",
        subtype="FILE_PATH",
        default="",
    )
    yrc_path: StringProperty(
        name="YRC 文件",
        description="选择要导入的 .yrc 逐字时间歌词文件",
        subtype="FILE_PATH",
        default="",
    )
    target_camera: PointerProperty(
        name="摄像机",
        description="用于定位歌词的摄像机",
        type=bpy.types.Object,
        poll=lambda self, obj: obj is not None and obj.type == "CAMERA",
    )
    occlusion_target: PointerProperty(
        name="人物遮挡目标",
        description="吸管选择人物网格，或选择人物骨架以查找其关联网格",
        type=bpy.types.Object,
        poll=lambda self, obj: obj is not None and obj.type in {"MESH", "ARMATURE"},
        update=update_lyric_positions,
    )
    keep_behind_target: BoolProperty(
        name="字幕避开人物",
        description="启用后将字幕平面放到所选人物网格后方；关闭时使用原摄像机距离",
        default=False,
        update=update_lyric_positions,
    )
    occlusion_margin: FloatProperty(
        name="人物后方间距",
        description="字幕与人物最远表面之间的额外距离",
        default=0.08,
        min=0.0,
        max=10.0,
        precision=3,
        update=update_lyric_positions,
    )
    font_size: FloatProperty(
        name="字体大小",
        description="歌词文字的大小",
        default=0.22,
        min=0.01,
        max=10.0,
        precision=3,
        update=update_lyric_font_size,
    )
    font_path: StringProperty(
        name="字体文件",
        description="可选：选择 .ttf/.otf 字体；留空使用 Blender 默认字体",
        subtype="FILE_PATH",
    )
    character_stagger: IntProperty(
        name="逐字间隔（帧）",
        description="每个字符依次出现的帧间隔；0 表示整句同时出现",
        default=2,
        min=0,
        max=24,
    )
    character_pop: BoolProperty(
        name="逐字弹入",
        description="字符依次从轻微下沉与缩小状态弹入",
        default=True,
    )
    spatial_depth: FloatProperty(
        name="空间入场深度",
        description="逐字入场时沿镜头深度方向的偏移量",
        default=0.08,
        min=0.0,
        max=2.0,
        precision=3,
    )
    glitch_enabled: BoolProperty(
        name="故障闪切",
        description="在每句歌词入场瞬间叠加短暂的彩色错位闪切",
        default=False,
    )
    glitch_strength: FloatProperty(
        name="故障错位幅度",
        description="控制彩色错位文字的偏移距离",
        default=0.012,
        min=0.001,
        max=0.08,
        precision=3,
    )
    glow_strength: FloatProperty(
        name="文字柔光强度",
        description="仅控制插件生成的歌词材质发光，不修改场景合成器",
        default=0.35,
        min=0.0,
        max=8.0,
        precision=2,
    )
    text_extrude: FloatProperty(
        name="文字立体厚度",
        description="给文字增加轻微的 3D 厚度",
        default=0.0,
        min=0.0,
        max=0.15,
        precision=3,
    )
    text_bevel: FloatProperty(
        name="文字边缘柔化",
        description="文字轮廓边缘的轻微倒角",
        default=0.0,
        min=0.0,
        max=0.05,
        precision=3,
    )
    layout_alignment: EnumProperty(
        name="排版对齐",
        items=[
            ("CENTER", "居中", "整句居中"),
            ("LEFT", "左对齐", "从左侧开始排版"),
            ("RIGHT", "右对齐", "从右侧开始排版"),
        ],
        default="CENTER",
    )
    display_x: FloatProperty(
        name="左右位置",
        description="歌词在画面中的水平位置；0 为居中，负数向左，正数向右",
        default=0.0,
        min=-0.9,
        max=0.9,
        precision=3,
        update=update_lyric_positions,
    )
    display_y: FloatProperty(
        name="上下位置",
        description="歌词在画面中的垂直位置；0 为居中，负数向下，正数向上",
        default=-0.48,
        min=-0.9,
        max=0.9,
        precision=3,
        update=update_lyric_positions,
    )
    camera_distance: FloatProperty(
        name="与摄像机距离",
        description="歌词平面与摄像机之间的距离",
        default=2.0,
        min=0.1,
        max=100.0,
        precision=2,
        update=update_lyric_positions,
    )
    slide_frames: IntProperty(
        name="入场移动帧数",
        description="实时控制歌词从镜头外进入画面的速度；数值越小越快",
        default=14,
        min=1,
        max=240,
        update=update_lyric_entrance_settings,
    )
    entrance_distance: FloatProperty(
        name="镜头外起点距离",
        description="控制歌词从画面外多远的位置开始进入；可实时调整",
        default=1.15,
        min=1.0,
        max=3.0,
        precision=2,
        update=update_lyric_entrance_settings,
    )
    fade_frames: IntProperty(
        name="淡入淡出帧数",
        description="每句歌词淡入和淡出的动画帧数",
        default=8,
        min=0,
        max=120,
    )
    hold_gap: FloatProperty(
        name="最后一句持续时间",
        description="最后一句歌词没有下一条时间戳时的显示时长",
        default=3.0,
        min=0.1,
        max=30.0,
    )
    time_offset: FloatProperty(
        name="手动时间偏移",
        description="整体调整歌词时间，单位为秒",
        default=0.0,
        min=-3600.0,
        max=3600.0,
        precision=3,
    )
    text_color: FloatVectorProperty(
        name="字幕颜色",
        subtype="COLOR",
        size=4,
        min=0.0,
        max=1.0,
        default=(1.0, 1.0, 1.0, 1.0),
    )
    random_seed: IntProperty(
        name="随机种子",
        description="相同种子和歌词会生成相同排版",
        default=20261103,
        min=0,
        max=2147483647,
    )
    random_amount: IntProperty(
        name="随机幅度",
        default=60,
        min=0,
        max=100,
        description="0 为完全稳定可复现，100 为最大随机偏移",
    )
    random_layout_enabled: BoolProperty(name="启用随机排版", default=True)
    layout_mode: EnumProperty(
        name="排版模式",
        items=[
            ("RANDOM", "逐句随机", "每句独立随机"),
            ("PER_SECTION", "按段落", "按时间间隔分段，段内统一"),
            ("FIXED", "固定", "全部使用指定对齐"),
        ],
        default="RANDOM",
    )
    chorus_y_offset: FloatProperty(name="副歌上移量", default=0.0, min=-0.5, max=0.5, precision=3)
    position_cycle: IntProperty(
        name="每 N 句换位",
        default=0,
        min=0,
        max=64,
        description="0 为不换位；大于 0 时每 N 句在上下位置间交替",
    )
    layout_line_index: IntProperty(
        name="目标歌词序号",
        description="从 1 开始；用于单句重抽和锁定",
        default=1,
        min=1,
    )
    layout_pool: EnumProperty(
        name="随机样式范围",
        items=[
            ("ALL", "全部 8 种", "从全部排版样式中随机"),
            ("SIMPLE", "基础 4 种", "从居中、左右、竖排中随机"),
        ],
        default="ALL",
    )
    animation_random_mode: EnumProperty(
        name="动画组合",
        description="控制自动随机动画的整体风格",
        items=[
            ("MIXED", "混合随机", "从全部动画方案中随机组合"),
            ("GENTLE", "柔和随机", "偏向渐隐、漂浮和缓慢入场"),
            ("IMPACT", "强烈随机", "偏向弹跳、故障效果"),
            ("TEXT_FX", "文字特效优先", "偏向故障文字效果"),
        ],
        default="MIXED",
    )
    animation_intensity: IntProperty(
        name="动画强度",
        default=60,
        min=0,
        max=100,
        description="控制动画位移、旋转和弹性幅度",
    )
    animation_random_enabled: BoolProperty(
        name="自动随机动画",
        default=True,
        description="每句歌词按随机种子选择入场与退场表现",
    )
    generated_count: IntProperty(name="已生成歌词数", default=0)
    hide_lyrics_in_viewport: BoolProperty(
        name="在视口中隐藏字幕",
        description="仅在 3D 视口中隐藏生成的字幕，不影响最终渲染",
        default=False,
        update=update_lyric_viewport_visibility,
    )
