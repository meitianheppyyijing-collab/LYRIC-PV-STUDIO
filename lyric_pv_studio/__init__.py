# SPDX-License-Identifier: GPL-3.0
#
# LYRIC PV STUDIO - Blender add-on for animated lyric typography and PV production.
# Copyright (C) 2026 静意, SOR2171
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""LYRIC PV STUDIO: Blender add-on for animated lyric typography and PV production.

LYRIC PV STUDIO 插件根入口模块：
- 定义 Blender 插件元数据（bl_info）；
- 提供插件生命周期的注册 (register) 与注销 (unregister) 逻辑；
- 挂载场景属性 lyric_pv_props 及逐帧实时缓动更新处理器 (frame_change_post)。
"""

bl_info = {
    "name": "LYRIC PV STUDIO",
    "author": "OpenAI",
    "version": (0, 5, 15),
    "blender": (5, 2, 0),
    "location": "View3D > Sidebar > Lyric PV",
    "description": "Create animated lyric typography, per-character motion and text effects from LRC files",
    "category": "Animation",
}

try:
    import bpy
    from bpy.props import PointerProperty
    from .animation.runtime import lyric_pv_frame_change_handler
    from .ui import CLASSES, LYRICPV_Properties

    _HAS_BPY = True
except ImportError:
    _HAS_BPY = False
    CLASSES = ()


def register():
    """Register the add-on safely, including repeated enable/reload attempts."""
    if not _HAS_BPY:
        return
    if hasattr(bpy.types.Scene, "lyric_pv_props"):
        del bpy.types.Scene.lyric_pv_props

    for cls in CLASSES:
        if getattr(cls, "is_registered", False):
            try:
                bpy.utils.unregister_class(cls)
            except (RuntimeError, ValueError):
                pass
        bpy.utils.register_class(cls)

    bpy.types.Scene.lyric_pv_props = PointerProperty(type=LYRICPV_Properties)

    handlers = bpy.app.handlers.frame_change_post
    for i in reversed(range(len(handlers))):
        h = handlers[i]
        if (
            getattr(h, "__name__", "") == "lyric_pv_frame_change_handler"
            and h is not lyric_pv_frame_change_handler
        ):
            del handlers[i]
    if lyric_pv_frame_change_handler not in handlers:
        handlers.append(lyric_pv_frame_change_handler)


def unregister():
    """Unregister in reverse dependency order; tolerate partial registration."""
    if not _HAS_BPY:
        return
    handlers = bpy.app.handlers.frame_change_post
    for i in reversed(range(len(handlers))):
        if getattr(handlers[i], "__name__", "") == "lyric_pv_frame_change_handler":
            del handlers[i]

    if hasattr(bpy.types.Scene, "lyric_pv_props"):
        del bpy.types.Scene.lyric_pv_props

    for cls in reversed(CLASSES):
        if getattr(cls, "is_registered", False):
            try:
                bpy.utils.unregister_class(cls)
            except (RuntimeError, ValueError):
                pass


if __name__ == "__main__":
    register()
