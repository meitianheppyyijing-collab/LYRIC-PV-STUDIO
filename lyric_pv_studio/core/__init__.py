"""Core algorithms for parsing, layout planning, and spatial calculations."""

from .parser import (
    estimate_lyric_unit_advance,
    lyric_display_units,
    parse_lrc_text,
    parse_yrc_text,
    read_lyric_file,
    yrc_character_frame_map,
)
from .layout import (
    load_layout_records,
    reroll_layout_records,
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
    "load_layout_records",
    "reroll_layout_records",
    "camera_frame_bounds",
    "fit_lyric_object_to_camera",
    "get_character_screen_bounds",
    "get_occlusion_safe_distance",
    "nudge_lyric_away_from_character",
]
