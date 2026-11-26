"""Geometry Nodes setup for lyric text thickness, outline, and per-char material state."""

import bpy

from ..constants import PV_TAG
from .materials import ATTR_ENTERED, ATTR_FINISHED

LYRIC_SOLIDIFY_GROUP_NAME = "lyc_solidify"
DEFAULT_TEXT_DEPTH = 0.02
DEFAULT_OUTLINE_THICKNESS = 0.0055
DEFAULT_OUTLINE_Z_OFFSET = -0.0015
DEFAULT_TRANSITION_FRAMES = 2.0

SOCKET_PER_CHAR_MATERIAL = "Per-Char Material"
SOCKET_CHAR_FRAME_IN = "Char Frame In"
SOCKET_CHAR_FRAME_OUT = "Char Frame Out"
SOCKET_TRANSITION_FRAMES = "Transition Frames"
SOCKET_OUTLINE_MATERIAL = "Outline Material"


def _enabled_input(node, name):
    """Return the first enabled input socket matching name/identifier."""
    for sock in node.inputs:
        if sock.enabled and (sock.identifier == name or sock.name == name):
            return sock
    return node.inputs.get(name)


def _set_input_default(node, name, value):
    sock = _enabled_input(node, name)
    if sock is not None and hasattr(sock, "default_value"):
        try:
            sock.default_value = value
        except (TypeError, ValueError):
            pass


def _interface_socket_by_name(node_group, name, in_out="INPUT"):
    if not hasattr(node_group, "interface"):
        return None
    for item in node_group.interface.items_tree:
        if item.item_type == "SOCKET" and item.in_out == in_out and item.name == name:
            return item
    return None


def _build_lyric_solidify_tree(node_group, outline_material):
    """Populate the lyc_solidify Geometry Node tree with thickness, outline, and 3-state attributes."""
    node_group.nodes.clear()
    if hasattr(node_group, "interface"):
        node_group.interface.clear()
        node_group.interface.new_socket(
            name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry"
        )
        node_group.interface.new_socket(
            name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry"
        )
        depth_sock = node_group.interface.new_socket(
            name="Text Depth", in_out="INPUT", socket_type="NodeSocketFloat"
        )
        depth_sock.subtype = "DISTANCE"
        depth_sock.min_value = 0.0
        depth_sock.default_value = DEFAULT_TEXT_DEPTH

        thick_sock = node_group.interface.new_socket(
            name="Outline Thickness", in_out="INPUT", socket_type="NodeSocketFloat"
        )
        thick_sock.subtype = "DISTANCE"
        thick_sock.min_value = 0.0
        thick_sock.default_value = DEFAULT_OUTLINE_THICKNESS

        z_sock = node_group.interface.new_socket(
            name="Z Offset", in_out="INPUT", socket_type="NodeSocketFloat"
        )
        z_sock.subtype = "DISTANCE"
        z_sock.default_value = DEFAULT_OUTLINE_Z_OFFSET

        mat_sock = node_group.interface.new_socket(
            name=SOCKET_OUTLINE_MATERIAL, in_out="INPUT", socket_type="NodeSocketMaterial"
        )
        if outline_material is not None:
            mat_sock.default_value = outline_material

        per_char_sock = node_group.interface.new_socket(
            name=SOCKET_PER_CHAR_MATERIAL, in_out="INPUT", socket_type="NodeSocketBool"
        )
        per_char_sock.default_value = True

        frame_in_sock = node_group.interface.new_socket(
            name=SOCKET_CHAR_FRAME_IN, in_out="INPUT", socket_type="NodeSocketFloat"
        )
        frame_in_sock.default_value = 1.0

        frame_out_sock = node_group.interface.new_socket(
            name=SOCKET_CHAR_FRAME_OUT, in_out="INPUT", socket_type="NodeSocketFloat"
        )
        frame_out_sock.default_value = 2.0

        trans_sock = node_group.interface.new_socket(
            name=SOCKET_TRANSITION_FRAMES, in_out="INPUT", socket_type="NodeSocketFloat"
        )
        trans_sock.min_value = 0.0
        trans_sock.default_value = DEFAULT_TRANSITION_FRAMES

    nodes = node_group.nodes
    links = node_group.links

    group_in = nodes.new("NodeGroupInput")
    group_in.location = (-1100.0, 0.0)

    group_out = nodes.new("NodeGroupOutput")
    group_out.location = (1460.0, 80.0)

    realize = nodes.new("GeometryNodeRealizeInstances")
    realize.location = (-860.0, 0.0)
    _set_input_default(realize, "Realize All", True)

    # --- Text thickness branch ---
    extrude = nodes.new("GeometryNodeExtrudeMesh")
    extrude.location = (-560.0, 320.0)
    extrude.mode = "FACES"
    _set_input_default(extrude, "Offset", (0.0, 0.0, 1.0))
    _set_input_default(extrude, "Individual", False)

    flip = nodes.new("GeometryNodeFlipFaces")
    flip.location = (-560.0, 100.0)

    join_text = nodes.new("GeometryNodeJoinGeometry")
    join_text.location = (-340.0, 240.0)

    merge = nodes.new("GeometryNodeMergeByDistance")
    merge.location = (-160.0, 240.0)
    _set_input_default(merge, "Distance", 0.0001)

    neg_depth = nodes.new("ShaderNodeMath")
    neg_depth.location = (-340.0, 460.0)
    neg_depth.operation = "MULTIPLY"
    neg_depth.inputs[1].default_value = -1.0

    comb_text_z = nodes.new("ShaderNodeCombineXYZ")
    comb_text_z.location = (-160.0, 460.0)

    xf_text = nodes.new("GeometryNodeTransform")
    xf_text.location = (40.0, 280.0)

    cmp_depth = nodes.new("FunctionNodeCompare")
    cmp_depth.location = (40.0, 480.0)
    cmp_depth.data_type = "FLOAT"
    cmp_depth.operation = "GREATER_THAN"
    _set_input_default(cmp_depth, "B", 1e-5)

    sw_text = nodes.new("GeometryNodeSwitch")
    sw_text.location = (260.0, 320.0)
    sw_text.input_type = "GEOMETRY"

    smooth_text = nodes.new("GeometryNodeSetShadeSmooth")
    smooth_text.location = (460.0, 320.0)
    smooth_text.domain = "FACE"
    _set_input_default(smooth_text, "Shade Smooth", False)

    # --- Per-character 3-state timing weights (Before -> Singing -> After) ---
    scene_time = nodes.new("GeometryNodeInputSceneTime")
    scene_time.location = (40.0, 820.0)

    enter_start = nodes.new("ShaderNodeMath")
    enter_start.location = (40.0, 680.0)
    enter_start.operation = "SUBTRACT"
    enter_start.inputs[1].default_value = 0.001

    enter_end = nodes.new("ShaderNodeMath")
    enter_end.location = (40.0, 560.0)
    enter_end.operation = "ADD"

    map_enter = nodes.new("ShaderNodeMapRange")
    map_enter.location = (260.0, 740.0)
    map_enter.data_type = "FLOAT"
    map_enter.interpolation_type = "SMOOTHSTEP"
    map_enter.clamp = True

    sw_enter = nodes.new("GeometryNodeSwitch")
    sw_enter.location = (480.0, 740.0)
    sw_enter.input_type = "FLOAT"
    _set_input_default(sw_enter, "False", 1.0)

    exit_start = nodes.new("ShaderNodeMath")
    exit_start.location = (40.0, 1080.0)
    exit_start.operation = "SUBTRACT"
    exit_start.inputs[1].default_value = 0.001

    exit_end = nodes.new("ShaderNodeMath")
    exit_end.location = (40.0, 960.0)
    exit_end.operation = "ADD"

    map_exit = nodes.new("ShaderNodeMapRange")
    map_exit.location = (260.0, 1020.0)
    map_exit.data_type = "FLOAT"
    map_exit.interpolation_type = "SMOOTHSTEP"
    map_exit.clamp = True

    sw_exit = nodes.new("GeometryNodeSwitch")
    sw_exit.location = (480.0, 1020.0)
    sw_exit.input_type = "FLOAT"
    _set_input_default(sw_exit, "False", 1.0)

    store_entered = nodes.new("GeometryNodeStoreNamedAttribute")
    store_entered.location = (700.0, 320.0)
    store_entered.data_type = "FLOAT"
    store_entered.domain = "FACE"
    _set_input_default(store_entered, "Name", ATTR_ENTERED)

    store_finished = nodes.new("GeometryNodeStoreNamedAttribute")
    store_finished.location = (920.0, 320.0)
    store_finished.data_type = "FLOAT"
    store_finished.domain = "FACE"
    _set_input_default(store_finished, "Name", ATTR_FINISHED)

    # --- Outline branch ---
    edge_nbr = nodes.new("GeometryNodeInputMeshEdgeNeighbors")
    edge_nbr.location = (-660.0, -280.0)

    cmp_edge = nodes.new("FunctionNodeCompare")
    cmp_edge.location = (-460.0, -280.0)
    cmp_edge.data_type = "INT"
    cmp_edge.operation = "EQUAL"
    _set_input_default(cmp_edge, "B", 1)

    mesh_to_curve = nodes.new("GeometryNodeMeshToCurve")
    mesh_to_curve.location = (-260.0, -160.0)
    if hasattr(mesh_to_curve, "mode"):
        mesh_to_curve.mode = "EDGES"

    curve_normal = nodes.new("GeometryNodeSetCurveNormal")
    curve_normal.location = (-60.0, -160.0)
    mode_sock = _enabled_input(curve_normal, "Mode")
    if mode_sock is not None and hasattr(mode_sock, "default_value"):
        try:
            mode_sock.default_value = "Z Up"
        except (TypeError, ValueError):
            pass
    elif hasattr(curve_normal, "mode"):
        try:
            curve_normal.mode = "Z_UP"
        except (TypeError, ValueError):
            pass

    mul_thick = nodes.new("ShaderNodeMath")
    mul_thick.location = (-260.0, -380.0)
    mul_thick.operation = "MULTIPLY"
    mul_thick.inputs[1].default_value = 2.0

    max_depth = nodes.new("ShaderNodeMath")
    max_depth.location = (-260.0, -540.0)
    max_depth.operation = "MAXIMUM"
    max_depth.inputs[1].default_value = 0.001

    quad = nodes.new("GeometryNodeCurvePrimitiveQuadrilateral")
    quad.location = (-60.0, -400.0)
    quad.mode = "RECTANGLE"

    curve_to_mesh = nodes.new("GeometryNodeCurveToMesh")
    curve_to_mesh.location = (160.0, -220.0)
    _set_input_default(curve_to_mesh, "Scale", 1.0)
    _set_input_default(curve_to_mesh, "Fill Caps", False)

    half_neg_depth = nodes.new("ShaderNodeMath")
    half_neg_depth.location = (-60.0, -600.0)
    half_neg_depth.operation = "MULTIPLY"
    half_neg_depth.inputs[1].default_value = -0.5

    add_z = nodes.new("ShaderNodeMath")
    add_z.location = (120.0, -520.0)
    add_z.operation = "ADD"

    comb_out_z = nodes.new("ShaderNodeCombineXYZ")
    comb_out_z.location = (280.0, -460.0)

    xf_out = nodes.new("GeometryNodeTransform")
    xf_out.location = (440.0, -220.0)

    smooth_out = nodes.new("GeometryNodeSetShadeSmooth")
    smooth_out.location = (600.0, -220.0)
    smooth_out.domain = "FACE"
    _set_input_default(smooth_out, "Shade Smooth", False)

    set_mat = nodes.new("GeometryNodeSetMaterial")
    set_mat.location = (740.0, -220.0)

    cmp_outline = nodes.new("FunctionNodeCompare")
    cmp_outline.location = (600.0, -420.0)
    cmp_outline.data_type = "FLOAT"
    cmp_outline.operation = "GREATER_THAN"
    _set_input_default(cmp_outline, "B", 1e-5)

    sw_outline = nodes.new("GeometryNodeSwitch")
    sw_outline.location = (880.0, -220.0)
    sw_outline.input_type = "GEOMETRY"

    join_final = nodes.new("GeometryNodeJoinGeometry")
    join_final.location = (1220.0, 80.0)

    # --- Links ---
    links.new(group_in.outputs["Geometry"], realize.inputs["Geometry"])

    # Text solidify path
    links.new(realize.outputs["Geometry"], extrude.inputs["Mesh"])
    links.new(group_in.outputs["Text Depth"], extrude.inputs["Offset Scale"])
    links.new(realize.outputs["Geometry"], flip.inputs["Mesh"])
    links.new(extrude.outputs["Mesh"], join_text.inputs["Geometry"])
    links.new(flip.outputs["Mesh"], join_text.inputs["Geometry"])
    links.new(join_text.outputs["Geometry"], merge.inputs["Geometry"])
    links.new(group_in.outputs["Text Depth"], neg_depth.inputs[0])
    links.new(neg_depth.outputs[0], comb_text_z.inputs["Z"])
    links.new(merge.outputs["Geometry"], xf_text.inputs["Geometry"])
    links.new(comb_text_z.outputs["Vector"], xf_text.inputs["Translation"])
    links.new(group_in.outputs["Text Depth"], _enabled_input(cmp_depth, "A"))
    links.new(cmp_depth.outputs["Result"], _enabled_input(sw_text, "Switch"))
    links.new(realize.outputs["Geometry"], _enabled_input(sw_text, "False"))
    links.new(xf_text.outputs["Geometry"], _enabled_input(sw_text, "True"))
    links.new(sw_text.outputs["Output"], smooth_text.inputs[0])

    # Per-char 3-state attributes path
    links.new(group_in.outputs[SOCKET_CHAR_FRAME_IN], enter_start.inputs[0])
    links.new(group_in.outputs[SOCKET_CHAR_FRAME_IN], enter_end.inputs[0])
    links.new(group_in.outputs[SOCKET_TRANSITION_FRAMES], enter_end.inputs[1])
    links.new(scene_time.outputs["Frame"], _enabled_input(map_enter, "Value"))
    links.new(enter_start.outputs[0], _enabled_input(map_enter, "From Min"))
    links.new(enter_end.outputs[0], _enabled_input(map_enter, "From Max"))
    links.new(group_in.outputs[SOCKET_PER_CHAR_MATERIAL], _enabled_input(sw_enter, "Switch"))
    links.new(map_enter.outputs["Result"], _enabled_input(sw_enter, "True"))

    links.new(group_in.outputs[SOCKET_CHAR_FRAME_OUT], exit_start.inputs[0])
    links.new(group_in.outputs[SOCKET_CHAR_FRAME_OUT], exit_end.inputs[0])
    links.new(group_in.outputs[SOCKET_TRANSITION_FRAMES], exit_end.inputs[1])
    links.new(scene_time.outputs["Frame"], _enabled_input(map_exit, "Value"))
    links.new(exit_start.outputs[0], _enabled_input(map_exit, "From Min"))
    links.new(exit_end.outputs[0], _enabled_input(map_exit, "From Max"))
    links.new(group_in.outputs[SOCKET_PER_CHAR_MATERIAL], _enabled_input(sw_exit, "Switch"))
    links.new(map_exit.outputs["Result"], _enabled_input(sw_exit, "True"))

    links.new(smooth_text.outputs[0], store_entered.inputs["Geometry"])
    links.new(sw_enter.outputs["Output"], _enabled_input(store_entered, "Value"))
    links.new(store_entered.outputs["Geometry"], store_finished.inputs["Geometry"])
    links.new(sw_exit.outputs["Output"], _enabled_input(store_finished, "Value"))

    # Outline path
    links.new(edge_nbr.outputs["Face Count"], _enabled_input(cmp_edge, "A"))
    links.new(realize.outputs["Geometry"], mesh_to_curve.inputs["Mesh"])
    links.new(cmp_edge.outputs["Result"], mesh_to_curve.inputs["Selection"])
    links.new(mesh_to_curve.outputs["Curve"], curve_normal.inputs["Curve"])
    links.new(group_in.outputs["Outline Thickness"], mul_thick.inputs[0])
    links.new(group_in.outputs["Text Depth"], max_depth.inputs[0])
    links.new(mul_thick.outputs[0], quad.inputs["Width"])
    links.new(max_depth.outputs[0], quad.inputs["Height"])
    links.new(curve_normal.outputs["Curve"], curve_to_mesh.inputs["Curve"])
    links.new(quad.outputs["Curve"], curve_to_mesh.inputs["Profile Curve"])
    links.new(max_depth.outputs[0], half_neg_depth.inputs[0])
    links.new(group_in.outputs["Z Offset"], add_z.inputs[0])
    links.new(half_neg_depth.outputs[0], add_z.inputs[1])
    links.new(add_z.outputs[0], comb_out_z.inputs["Z"])
    links.new(curve_to_mesh.outputs["Mesh"], xf_out.inputs["Geometry"])
    links.new(comb_out_z.outputs["Vector"], xf_out.inputs["Translation"])
    links.new(xf_out.outputs["Geometry"], smooth_out.inputs[0])
    links.new(smooth_out.outputs[0], set_mat.inputs["Geometry"])
    links.new(group_in.outputs[SOCKET_OUTLINE_MATERIAL], set_mat.inputs["Material"])
    links.new(group_in.outputs["Outline Thickness"], _enabled_input(cmp_outline, "A"))
    links.new(cmp_outline.outputs["Result"], _enabled_input(sw_outline, "Switch"))
    links.new(set_mat.outputs["Geometry"], _enabled_input(sw_outline, "True"))

    # Final merge
    links.new(store_finished.outputs["Geometry"], join_final.inputs["Geometry"])
    links.new(sw_outline.outputs["Output"], join_final.inputs["Geometry"])
    links.new(join_final.outputs["Geometry"], group_out.inputs["Geometry"])


def get_or_create_lyric_solidify_node_group(outline_material=None, reset=False):
    """Create or reuse the tagged lyc_solidify Geometry Node group."""
    node_group = next(
        (
            ng
            for ng in bpy.data.node_groups
            if ng.type == "GEOMETRY"
            and ng.get(PV_TAG, False)
            and ng.name.startswith(LYRIC_SOLIDIFY_GROUP_NAME)
        ),
        None,
    )
    needs_build = (
        node_group is None
        or reset
        or _interface_socket_by_name(node_group, SOCKET_PER_CHAR_MATERIAL) is None
    )
    if node_group is None:
        node_group = bpy.data.node_groups.new(
            LYRIC_SOLIDIFY_GROUP_NAME, "GeometryNodeTree"
        )
    if needs_build:
        _build_lyric_solidify_tree(node_group, outline_material)
    elif outline_material is not None:
        mat_sock = _interface_socket_by_name(node_group, SOCKET_OUTLINE_MATERIAL)
        if mat_sock is not None:
            mat_sock.default_value = outline_material
    node_group[PV_TAG] = True
    return node_group


def _set_modifier_input(mod, identifier, value):
    """Set a Geometry Nodes modifier input across Blender 5.2+ and legacy APIs."""
    props = getattr(mod, "properties", None)
    inputs = getattr(props, "inputs", None) if props is not None else None
    if inputs is not None and hasattr(inputs, identifier):
        socket_prop = getattr(inputs, identifier)
        if hasattr(socket_prop, "value"):
            try:
                socket_prop.value = value
                return True
            except (TypeError, ValueError, AttributeError):
                pass
    try:
        mod[identifier] = value
        return True
    except (TypeError, KeyError, ValueError):
        return False


def set_lyric_solidify_inputs(
    mod,
    *,
    outline_material=None,
    per_char_enabled=None,
    char_frame_in=None,
    char_frame_out=None,
    transition_frames=None,
):
    """Update per-object lyc_solidify modifier inputs by interface socket name."""
    node_group = getattr(mod, "node_group", None)
    if node_group is None:
        return
    mapping = (
        (SOCKET_OUTLINE_MATERIAL, outline_material),
        (SOCKET_PER_CHAR_MATERIAL, None if per_char_enabled is None else bool(per_char_enabled)),
        (SOCKET_CHAR_FRAME_IN, None if char_frame_in is None else float(char_frame_in)),
        (SOCKET_CHAR_FRAME_OUT, None if char_frame_out is None else float(char_frame_out)),
        (SOCKET_TRANSITION_FRAMES, None if transition_frames is None else float(transition_frames)),
    )
    for socket_name, value in mapping:
        if value is None:
            continue
        sock = _interface_socket_by_name(node_group, socket_name)
        if sock is not None:
            _set_modifier_input(mod, sock.identifier, value)


def attach_lyric_solidify_modifier(
    obj,
    node_group,
    outline_material=None,
    *,
    per_char_enabled=True,
    char_frame_in=1.0,
    char_frame_out=2.0,
    transition_frames=DEFAULT_TRANSITION_FRAMES,
):
    """Attach the lyc_solidify Geometry Nodes modifier and configure per-char parameters."""
    mod = obj.modifiers.get(LYRIC_SOLIDIFY_GROUP_NAME)
    if mod is None or mod.type != "NODES":
        mod = obj.modifiers.new(name=LYRIC_SOLIDIFY_GROUP_NAME, type="NODES")
    mod.node_group = node_group
    set_lyric_solidify_inputs(
        mod,
        outline_material=outline_material,
        per_char_enabled=per_char_enabled,
        char_frame_in=char_frame_in,
        char_frame_out=char_frame_out,
        transition_frames=transition_frames,
    )
    return mod
