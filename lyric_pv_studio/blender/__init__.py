"""Blender scene interactions: collections, object cleanup, materials, and geometry nodes.

Blender 场景数据与资源管理模块：
- 集合管理：安全创建与维护专属根集合，避免污染用户自有场景内容；
- 数据清理：安全递归清理生成的文字对象、曲线与无引用的孤立数据块（材质与几何节点组）；
- 材质构建：自动创建并复用默认暖橙自发光文字材质、无影描边材质与故障错位材质；
- 几何节点：自动创建并挂载默认 `lyc_solidify` 立体厚度与描边几何节点修改器。
"""

from .collections import (
    get_or_create_collection,
    remove_generated_collection,
    remove_legacy_generated_background,
)
from .geometry_nodes import (
    attach_lyric_solidify_modifier,
    get_or_create_lyric_solidify_node_group,
)
from .materials import (
    DEFAULT_OUTLINE_COLOR,
    DEFAULT_TEXT_COLOR,
    make_outline_material,
    make_text_material,
)

__all__ = [
    "DEFAULT_TEXT_COLOR",
    "DEFAULT_OUTLINE_COLOR",
    "get_or_create_collection",
    "remove_generated_collection",
    "remove_legacy_generated_background",
    "get_or_create_lyric_solidify_node_group",
    "attach_lyric_solidify_modifier",
    "make_text_material",
    "make_outline_material",
]
