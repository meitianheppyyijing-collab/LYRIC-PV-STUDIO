"""Material creation and shader node setup for lyric text and outlines."""

import bpy

from ..constants import PV_TAG

DEFAULT_TEXT_COLOR = (1.0, 0.503542, 0.162092, 1.0)
DEFAULT_OUTLINE_COLOR = (0.03, 0.02, 0.02, 1.0)
OUTLINE_MATERIAL_NAME = "LPV_Text_Outline"


def _find_or_create_material(name):
    mat = next(
        (
            item
            for item in bpy.data.materials
            if item.get(PV_TAG, False) and item.name.startswith(name)
        ),
        None,
    )
    if mat is None:
        mat = bpy.data.materials.new(name)
    return mat


def make_text_material(name, color, glow_strength=0.35):
    """Create or reuse the default RGB -> Reroute -> Principled BSDF lyric material."""
    mat = _find_or_create_material(name)
    rgba = (float(color[0]), float(color[1]), float(color[2]), float(color[3]) if len(color) > 3 else 1.0)
    mat.diffuse_color = rgba
    mat.use_nodes = True

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    rgb_node = nodes.new("ShaderNodeRGB")
    rgb_node.location = (-660.0, -30.0)
    rgb_node.outputs[0].default_value = (*rgba[:3], 1.0)

    reroute = nodes.new("NodeReroute")
    reroute.location = (-400.0, -60.0)

    principled = nodes.new("ShaderNodeBsdfPrincipled")
    principled.location = (-200.0, 100.0)

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (200.0, 100.0)

    roughness_socket = principled.inputs.get("Roughness")
    if roughness_socket is not None:
        roughness_socket.default_value = 0.5
    emission_strength_socket = principled.inputs.get("Emission Strength")
    if emission_strength_socket is not None:
        emission_strength_socket.default_value = max(0.0, float(glow_strength))

    base_color_socket = principled.inputs.get("Base Color")
    emission_color_socket = principled.inputs.get("Emission Color") or principled.inputs.get("Emission")

    links.new(rgb_node.outputs[0], reroute.inputs[0])
    if base_color_socket is not None:
        links.new(reroute.outputs[0], base_color_socket)
    if emission_color_socket is not None:
        links.new(reroute.outputs[0], emission_color_socket)
    links.new(principled.outputs[0], output.inputs["Surface"])

    mat[PV_TAG] = True
    return mat


def make_outline_material(name=OUTLINE_MATERIAL_NAME, color=DEFAULT_OUTLINE_COLOR):
    """Create or reuse the shadowless emission outline material for lyc_solidify."""
    mat = _find_or_create_material(name)
    rgba = (float(color[0]), float(color[1]), float(color[2]), float(color[3]) if len(color) > 3 else 1.0)
    mat.diffuse_color = rgba
    mat.use_nodes = True

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    light_path = nodes.new("ShaderNodeLightPath")
    light_path.location = (-495.0, -45.0)

    rgb_node = nodes.new("ShaderNodeRGB")
    rgb_node.label = "描边颜色"
    rgb_node.location = (-315.0, 15.0)
    rgb_node.outputs[0].default_value = (*rgba[:3], 1.0)

    emission = nodes.new("ShaderNodeEmission")
    emission.location = (-95.0, 15.0)
    emission.inputs["Strength"].default_value = 1.0

    transparent = nodes.new("ShaderNodeBsdfTransparent")
    transparent.location = (-95.0, -165.0)
    transparent.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)

    mix_shader = nodes.new("ShaderNodeMixShader")
    mix_shader.location = (165.0, -35.0)

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (385.0, -85.0)

    links.new(rgb_node.outputs[0], emission.inputs["Color"])
    links.new(light_path.outputs["Is Shadow Ray"], mix_shader.inputs[0])
    links.new(emission.outputs[0], mix_shader.inputs[1])
    links.new(transparent.outputs[0], mix_shader.inputs[2])
    links.new(mix_shader.outputs[0], output.inputs["Surface"])

    mat[PV_TAG] = True
    return mat
