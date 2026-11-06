"""Blender scene interactions: collections, object cleanup, and materials."""

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
