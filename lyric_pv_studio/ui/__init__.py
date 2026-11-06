"""UI components: properties, operators, callbacks, and panels."""

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
