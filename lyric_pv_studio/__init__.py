"""LYRIC PV STUDIO: Blender add-on for animated lyric typography and PV production."""

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
        registered_cls = getattr(bpy.types, cls.__name__, None)
        if registered_cls is cls:
            continue
        if registered_cls is not None:
            try:
                bpy.utils.unregister_class(registered_cls)
            except (RuntimeError, ValueError):
                pass
        bpy.utils.register_class(cls)

    bpy.types.Scene.lyric_pv_props = PointerProperty(type=LYRICPV_Properties)

    handlers = bpy.app.handlers.frame_change_post
    for handler in list(handlers):
        if (
            getattr(handler, "__name__", "") == "lyric_pv_frame_change_handler"
            and handler is not lyric_pv_frame_change_handler
        ):
            handlers.remove(handler)
    if lyric_pv_frame_change_handler not in handlers:
        handlers.append(lyric_pv_frame_change_handler)


def unregister():
    """Unregister in reverse dependency order; tolerate partial registration."""
    if not _HAS_BPY:
        return
    handlers = bpy.app.handlers.frame_change_post
    for handler in list(handlers):
        if getattr(handler, "__name__", "") == "lyric_pv_frame_change_handler":
            handlers.remove(handler)

    if hasattr(bpy.types.Scene, "lyric_pv_props"):
        del bpy.types.Scene.lyric_pv_props

    for cls in reversed(CLASSES):
        registered_cls = getattr(bpy.types, cls.__name__, None)
        if registered_cls is not None:
            try:
                bpy.utils.unregister_class(registered_cls)
            except (RuntimeError, ValueError):
                pass


if __name__ == "__main__":
    register()
