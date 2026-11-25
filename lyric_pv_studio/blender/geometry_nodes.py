"""Geometry Nodes setup for default lyric text thickness and outline."""

import bpy

from ..constants import PV_TAG

LYRIC_SOLIDIFY_GROUP_NAME = "lyc_solidify"
DEFAULT_TEXT_DEPTH = 0.02
DEFAULT_OUTLINE_THICKNESS = 0.0055
DEFAULT_OUTLINE_Z_OFFSET = -0.0015


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


def _build_lyric_solidify_tree(node_group, outline_material):
    """Populate the lyc_solidify Geometry Node tree matching the default preset."""
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
            name="Outline Material", in_out="INPUT", socket_type="NodeSocketMaterial"
        )
        if outline_material is not None:
            mat_sock.default_value = outline_material

    nodes = node_group.nodes
    links = node_group.links

    group_in = nodes.new("NodeGroupInput")
    group_in.location = (-1100.0, 0.0)

    group_out = nodes.new("NodeGroupOutput")
    group_out.location = (1100.0, 0.0)

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
    join_final.location = (960.0, 80.0)

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
    links.new(group_in.outputs["Outline Material"], set_mat.inputs["Material"])
    links.new(group_in.outputs["Outline Thickness"], _enabled_input(cmp_outline, "A"))
    links.new(cmp_outline.outputs["Result"], _enabled_input(sw_outline, "Switch"))
    links.new(set_mat.outputs["Geometry"], _enabled_input(sw_outline, "True"))

    # Final merge
    links.new(smooth_text.outputs[0], join_final.inputs["Geometry"])
    links.new(sw_outline.outputs["Output"], join_final.inputs["Geometry"])
    links.new(join_final.outputs["Geometry"], group_out.inputs["Geometry"])


def get_or_create_lyric_solidify_node_group(outline_material=None):
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
    if node_group is None:
        node_group = bpy.data.node_groups.new(
            LYRIC_SOLIDIFY_GROUP_NAME, "GeometryNodeTree"
        )
        _build_lyric_solidify_tree(node_group, outline_material)
    elif outline_material is not None and hasattr(node_group, "interface"):
        for item in node_group.interface.items_tree:
            if (
                item.item_type == "SOCKET"
                and item.in_out == "INPUT"
                and item.name == "Outline Material"
            ):
                item.default_value = outline_material
                break
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
                return
            except (TypeError, ValueError, AttributeError):
                pass
    try:
        mod[identifier] = value
    except (TypeError, KeyError, ValueError):
        pass


def attach_lyric_solidify_modifier(obj, node_group, outline_material=None):
    """Attach the default lyc_solidify Geometry Nodes modifier to a lyric object."""
    mod = obj.modifiers.get(LYRIC_SOLIDIFY_GROUP_NAME)
    if mod is None or mod.type != "NODES":
        mod = obj.modifiers.new(name=LYRIC_SOLIDIFY_GROUP_NAME, type="NODES")
    mod.node_group = node_group
    if outline_material is not None and hasattr(node_group, "interface"):
        for item in node_group.interface.items_tree:
            if (
                item.item_type == "SOCKET"
                and item.in_out == "INPUT"
                and item.name == "Outline Material"
            ):
                _set_modifier_input(mod, item.identifier, outline_material)
                break
    return mod
