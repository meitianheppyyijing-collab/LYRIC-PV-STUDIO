"""Animation keyframing, motion effects, and real-time entrance evaluation.

动画控制模块：
- 关键帧烘焙：处理文字缩放、旋转、弹跳与微动效果；
- 曲线平滑：统一将关键帧曲线设置为防过冲的贝塞尔插值；
- 实时运行时：在时间轴播放或渲染时根据入场方向与缓动曲线实时计算文字位置。
"""

from .keyframing import (
    apply_text_animation,
    key_object_scale,
    smooth_action_fcurves,
)

try:
    from .runtime import (
        invalidate_entrance_cache,
        lyric_pv_frame_change_handler,
        update_lyric_entrance_positions,
    )
except ImportError:
    pass

__all__ = [
    "apply_text_animation",
    "key_object_scale",
    "smooth_action_fcurves",
    "invalidate_entrance_cache",
    "lyric_pv_frame_change_handler",
    "update_lyric_entrance_positions",
]
