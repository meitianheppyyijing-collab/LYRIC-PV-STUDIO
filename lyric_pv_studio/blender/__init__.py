"""Blender scene interactions: collections, object cleanup, and materials.

Blender 场景数据与资源管理模块：
- 集合管理：安全创建与维护专属根集合，避免污染用户自有场景内容；
- 数据清理：安全递归清理生成的文字对象、曲线与无引用的孤立数据块；
- 材质构建：自动创建并复用基于 Principled BSDF 的自发光与故障错位材质。
"""

from .collections import (
    get_or_create_collection,
    remove_generated_collection,
    remove_legacy_generated_background,
)
from .materials import make_text_material

__all__ = [
    "get_or_create_collection",
    "remove_generated_collection",
    "remove_legacy_generated_background",
    "make_text_material",
]
