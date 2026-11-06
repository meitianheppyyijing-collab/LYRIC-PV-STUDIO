"""Core algorithms for parsing, layout planning, and spatial calculations.

核心计算与算法库模块（与 Blender UI 解耦，可独立测试）：
- parser: 解析 LRC 标准歌词与 YRC 逐字歌词，智能断词及字距排版步进估算；
- layout: 随机排版策略调度、歌曲段落切分、单句布局参数构建与重抽；
- spatial: 摄像机视锥投影边界计算、文字安全框自适应、人物三维遮挡投影与二维智能避让。
"""

from .layout import (
    get_random_amount,
    load_layout_records,
    reroll_layout_records,
)
from .parser import (
    estimate_lyric_unit_advance,
    lyric_display_units,
    parse_lrc_text,
    parse_yrc_text,
    read_lyric_file,
    yrc_character_frame_map,
)

try:
    from .spatial import (
        camera_frame_bounds,
        fit_lyric_object_to_camera,
        get_character_screen_bounds,
        get_occlusion_safe_distance,
        nudge_lyric_away_from_character,
    )
except ImportError:
    pass

__all__ = [
    "estimate_lyric_unit_advance",
    "lyric_display_units",
    "parse_lrc_text",
    "parse_yrc_text",
    "read_lyric_file",
    "yrc_character_frame_map",
    "get_random_amount",
    "load_layout_records",
    "reroll_layout_records",
    "camera_frame_bounds",
    "fit_lyric_object_to_camera",
    "get_character_screen_bounds",
    "get_occlusion_safe_distance",
    "nudge_lyric_away_from_character",
]
