"""Material creation and 3-state (before/singing/after) shader node setup."""

import bpy

from ..constants import PV_TAG

DEFAULT_BEFORE_COLOR = (0.55, 0.55, 0.58, 1.0)
DEFAULT_BEFORE_GLOW = 0.05
DEFAULT_SINGING_COLOR = (1.0, 0.88, 0.72, 1.0)
DEFAULT_SINGING_GLOW = 0.25
DEFAULT_TEXT_COLOR = (1.0, 0.503542, 0.162092, 1.0)
DEFAULT_AFTER_COLOR = DEFAULT_TEXT_COLOR
DEFAULT_AFTER_GLOW = 0.35
DEFAULT_OUTLINE_COLOR = (0.03, 0.02, 0.02, 1.0)

TEXT_MATERIAL_NAME = "LPV_Text_Material"
OUTLINE_MATERIAL_NAME = "LPV_Text_Outline"
SHADER_GROUP_BEFORE = "LPV_Shader_Before"
SHADER_GROUP_SINGING = "LPV_Shader_Singing"
SHADER_GROUP_AFTER = "LPV_Shader_After"

ATTR_ENTERED = "lpv_entered"
ATTR_FINISHED = "lpv_finished"


def _to_rgba(color):
    return (
        float(color[0]),
        float(color[1]),
        float(color[2]),
        float(color[3]) if len(color) > 3 else 1.0,
    )


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


def _build_basic_shader_tree(nodes, links, output_socket, color, glow_strength):
    """Build RGB -> Reroute -> Principled BSDF connected into output_socket."""
    rgba = _to_rgba(color)

    rgb_node = nodes.new("ShaderNodeRGB")
    rgb_node.location = (-660.0, -30.0)
    rgb_node.outputs[0].default_value = (*rgba[:3], 1.0)

    reroute = nodes.new("NodeReroute")
    reroute.location = (-400.0, -60.0)

    principled = nodes.new("ShaderNodeBsdfPrincipled")
    principled.location = (-200.0, 100.0)

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
    links.new(principled.outputs[0], output_socket)


def get_or_create_stage_shader_group(name, default_color, default_glow, reset=False):
    """Create or safely reuse a user-editable ShaderNodeTree for a lyric stage.

    Existing groups are never cleared unless reset=True, so user edits in the
    Shader Editor survive regenerations and layout rerolls.
    """
    group = bpy.data.node_groups.get(name)
    if group is not None and group.type != "SHADER":
        group = None
    if group is None:
        group = next(
            (
                ng
                for ng in bpy.data.node_groups
                if ng.type == "SHADER" and ng.get(PV_TAG, False) and ng.name.startswith(name)
            ),
            None,
        )

    is_new = group is None
    if is_new:
        group = bpy.data.node_groups.new(name, "ShaderNodeTree")

    has_shader_output = any(
        item.item_type == "SOCKET"
        and item.in_out == "OUTPUT"
        and item.socket_type == "NodeSocketShader"
        for item in getattr(getattr(group, "interface", None), "items_tree", ())
    )

    if is_new or reset or not has_shader_output:
        group.nodes.clear()
        if hasattr(group, "interface"):
            group.interface.clear()
            group.interface.new_socket(
                name="Shader", in_out="OUTPUT", socket_type="NodeSocketShader"
            )
        group_out = group.nodes.new("NodeGroupOutput")
        group_out.location = (200.0, 100.0)
        _build_basic_shader_tree(
            group.nodes, group.links, group_out.inputs[0], default_color, default_glow
        )

    group[PV_TAG] = True
    return group


def ensure_stage_shader_groups(
    before_group=None,
    singing_group=None,
    after_group=None,
    after_color=DEFAULT_AFTER_COLOR,
    after_glow=DEFAULT_AFTER_GLOW,
    reset=False,
):
    """Return the (before, singing, after) ShaderNodeTree trio, creating missing ones."""
    if before_group is None or before_group.type != "SHADER" or reset:
        before_group = get_or_create_stage_shader_group(
            SHADER_GROUP_BEFORE, DEFAULT_BEFORE_COLOR, DEFAULT_BEFORE_GLOW, reset=reset
        )
    if singing_group is None or singing_group.type != "SHADER" or reset:
        singing_group = get_or_create_stage_shader_group(
            SHADER_GROUP_SINGING, DEFAULT_SINGING_COLOR, DEFAULT_SINGING_GLOW, reset=reset
        )
    if after_group is None or after_group.type != "SHADER" or reset:
        after_group = get_or_create_stage_shader_group(
            SHADER_GROUP_AFTER, after_color, after_glow, reset=reset
        )
    return before_group, singing_group, after_group


def _shader_group_output_socket(node):
    for sock in node.outputs:
        if sock.type == "SHADER":
            return sock
    return node.outputs[0] if node.outputs else None


def _build_three_state_material_tree(mat, before_group, singing_group, after_group):
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    attr_entered = nodes.new("ShaderNodeAttribute")
    attr_entered.name = "LPV_Attr_Entered"
    attr_entered.label = "唱入权重 (lpv_entered)"
    attr_entered.attribute_type = "GEOMETRY"
    attr_entered.attribute_name = ATTR_ENTERED
    attr_entered.location = (-360.0, 320.0)

    attr_finished = nodes.new("ShaderNodeAttribute")
    attr_finished.name = "LPV_Attr_Finished"
    attr_finished.label = "唱完权重 (lpv_finished)"
    attr_finished.attribute_type = "GEOMETRY"
    attr_finished.attribute_name = ATTR_FINISHED
    attr_finished.location = (-40.0, 320.0)

    n_before = nodes.new("ShaderNodeGroup")
    n_before.name = "LPV_Stage_Before"
    n_before.label = "唱前材质"
    n_before.node_tree = before_group
    n_before.location = (-360.0, 120.0)

    n_singing = nodes.new("ShaderNodeGroup")
    n_singing.name = "LPV_Stage_Singing"
    n_singing.label = "唱中材质"
    n_singing.node_tree = singing_group
    n_singing.location = (-360.0, -40.0)

    n_after = nodes.new("ShaderNodeGroup")
    n_after.name = "LPV_Stage_After"
    n_after.label = "唱后材质"
    n_after.node_tree = after_group
    n_after.location = (-360.0, -200.0)

    mix_enter = nodes.new("ShaderNodeMixShader")
    mix_enter.name = "LPV_Mix_Before_Singing"
    mix_enter.label = "唱前 -> 唱中"
    mix_enter.location = (-40.0, 60.0)

    mix_finish = nodes.new("ShaderNodeMixShader")
    mix_finish.name = "LPV_Mix_Singing_After"
    mix_finish.label = "唱中 -> 唱后"
    mix_finish.location = (200.0, 0.0)

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (440.0, 0.0)

    links.new(attr_entered.outputs["Fac"], mix_enter.inputs[0])
    out_before = _shader_group_output_socket(n_before)
    out_singing = _shader_group_output_socket(n_singing)
    out_after = _shader_group_output_socket(n_after)
    if out_before is not None:
        links.new(out_before, mix_enter.inputs[1])
    if out_singing is not None:
        links.new(out_singing, mix_enter.inputs[2])

    links.new(attr_finished.outputs["Fac"], mix_finish.inputs[0])
    links.new(mix_enter.outputs[0], mix_finish.inputs[1])
    if out_after is not None:
        links.new(out_after, mix_finish.inputs[2])
    links.new(mix_finish.outputs[0], output.inputs["Surface"])


def sync_three_state_material_groups(mat, before_group, singing_group, after_group):
    """Update the 3 stage node-group references on an existing master material."""
    if mat is None or not mat.use_nodes or mat.node_tree is None:
        return False
    nodes = mat.node_tree.nodes
    n_before = nodes.get("LPV_Stage_Before")
    n_singing = nodes.get("LPV_Stage_Singing")
    n_after = nodes.get("LPV_Stage_After")
    if not (n_before and n_singing and n_after):
        return False
    if before_group is not None and before_group.type == "SHADER":
        n_before.node_tree = before_group
    if singing_group is not None and singing_group.type == "SHADER":
        n_singing.node_tree = singing_group
    if after_group is not None and after_group.type == "SHADER":
        n_after.node_tree = after_group
    return True


def make_three_state_text_material(
    name=TEXT_MATERIAL_NAME,
    before_group=None,
    singing_group=None,
    after_group=None,
    after_color=DEFAULT_AFTER_COLOR,
    after_glow=DEFAULT_AFTER_GLOW,
    reset=False,
):
    """Create or reuse the master 3-state lyric material driven by lpv_entered/lpv_finished."""
    before_group, singing_group, after_group = ensure_stage_shader_groups(
        before_group=before_group,
        singing_group=singing_group,
        after_group=after_group,
        after_color=after_color,
        after_glow=after_glow,
        reset=reset,
    )
    mat = _find_or_create_material(name)
    mat.diffuse_color = _to_rgba(after_color)
    mat.use_nodes = True

    if (
        not reset
        and mat.get("lpv_three_state", False)
        and sync_three_state_material_groups(mat, before_group, singing_group, after_group)
    ):
        mat[PV_TAG] = True
        return mat, (before_group, singing_group, after_group)

    _build_three_state_material_tree(mat, before_group, singing_group, after_group)
    mat["lpv_three_state"] = True
    mat[PV_TAG] = True
    return mat, (before_group, singing_group, after_group)


def update_stage_group_basic_params(group, color=None, glow_strength=None):
    """Gently update RGB/Emission Strength on a stage group if those default nodes exist."""
    if group is None or group.type != "SHADER":
        return
    if color is not None:
        rgba = _to_rgba(color)
        for node in group.nodes:
            if node.type == "RGB":
                node.outputs[0].default_value = (*rgba[:3], 1.0)
                break
    if glow_strength is not None:
        for node in group.nodes:
            if node.type == "BSDF_PRINCIPLED":
                sock = node.inputs.get("Emission Strength")
                if sock is not None:
                    sock.default_value = max(0.0, float(glow_strength))
                break


def make_text_material(name, color, glow_strength=0.35):
    """Create or reuse a simple RGB -> Reroute -> Principled BSDF material (glitch/SRT color)."""
    mat = _find_or_create_material(name)
    rgba = _to_rgba(color)
    mat.diffuse_color = rgba
    mat.use_nodes = True

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (200.0, 100.0)
    _build_basic_shader_tree(nodes, links, output.inputs["Surface"], rgba, glow_strength)

    mat[PV_TAG] = True
    return mat


def make_outline_material(name=OUTLINE_MATERIAL_NAME, color=DEFAULT_OUTLINE_COLOR, reset=False):
    """Create or reuse the shadowless emission outline material without clobbering user edits."""
    mat = _find_or_create_material(name)
    already_initialized = bool(mat.get("lpv_outline_initialized", False)) and mat.use_nodes and bool(mat.node_tree.nodes)
    if already_initialized and not reset:
        mat[PV_TAG] = True
        return mat

    rgba = _to_rgba(color)
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

    mat["lpv_outline_initialized"] = True
    mat[PV_TAG] = True
    return mat
