"""Animation keyframing, motion effects, and real-time entrance evaluation."""

from .keyframing import (
    apply_text_animation,
    _key_object_scale,
)
from .runtime import (
    invalidate_entrance_cache,
    lyric_pv_frame_change_handler,
    update_lyric_entrance_positions,
)

__all__ = [
    "apply_text_animation",
    "_key_object_scale",
    "invalidate_entrance_cache",
    "lyric_pv_frame_change_handler",
    "update_lyric_entrance_positions",
]
