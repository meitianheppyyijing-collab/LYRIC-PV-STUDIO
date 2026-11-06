"""Blender scene collection management, tagging, and safe cleanup."""

import bpy

from ..animation.runtime import invalidate_entrance_cache
from ..constants import PV_ROOT_NAME, PV_TAG, PV_VERSION


def get_or_create_collection(scene):
    """Retrieve or safely initialize the dedicated add-on collection."""
    collection = bpy.data.collections.get(PV_ROOT_NAME)
    if collection is not None and not collection.get(PV_TAG, False):
        raise RuntimeError(f"集合名称 {PV_ROOT_NAME} 已被用户内容占用；为保护原场景，插件不会接管它。")
    if collection is None:
        collection = bpy.data.collections.new(PV_ROOT_NAME)
        scene.collection.children.link(collection)
    elif collection.name not in {child.name for child in scene.collection.children}:
        scene.collection.children.link(collection)
    collection[PV_TAG] = True
    collection["pv_version"] = PV_VERSION
    return collection


def _remove_tagged_object(obj):
    """Safely delete a tagged object and unlinked orphan data blocks."""
    if not obj.get(PV_TAG, False):
        return False
    data = getattr(obj, "data", None)
    bpy.data.objects.remove(obj, do_unlink=True)
    if data is not None and data.users == 0:
        if isinstance(data, bpy.types.Curve):
            bpy.data.curves.remove(data)
        elif isinstance(data, bpy.types.Mesh):
            bpy.data.meshes.remove(data)
        elif isinstance(data, bpy.types.Armature):
            bpy.data.armatures.remove(data)
        elif isinstance(data, bpy.types.Camera):
            bpy.data.cameras.remove(data)
        elif isinstance(data, bpy.types.Light):
            bpy.data.lights.remove(data)
    return True


def _clean_tagged_collection_tree(collection):
    """Recursively clean tagged objects and empty child collections."""
    for obj in list(collection.objects):
        _remove_tagged_object(obj)
    for child in list(collection.children):
        if child.get(PV_TAG, False):
            _clean_tagged_collection_tree(child)
            if not child.objects and not child.children:
                bpy.data.collections.remove(child)
    return not collection.objects and not collection.children


def remove_generated_collection():
    """Remove all generated text objects, collections, and orphan materials."""
    collection = bpy.data.collections.get(PV_ROOT_NAME)
    if collection is None or not collection.get(PV_TAG, False):
        return False
    _clean_tagged_collection_tree(collection)
    for mat in list(bpy.data.materials):
        if mat.get(PV_TAG, False) and mat.users == 0:
            bpy.data.materials.remove(mat)
    if not collection.objects and not collection.children:
        bpy.data.collections.remove(collection)
    invalidate_entrance_cache()
    return True


def remove_legacy_generated_background():
    """Clean up legacy LYRIC_PV_STUDIO_BACKGROUND collection from earlier versions."""
    collection = bpy.data.collections.get("LYRIC_PV_STUDIO_BACKGROUND")
    if collection is None or not collection.get("lyric_pv_studio_background", False):
        return False
    for obj in list(collection.all_objects):
        if obj.get("lyric_pv_studio_background", False):
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if data and data.users == 0:
                if isinstance(data, bpy.types.Mesh):
                    bpy.data.meshes.remove(data)
                elif isinstance(data, bpy.types.Curve):
                    bpy.data.curves.remove(data)
    for mat in list(bpy.data.materials):
        if mat.get("lyric_pv_studio_background", False) and mat.users == 0:
            bpy.data.materials.remove(mat)
    if not collection.objects and not collection.children:
        bpy.data.collections.remove(collection)
    return True
