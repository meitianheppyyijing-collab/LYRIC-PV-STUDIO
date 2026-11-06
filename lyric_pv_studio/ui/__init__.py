"""UI components: properties, operators, callbacks, and panels.

用户界面与交互控制模块：
- properties: 定义歌词路径、摄像机、字体外观、随机排版与动效参数等属性组；
- operators: 提供 LRC/YRC 文件导入、排版生成、局部/全部重抽、单句锁定与清理等操作符；
- callbacks: 视口可见性、字号、镜头距离等属性发生变动时的实时联动回调；
- panels: 绘制 3D 视图侧边栏（N 面板）的“歌词PV”交互界面。
"""

from .operators import (
    LYRICPV_OT_clear,
    LYRICPV_OT_generate,
    LYRICPV_OT_import_lrc,
    LYRICPV_OT_import_yrc,
    LYRICPV_OT_reroll_all,
    LYRICPV_OT_reroll_one,
    LYRICPV_OT_toggle_lock,
)
from .panels import LYRICPV_PT_main
from .properties import LYRICPV_Properties

CLASSES = (
    LYRICPV_Properties,
    LYRICPV_OT_import_lrc,
    LYRICPV_OT_import_yrc,
    LYRICPV_OT_generate,
    LYRICPV_OT_reroll_all,
    LYRICPV_OT_reroll_one,
    LYRICPV_OT_toggle_lock,
    LYRICPV_OT_clear,
    LYRICPV_PT_main,
)

__all__ = [
    "CLASSES",
    "LYRICPV_Properties",
    "LYRICPV_OT_import_lrc",
    "LYRICPV_OT_import_yrc",
    "LYRICPV_OT_generate",
    "LYRICPV_OT_reroll_all",
    "LYRICPV_OT_reroll_one",
    "LYRICPV_OT_toggle_lock",
    "LYRICPV_OT_clear",
    "LYRICPV_PT_main",
]
