"""Material creation and shader node setup for lyric text."""

import bpy

from ..constants import PV_TAG


def make_text_material(name, color, glow_strength=0.35):
    """Create or reuse a Principled BSDF emission material for text."""
    mat = next(
        (item for item in bpy.data.materials if item.get(PV_TAG, False) and item.name.startswith(name)),
        None,
    )
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color[:3], color[3])
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    principled = nodes.get("Principled BSDF")
    if principled:
        base_color_socket = principled.inputs.get("Base Color")
        roughness_socket = principled.inputs.get("Roughness")
        emission_color_socket = principled.inputs.get("Emission Color")
        if emission_color_socket is None:
            emission_color_socket = principled.inputs.get("Emission")
        emission_strength_socket = principled.inputs.get("Emission Strength")
        if base_color_socket is not None:
            base_color_socket.default_value = (*color[:3], color[3])
        if roughness_socket is not None:
            roughness_socket.default_value = 0.65
        if emission_color_socket is not None:
            emission_color_socket.default_value = (*color[:3], 1.0)
        if emission_strength_socket is not None:
            emission_strength_socket.default_value = max(0.0, float(glow_strength))
    mat[PV_TAG] = True
    return mat
