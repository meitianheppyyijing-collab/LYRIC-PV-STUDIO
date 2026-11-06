bl_info = {
    "name": "LYRIC PV STUDIO",
    "author": "OpenAI",
    "version": (0, 5, 15),
    "blender": (5, 2, 0),
    "location": "View3D > Sidebar > Lyric PV",
    "description": "Create animated lyric typography, per-character motion and text effects from LRC files",
    "category": "Animation",
}

import bpy
import json
import re
import random
import math
from mathutils import Vector
from bpy.app.handlers import persistent
from bpy.props import (
    StringProperty,
    PointerProperty,
    FloatProperty,
    IntProperty,
    FloatVectorProperty,
    BoolProperty,
    EnumProperty,
)
from bpy.types import Operator, Panel, PropertyGroup


PV_ROOT_NAME = "LYRIC_PV_STUDIO_GENERATED"
PV_TAG = "lyric_pv_studio_generated"
PV_VERSION = "0.5.15"

_ENTRANCE_CACHE = {}
_CONTROLLER_CACHE = {}


def invalidate_entrance_cache():
    """Invalidate per-scene entrance indexes after generated objects change."""
    _ENTRANCE_CACHE.clear()
    _CONTROLLER_CACHE.clear()


def parse_lrc_text(text):
    timestamp_re = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]")
    offset_re = re.compile(r"^\s*\[offset\s*:\s*([+-]?\d+)\s*\]\s*$", re.I)
    offset_ms = 0
    entries = []
    for raw_line in text.replace("\ufeff", "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        offset_match = offset_re.match(line)
        if offset_match:
            offset_ms = int(offset_match.group(1))
            continue
        matches = list(timestamp_re.finditer(line))
        if not matches:
            continue
        lyric = timestamp_re.sub("", line).strip()
        if not lyric:
            continue
        for match in matches:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            fraction = match.group(3) or "0"
            if len(fraction) == 1:
                fraction_value = int(fraction) / 10.0
            elif len(fraction) == 2:
                fraction_value = int(fraction) / 100.0
            else:
                fraction_value = int(fraction) / 1000.0
            total = minutes * 60.0 + seconds + fraction_value + offset_ms / 1000.0
            entries.append((max(0.0, total), lyric))
    entries.sort(key=lambda item: item[0])
    return entries, offset_ms



def parse_yrc_text(text):
    """Parse common NetEase-style YRC lines while retaining per-token timing.

    Returns sentence entries compatible with the existing LRC generator and a
    parallel detailed structure containing each timed text token.
    """
    sentences = []
    detailed = []
    token_re = re.compile(r"\((\d+)\s*,\s*(\d+)\s*,\s*(-?\d+)\)(.*?)(?=\(\d+\s*,\s*\d+\s*,\s*-?\d+\)|$)")
    header_re = re.compile(r"^\s*\[(\d+)\s*,\s*(\d+)\](.*)$")
    for raw in text.replace("\ufeff", "").splitlines():
        line = raw.strip()
        if not line or line.startswith("[") and not header_re.match(line):
            continue
        hm = header_re.match(line)
        if not hm:
            continue
        sentence_start_ms, sentence_duration_ms = int(hm.group(1)), int(hm.group(2))
        body = hm.group(3)
        tokens = []
        for match in token_re.finditer(body):
            start_ms, duration_ms, flag = map(int, match.group(1, 2, 3))
            value = match.group(4)
            if value:
                tokens.append({"start_ms": start_ms, "duration_ms": duration_ms,
                               "flag": flag, "text": value})
        lyric = "".join(token["text"] for token in tokens)
        if lyric.strip():
            sentences.append((max(0.0, sentence_start_ms / 1000.0), lyric))
            detailed.append({"start_ms": sentence_start_ms,
                             "duration_ms": sentence_duration_ms,
                             "text": lyric, "tokens": tokens})
    sentences.sort(key=lambda item: item[0])
    detailed.sort(key=lambda item: item["start_ms"])
    return sentences, detailed


def yrc_character_frame_map(timed_entry, fps, start_frame, time_offset=0.0):
    """Expand YRC token timings to one frame start per displayed character."""
    result = []
    if not isinstance(timed_entry, dict):
        return result
    offset_ms = float(time_offset) * 1000.0
    for token in timed_entry.get("tokens", []):
        value = str(token.get("text", ""))
        if not value:
            continue
        token_start = float(token.get("start_ms", 0)) - offset_ms
        token_duration = max(0.0, float(token.get("duration_ms", 0)))
        # Multi-character tokens are spread evenly across their source duration.
        count = max(1, len(value))
        for char_index, _char in enumerate(value):
            char_ms = token_start + token_duration * (char_index / count)
            result.append(max(start_frame, start_frame + round((char_ms / 1000.0) * fps)))
    return result



def estimate_lyric_unit_advance(text, base_size):
    """Fallback advance in local text units when Blender has not evaluated FONT bounds."""
    if not text:
        return max(float(base_size) * 0.5, 1e-4)
    size = max(float(base_size), 1e-4)
    if text.isspace():
        return size * 0.34 * max(1, len(text))
    advance = 0.0
    for ch in text:
        code = ord(ch)
        if ch in "，。！？；：、（）【】《》「」『』〈〉…—·“”‘’":
            advance += size * 0.95
        elif code >= 0x2E80 or code >= 0x1F000:
            advance += size
        elif ch in "ilI|!.,'`:;":
            advance += size * 0.32
        elif ch in "mwMW@%&":
            advance += size * 0.82
        else:
            advance += size * 0.60
    return max(advance, size * 0.18)


def lyric_display_units(text):
    """Group Latin words while preserving spaces and CJK per-character units."""
    units = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch.isspace():
            j = i + 1
            while j < len(text) and text[j].isspace():
                j += 1
            units.append((text[i:j], i))
            i = j
            continue
        # Apostrophes at the start of a contraction fragment (e.g. 'n')
        # belong to the following Latin letters; internal apostrophes stay joined.
        if ch.isascii() and (ch.isalnum() or (ch in "'’" and i + 1 < len(text) and text[i + 1].isascii() and text[i + 1].isalnum())):
            j = i + 1
            while j < len(text):
                nxt = text[j]
                if nxt.isascii() and (nxt.isalnum() or nxt in "'’"):
                    j += 1
                elif nxt in "-–" and j + 1 < len(text) and text[j + 1].isascii() and text[j + 1].isalnum():
                    j += 1
                else:
                    break
            units.append((text[i:j], i))
            i = j
            continue
        units.append((ch, i))
        i += 1
    return units

def read_lyric_file(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            return handle.read()
    except UnicodeDecodeError:
        with open(path, "r", encoding="gb18030") as handle:
            return handle.read()


def get_or_create_collection(scene):
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
    for obj in list(collection.objects):
        _remove_tagged_object(obj)
    for child in list(collection.children):
        if child.get(PV_TAG, False):
            _clean_tagged_collection_tree(child)
            if not child.objects and not child.children:
                bpy.data.collections.remove(child)
    return not collection.objects and not collection.children


def remove_generated_collection():
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


def camera_frame_bounds(scene, camera, distance):
    frame = camera.data.view_frame(scene=scene)
    zs = [abs(v.z) for v in frame if abs(v.z) > 1e-8]
    reference_depth = sum(zs) / len(zs) if zs else 1.0
    xs = [v.x * distance / reference_depth for v in frame]
    ys = [v.y * distance / reference_depth for v in frame]
    return min(xs), max(xs), min(ys), max(ys)


def update_lyric_viewport_visibility(self, context):
    collection = bpy.data.collections.get(PV_ROOT_NAME)
    if collection is None:
        return
    hide_lyrics = bool(self.hide_lyrics_in_viewport)
    view_layer = context.view_layer if context else None
    for obj in collection.all_objects:
        if obj.get(PV_TAG, False):
            obj.hide_set(hide_lyrics, view_layer=view_layer)


def update_lyric_font_size(self, context):
    collection = bpy.data.collections.get(PV_ROOT_NAME)
    if collection is None:
        return
    size = float(self.font_size)
    for obj in collection.all_objects:
        if obj.get(PV_TAG, False) and obj.type == "FONT" and obj.data:
            multiplier = float(obj.get("lyric_font_multiplier", 1.0))
            obj.data.size = size * multiplier


def get_occlusion_safe_distance(scene, camera, props):
    base_distance = float(props.camera_distance)
    target = getattr(props, "occlusion_target", None)
    if not getattr(props, "keep_behind_target", False) or target is None:
        return base_distance
    if target.type == "MESH":
        candidates = [target]
    elif target.type == "ARMATURE":
        candidates = []
        for obj in scene.objects:
            if obj.type != "MESH":
                continue
            driven = any(mod.type == "ARMATURE" and mod.object == target for mod in obj.modifiers)
            parent = obj.parent
            parented = False
            while parent is not None:
                if parent == target:
                    parented = True
                    break
                parent = parent.parent
            if driven or parented:
                candidates.append(obj)
    else:
        candidates = []
    if not candidates:
        return base_distance
    try:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        camera_inverse = camera.matrix_world.inverted_safe()
    except Exception:
        return base_distance
    farthest_depth = None
    for source in candidates:
        try:
            evaluated = source.evaluated_get(depsgraph)
            for corner in evaluated.bound_box:
                camera_corner = camera_inverse @ (evaluated.matrix_world @ Vector(corner))
                depth = -camera_corner.z
                if depth > 0.0:
                    farthest_depth = depth if farthest_depth is None else max(farthest_depth, depth)
        except Exception:
            continue
    if farthest_depth is None:
        return base_distance
    return max(base_distance, farthest_depth + float(props.occlusion_margin))


def get_character_screen_bounds(scene, camera, target, distance):
    if target is None:
        return None
    if target.type == "MESH":
        candidates = [target]
    elif target.type == "ARMATURE":
        candidates = []
        for obj in scene.objects:
            if obj.type != "MESH":
                continue
            driven = any(mod.type == "ARMATURE" and mod.object == target for mod in obj.modifiers)
            parent = obj.parent
            parented = False
            while parent is not None:
                if parent == target:
                    parented = True
                    break
                parent = parent.parent
            if driven or parented:
                candidates.append(obj)
    else:
        return None
    if not candidates:
        return None
    try:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        camera_inverse = camera.matrix_world.inverted_safe()
    except Exception:
        return None
    points = []
    for source in candidates:
        try:
            evaluated = source.evaluated_get(depsgraph)
            for corner in evaluated.bound_box:
                co = camera_inverse @ (evaluated.matrix_world @ Vector(corner))
                if co.z < -1e-5:
                    scale = distance / max(-co.z, 1e-5)
                    points.append((co.x * scale, co.y * scale))
        except Exception:
            continue
    if not points:
        return None
    return (min(v[0] for v in points), max(v[0] for v in points),
            min(v[1] for v in points), max(v[1] for v in points))


def nudge_lyric_away_from_character(scene, camera, props, x, y, width, height, distance, frame_bounds):
    target = getattr(props, "occlusion_target", None)
    if target is None:
        return x, y
    char_bounds = get_character_screen_bounds(scene, camera, target, distance)
    if char_bounds is None:
        return x, y
    min_x, max_x, min_y, max_y = frame_bounds
    fw, fh = max_x-min_x, max_y-min_y
    half_w, half_h = max(width, fw*0.025)*0.5, max(height, fh*0.018)*0.5

    def overlap(cx, cy):
        a0, a1 = cx-half_w, cx+half_w
        b0, b1 = cy-half_h, cy+half_h
        ix = max(0.0, min(a1, char_bounds[1])-max(a0, char_bounds[0]))
        iy = max(0.0, min(b1, char_bounds[3])-max(b0, char_bounds[2]))
        return ix*iy

    if overlap(x, y) <= 1e-8:
        return x, y
    dx, dy = fw*0.045, fh*0.045
    candidates = [(x-dx,y),(x+dx,y),(x,y-dy),(x,y+dy),
                  (x-dx,y-dy),(x+dx,y-dy),(x-dx,y+dy),(x+dx,y+dy)]
    safe_min_x, safe_max_x = min_x+half_w+fw*0.015, max_x-half_w-fw*0.015
    safe_min_y, safe_max_y = min_y+half_h+fh*0.015, max_y-half_h-fh*0.015
    ranked=[]
    for cx,cy in candidates:
        cx=max(safe_min_x,min(safe_max_x,cx)); cy=max(safe_min_y,min(safe_max_y,cy))
        ranked.append((overlap(cx,cy), (cx-x)**2+(cy-y)**2, cx, cy))
    best=min(ranked, key=lambda item:(item[0],item[1]))
    return best[2], best[3]


def update_lyric_positions(self, context):
    scene = context.scene if context else bpy.context.scene
    if scene is None:
        return
    collection = bpy.data.collections.get(PV_ROOT_NAME)
    if collection is None:
        return
    props = getattr(scene, "lyric_pv_props", None)
    if props is None:
        return
    controller = next(
        (obj for obj in collection.all_objects
         if obj.get(PV_TAG, False) and obj.get("lyric_pv_controller", False)),
        None,
    )
    if controller is None:
        return
    camera = controller.parent
    if camera is None or camera.type != "CAMERA":
        camera = props.target_camera or scene.camera
    if camera is None or camera.type != "CAMERA":
        return
    distance = get_occlusion_safe_distance(scene, camera, props)
    min_x, max_x, min_y, max_y = camera_frame_bounds(scene, camera, distance)
    frame_width = max_x - min_x
    frame_height = max_y - min_y
    x = min_x + frame_width * (props.display_x + 0.5)
    y = min_y + frame_height * (props.display_y + 0.5)
    controller.parent = camera
    controller.location = (x, y, -distance)
    controller.rotation_euler = (0.0, 0.0, 0.0)
    base_distance = max(1e-4, float(controller.get("lyric_base_distance", distance)))
    depth_ratio = max(0.25, min(4.0, float(distance) / base_distance))
    controller.scale = (depth_ratio, depth_ratio, depth_ratio)


def _build_entrance_index(scene, collection, cache_key, current_frame):
    """Build an event index once; sequential frames then update only changed objects."""
    events = {}
    objects = []
    for obj in collection.all_objects:
        try:
            if not (obj.get(PV_TAG, False) and obj.type == "FONT"
                    and obj.get("lyric_entrance_enabled", False)):
                continue
            frame_in = int(float(obj.get("lyric_frame_in", 1.0)))
            frame_out = int(float(obj.get("lyric_frame_out", frame_in + 2)))
            first = frame_in - 1
            last_exclusive = frame_out + 2
            events.setdefault(first, [[], []])[0].append(obj)
            events.setdefault(last_exclusive, [[], []])[1].append(obj)
            objects.append(obj)
        except (ReferenceError, TypeError, ValueError):
            continue
    active = set()
    for frame, (added, removed) in events.items():
        if frame <= current_frame:
            active.difference_update(removed)
            active.update(added)
    _ENTRANCE_CACHE[cache_key] = {
        "events": events,
        "active": active,
        "frame": int(current_frame),
        "objects": tuple(objects),
    }
    return _ENTRANCE_CACHE[cache_key]


def update_lyric_entrance_positions(scene):
    if scene is None:
        return
    collection = bpy.data.collections.get(PV_ROOT_NAME)
    props = getattr(scene, "lyric_pv_props", None)
    if collection is None or props is None:
        return
    try:
        cache_key = (scene.as_pointer(), collection.as_pointer())
        controller = _CONTROLLER_CACHE.get(cache_key)
        if controller is None or controller.name not in bpy.data.objects:
            controller = next(
                (obj for obj in collection.all_objects
                 if obj.get(PV_TAG, False) and obj.get("lyric_pv_controller", False)),
                None,
            )
            if controller is None:
                return
            _CONTROLLER_CACHE[cache_key] = controller
        camera = controller.parent
        if camera is None or camera.type != "CAMERA":
            camera = props.target_camera or scene.camera
        if camera is None or camera.type != "CAMERA":
            return
        depth = abs(float(controller.location.z))
        if depth < 1e-6:
            depth = float(props.camera_distance)
        min_x, max_x, min_y, max_y = camera_frame_bounds(scene, camera, depth)
        frame_width = max(1e-6, max_x - min_x)
        frame_height = max(1e-6, max_y - min_y)
        slide_frames = max(1, int(props.slide_frames))
        distance_factor = max(1.0, float(props.entrance_distance))
        current_frame = int(scene.frame_current)
        index = _ENTRANCE_CACHE.get(cache_key)
        if index is None or current_frame != index["frame"] + 1:
            index = _build_entrance_index(scene, collection, cache_key, current_frame)
        else:
            # Sequential playback/render: process only events at this frame.
            added, removed = index["events"].get(current_frame, ((), ()))
            index["active"].difference_update(removed)
            index["active"].update(added)
            index["frame"] = current_frame
        for obj in index["active"]:
            try:
                frame_in = float(obj.get("lyric_frame_in", 1.0))
                frame_out = float(obj.get("lyric_frame_out", frame_in + slide_frames + 1.0))
                fade_frames = int(obj.get("lyric_fade_frames", 0))
                direction = str(obj.get("lyric_entrance_direction", "LEFT"))
                line_limit = max(1, int(frame_out - frame_in - fade_frames))
                effective_slide = min(slide_frames, line_limit)
                elapsed = current_frame - frame_in
                t = max(0.0, min(1.0, elapsed / effective_slide))
                eased = 1.0 - (1.0 - t) ** 3
                if direction == "NONE":
                    start_offset = (0.0, 0.0, 0.0)
                elif direction == "LEFT":
                    start_offset = (-frame_width * distance_factor, 0.0, 0.0)
                elif direction == "RIGHT":
                    start_offset = (frame_width * distance_factor, 0.0, 0.0)
                elif direction == "TOP":
                    start_offset = (0.0, frame_height * distance_factor, 0.0)
                else:
                    start_offset = (0.0, -frame_height * distance_factor, 0.0)
                if fade_frames > 0 and current_frame > frame_out - fade_frames:
                    exit_t = max(0.0, min(1.0, (current_frame - (frame_out - fade_frames)) / max(1, fade_frames)))
                    exit_eased = exit_t * exit_t * (3.0 - 2.0 * exit_t)
                    motion_x = -start_offset[0] * exit_eased
                    motion_y = -start_offset[1] * exit_eased
                else:
                    motion_x = start_offset[0] * (1.0 - eased)
                    motion_y = start_offset[1] * (1.0 - eased)
                base_x = float(obj.get("lyric_base_x", 0.0))
                base_y = float(obj.get("lyric_base_y", 0.0))
                base_z = float(obj.get("lyric_base_z", 0.0))
                pop_enabled = bool(obj.get("lyric_pop_enabled", False))
                pop_frames = max(1, int(obj.get("lyric_pop_frames", 4)))
                pop_t = max(0.0, min(1.0, (current_frame - frame_in) / pop_frames)) if pop_enabled else 1.0
                pop_eased = 1.0 - (1.0 - pop_t) ** 3
                pop_y = float(obj.get("lyric_pop_y", 0.0)) * (1.0 - pop_eased)
                pop_z = float(obj.get("lyric_pop_z", 0.0)) * (1.0 - pop_eased)
                obj.location = (base_x + motion_x, base_y + motion_y + pop_y, base_z + pop_z)
            except (ReferenceError, TypeError, ValueError):
                continue
    except (ReferenceError, RuntimeError, TypeError, ValueError):
        invalidate_entrance_cache()
        return


def update_lyric_entrance_settings(self, context):
    scene = context.scene if context else bpy.context.scene
    update_lyric_entrance_positions(scene)


@persistent
def lyric_pv_frame_change_handler(scene, depsgraph=None):
    update_lyric_entrance_positions(scene)


def make_text_material(name, color, glow_strength=0.35):
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
LAYOUT_STYLES = ("CLEAN_CENTER", "LEFT_TITLE", "RIGHT_TITLE", "VERTICAL", "DIAGONAL", "WIDE_SPACING", "EMPHASIS", "PER_CHARACTER")
ENTRANCE_DIRECTIONS = ("LEFT", "RIGHT", "TOP", "BOTTOM")

# 已移除 ELECTRIC（电光）
ANIMATION_SCHEMES = ("SLIDE", "POP", "FADE", "ROTATE", "GLITCH", "BOUNCE", "FLOAT")


def _weighted_choice(rng, items, weights, amount=1.0):
    """随机强度越低越偏向基础选项；越高越容易抽到表现型选项。"""
    amount = max(0.0, min(1.0, float(amount)))
    base = [float(w) for w in weights]
    if not items:
        return None
    # amount=0 时仍保留少量变化，避免完全僵化；amount=1 使用完整权重。
    weights = [max(0.01, 1.0 + (w - 1.0) * amount) for w in base]
    return rng.choices(items, weights=weights, k=1)[0]


def _choose_animation(rng, props):
    mode = props.animation_random_mode
    amount = _random_amount(props)
    pools = {
        "GENTLE": (("FADE", "SLIDE", "FLOAT", "ROTATE"), (1.35, 1.25, 0.8, 0.65)),
        "IMPACT": (("POP", "BOUNCE", "GLITCH", "SLIDE"), (1.15, 0.9, 0.45, 1.3)),
        "TEXT_FX": (("GLITCH",), (1.0,)),
        "MIXED": (ANIMATION_SCHEMES, (1.35, 0.9, 1.15, 0.75, 0.45, 0.65, 0.85)),
    }
    pool, weights = pools.get(mode, pools["MIXED"])
    return _weighted_choice(rng, pool, weights, amount)


def _random_amount(props):
    """0 = 完全稳定，100 = 最大随机偏移。"""
    return 1.0 if props is None else max(0.0, min(1.0, props.random_amount / 100.0))


def _new_layout_record(rng, props=None):
    amount = _random_amount(props)
    animation = _choose_animation(rng, props) if props and props.animation_random_enabled else "SLIDE"
    style_pool = ("CLEAN_CENTER", "LEFT_TITLE", "RIGHT_TITLE", "WIDE_SPACING",
                  "VERTICAL", "DIAGONAL", "EMPHASIS", "PER_CHARACTER")
    style_weights = (1.45, 1.2, 1.2, 0.9, 0.55, 0.55, 0.5, 0.28)
    style = _weighted_choice(rng, style_pool, style_weights, amount)
    return {"style": style,
            "font_multiplier": round(1.0 + rng.uniform(-0.18, 0.22) * amount, 3),
            "x": round(rng.uniform(-0.14, 0.14) * amount, 4),
            "y": round(rng.uniform(-0.08, 0.08) * amount, 4),
            "rotation": round(rng.uniform(-10.0, 10.0) * amount, 2),
            "spacing": round(1.0 + rng.uniform(-0.10, 0.15) * amount, 3),
             "animation": animation,
            "entrance": _weighted_choice(rng, ENTRANCE_DIRECTIONS, (1.15, 1.15, 0.85, 0.85), amount),
            "locked": False}


def _split_sections(entries, gap=4.0):
    """按时间间隔把歌词切成段落，供 PER_SECTION 排版模式使用。"""
    if not entries:
        return []
    sections = [[0]]
    for i in range(1, len(entries)):
        if entries[i][0] - entries[i - 1][0] > gap:
            sections.append([i])
        else:
            sections[-1].append(i)
    return sections


def load_layout_records(scene, entries, props):
    try:
        saved = json.loads(scene.get("lyric_pv_layouts", "{}"))
        if not isinstance(saved, dict):
            saved = {}
    except Exception:
        saved = {}
    rng = random.Random(int(props.random_seed))
    result = {}
    styles = LAYOUT_STYLES if props.layout_pool == "ALL" else LAYOUT_STYLES[:4]
    sections = _split_sections(entries)
    section_of = {}
    if props.layout_mode == "PER_SECTION":
        for si, idxs in enumerate(sections):
            for idx in idxs:
                section_of[idx] = si
    section_template = {}
    for i, _entry in enumerate(entries):
        key = str(i)
        record = saved.get(key)
        if isinstance(record, dict) and all(k in record for k in ("style", "font_multiplier", "x", "y", "rotation", "spacing", "animation", "entrance")):
            record = dict(record)
            if record.get("animation") in {"PARTICLE_IN", "PARTICLE_OUT", "ELECTRIC"}:
                record["animation"] = "GLITCH" if record.get("animation") == "ELECTRIC" else "SLIDE"
                record["animation_v050"] = True
            if not record.get("animation_v050", False) and not record.get("locked", False):
                record["animation"] = _choose_animation(rng, props)
                record["animation_v050"] = True
            result[key] = record
        else:
            if props.layout_mode == "PER_SECTION":
                si = section_of.get(i, 0)
                if si not in section_template:
                    section_template[si] = _new_layout_record(rng, props)
                record = dict(section_template[si])
            elif props.layout_mode == "FIXED":
                record = _new_layout_record(rng, props)
                record.update({"style": "CLEAN_CENTER", "font_multiplier": 1.0, "x": 0.0, "y": 0.0,
                               "rotation": 0.0, "spacing": 1.0, "animation": "SLIDE", "entrance": "LEFT"})
            else:
                record = _new_layout_record(rng, props)
            if not props.random_layout_enabled:
                record.update({"style": "CLEAN_CENTER", "font_multiplier": 1.0, "x": 0.0, "y": 0.0,
                               "rotation": 0.0, "spacing": 1.0, "animation": "SLIDE", "entrance": "LEFT"})
            elif props.layout_pool != "ALL":
                record["style"] = _weighted_choice(
                    rng, styles, (1.45, 1.2, 1.2, 0.9), _random_amount(props))
            record["animation_v050"] = True
            result[key] = record
    return result


def reroll_layout_records(scene, props, indices=None):
    try:
        records = json.loads(scene.get("lyric_pv_layouts", "{}"))
    except Exception:
        records = {}
    if not isinstance(records, dict):
        records = {}
    rng = random.Random(int(props.random_seed) + int(scene.get("lyric_pv_reroll", 0)) + 1)
    target = list(records.keys()) if indices is None else [str(i) for i in indices]
    for key in target:
        old = records.get(key, {})
        if old.get("locked", False):
            continue
        new = _new_layout_record(rng, props)
        new["animation_v050"] = True
        if not props.random_layout_enabled:
            new.update({"style": "CLEAN_CENTER", "font_multiplier": 1.0, "x": 0.0, "y": 0.0,
                        "rotation": 0.0, "spacing": 1.0, "animation": "SLIDE", "entrance": "LEFT"})
        elif props.layout_pool != "ALL":
            new["style"] = _weighted_choice(
                rng, LAYOUT_STYLES[:4], (1.45, 1.2, 1.2, 0.9), _random_amount(props))
        records[key] = new
    scene["lyric_pv_reroll"] = int(scene.get("lyric_pv_reroll", 0)) + 1
    scene["lyric_pv_layouts"] = json.dumps(records, ensure_ascii=False, sort_keys=True)
    return records


def _key_object_scale(obj, frame_in, frame_out, fade, pop_enabled):
    base = obj.scale.copy()
    hidden = base * 0.001
    obj.scale = hidden if pop_enabled else base
    obj.keyframe_insert(data_path="scale", frame=frame_in)
    if pop_enabled:
        obj.scale = base
        obj.keyframe_insert(data_path="scale", frame=min(frame_in + max(2, fade), frame_out - 1))
    if fade > 0 and frame_out - fade > frame_in:
        obj.keyframe_insert(data_path="scale", frame=frame_out-fade)
        obj.scale = hidden
        obj.keyframe_insert(data_path="scale", frame=frame_out)
    else:
        obj.scale = base
        obj.keyframe_insert(data_path="scale", frame=frame_out)
    action = obj.animation_data.action if obj.animation_data else None
    if action:
        try:
            for fc in action.fcurves:
                for key in fc.keyframe_points:
                    key.interpolation="BEZIER"; key.handle_left_type="AUTO_CLAMPED"; key.handle_right_type="AUTO_CLAMPED"
        except (AttributeError, TypeError):
            pass


def apply_text_animation(obj, record, frame_in, frame_out, props, rng):
    mode = record.get("animation", "SLIDE")
    strength = max(0.0, min(1.0, float(props.animation_intensity) / 100.0)) * _random_amount(props)
    base_scale = obj.scale.copy()
    base_rotation = obj.rotation_euler.copy()
    reveal = max(2, min(12, int((frame_out-frame_in) * 0.12)))
    end_in = min(frame_out, frame_in + reveal)
    if mode in {"ROTATE", "BOUNCE", "FLOAT", "GLITCH"}:
        obj.rotation_euler.z = base_rotation.z + math.radians((18.0 if rng.random() > .5 else -18.0) * strength)
        obj.keyframe_insert(data_path="rotation_euler", frame=frame_in)
        obj.rotation_euler = base_rotation
        obj.keyframe_insert(data_path="rotation_euler", frame=end_in)
    if mode == "BOUNCE":
        obj.rotation_euler.z = base_rotation.z + math.radians(3.0 * strength)
        obj.keyframe_insert(data_path="rotation_euler", frame=min(frame_in + max(2, reveal//2), frame_out))
        obj.rotation_euler = base_rotation
        obj.keyframe_insert(data_path="rotation_euler", frame=end_in)
    if mode == "FLOAT":
        mid = min(frame_out-1, frame_in + max(3, (frame_out-frame_in)//2))
        obj.rotation_euler.z = base_rotation.z + math.radians(1.5 * strength)
        obj.keyframe_insert(data_path="rotation_euler", frame=mid)
        obj.rotation_euler = base_rotation
        obj.keyframe_insert(data_path="rotation_euler", frame=frame_out)
    # ELECTRIC 已移除：不再每句复制材质做发光脉冲
    action = obj.animation_data.action if obj.animation_data else None
    if action:
        try:
            for fc in action.fcurves:
                for key in fc.keyframe_points:
                    key.interpolation = "BEZIER"
                    key.handle_left_type = "AUTO_CLAMPED"
                    key.handle_right_type = "AUTO_CLAMPED"
        except (AttributeError, TypeError):
            pass
class LYRICPV_Properties(PropertyGroup):
    lrc_path: StringProperty(
        name="LRC 文件",
        description="选择要导入的 .lrc 歌词文件",
        subtype="FILE_PATH",
        default="",
    )
    yrc_path: StringProperty(
        name="YRC 文件",
        description="选择要导入的 .yrc 逐字时间歌词文件",
        subtype="FILE_PATH",
        default="",
    )
    target_camera: PointerProperty(
        name="摄像机",
        description="用于定位歌词的摄像机",
        type=bpy.types.Object,
        poll=lambda self, obj: obj is not None and obj.type == "CAMERA",
    )
    occlusion_target: PointerProperty(
        name="人物遮挡目标",
        description="吸管选择人物网格，或选择人物骨架以查找其关联网格",
        type=bpy.types.Object,
        poll=lambda self, obj: obj is not None and obj.type in {"MESH", "ARMATURE"},
        update=update_lyric_positions,
    )
    keep_behind_target: BoolProperty(
        name="字幕避开人物",
        description="启用后将字幕平面放到所选人物网格后方；关闭时使用原摄像机距离",
        default=False,
        update=update_lyric_positions,
    )
    occlusion_margin: FloatProperty(
        name="人物后方间距",
        description="字幕与人物最远表面之间的额外距离",
        default=0.08,
        min=0.0,
        max=10.0,
        precision=3,
        update=update_lyric_positions,
    )
    font_size: FloatProperty(
        name="字体大小",
        description="歌词文字的大小",
        default=0.22,
        min=0.01,
        max=10.0,
        precision=3,
        update=update_lyric_font_size,
    )
    font_path: StringProperty(
        name="字体文件",
        description="可选：选择 .ttf/.otf 字体；留空使用 Blender 默认字体",
        subtype="FILE_PATH",
    )
    character_stagger: IntProperty(
        name="逐字间隔（帧）",
        description="每个字符依次出现的帧间隔；0 表示整句同时出现",
        default=2, min=0, max=24,
    )
    character_pop: BoolProperty(
        name="逐字弹入",
        description="字符依次从轻微下沉与缩小状态弹入",
        default=True,
    )
    spatial_depth: FloatProperty(
        name="空间入场深度",
        description="逐字入场时沿镜头深度方向的偏移量",
        default=0.08, min=0.0, max=2.0, precision=3,
    )
    glitch_enabled: BoolProperty(
        name="故障闪切",
        description="在每句歌词入场瞬间叠加短暂的彩色错位闪切",
        default=False,
    )
    glitch_strength: FloatProperty(
        name="故障错位幅度",
        description="控制彩色错位文字的偏移距离",
        default=0.012, min=0.001, max=0.08, precision=3,
    )
    glow_strength: FloatProperty(
        name="文字柔光强度",
        description="仅控制插件生成的歌词材质发光，不修改场景合成器",
        default=0.35, min=0.0, max=8.0, precision=2,
    )
    text_extrude: FloatProperty(
        name="文字立体厚度",
        description="给文字增加轻微的 3D 厚度",
        default=0.0, min=0.0, max=0.15, precision=3,
    )
    text_bevel: FloatProperty(
        name="文字边缘柔化",
        description="文字轮廓边缘的轻微倒角",
        default=0.0, min=0.0, max=0.05, precision=3,
    )
    layout_alignment: EnumProperty(
        name="排版对齐",
        items=[("CENTER", "居中", "整句居中"), ("LEFT", "左对齐", "从左侧开始排版"), ("RIGHT", "右对齐", "从右侧开始排版")],
        default="CENTER",
    )
    display_x: FloatProperty(
        name="左右位置",
        description="歌词在画面中的水平位置；0 为居中，负数向左，正数向右",
        default=0.0,
        min=-0.9,
        max=0.9,
        precision=3,
        update=update_lyric_positions,
    )
    display_y: FloatProperty(
        name="上下位置",
        description="歌词在画面中的垂直位置；0 为居中，负数向下，正数向上",
        default=-0.48,
        min=-0.9,
        max=0.9,
        precision=3,
        update=update_lyric_positions,
    )
    camera_distance: FloatProperty(
        name="与摄像机距离",
        description="歌词平面与摄像机之间的距离",
        default=2.0,
        min=0.1,
        max=100.0,
        precision=2,
        update=update_lyric_positions,
    )
    slide_frames: IntProperty(
        name="入场移动帧数",
        description="实时控制歌词从镜头外进入画面的速度；数值越小越快",
        default=14,
        min=1,
        max=240,
        update=update_lyric_entrance_settings,
    )
    entrance_distance: FloatProperty(
        name="镜头外起点距离",
        description="控制歌词从画面外多远的位置开始进入；可实时调整",
        default=1.15,
        min=1.0,
        max=3.0,
        precision=2,
        update=update_lyric_entrance_settings,
    )
    fade_frames: IntProperty(
        name="淡入淡出帧数",
        description="每句歌词淡入和淡出的动画帧数",
        default=8,
        min=0,
        max=120,
    )
    hold_gap: FloatProperty(
        name="最后一句持续时间",
        description="最后一句歌词没有下一条时间戳时的显示时长",
        default=3.0,
        min=0.1,
        max=30.0,
    )
    time_offset: FloatProperty(
        name="手动时间偏移",
        description="整体调整歌词时间，单位为秒",
        default=0.0,
        min=-3600.0,
        max=3600.0,
        precision=3,
    )
    text_color: FloatVectorProperty(
        name="字幕颜色",
        subtype="COLOR",
        size=4,
        min=0.0,
        max=1.0,
        default=(1.0, 1.0, 1.0, 1.0),
    )
    random_seed: IntProperty(name="随机种子", description="相同种子和歌词会生成相同排版", default=20261103, min=0, max=2147483647)
    random_amount: IntProperty(name="随机幅度", default=60, min=0, max=100,
        description="0 为完全稳定可复现，100 为最大随机偏移")
    random_layout_enabled: BoolProperty(name="启用随机排版", default=True)
    layout_mode: EnumProperty(
        name="排版模式",
        items=[("RANDOM", "逐句随机", "每句独立随机"), ("PER_SECTION", "按段落", "按时间间隔分段，段内统一"), ("FIXED", "固定", "全部使用指定对齐")],
        default="RANDOM",
    )
    chorus_y_offset: FloatProperty(name="副歌上移量", default=0.0, min=-0.5, max=0.5, precision=3)
    position_cycle: IntProperty(name="每 N 句换位", default=0, min=0, max=64,
        description="0 为不换位；大于 0 时每 N 句在上下位置间交替")
    layout_line_index: IntProperty(name="目标歌词序号", description="从 1 开始；用于单句重抽和锁定", default=1, min=1)
    layout_pool: EnumProperty(
        name="随机样式范围",
        items=[("ALL", "全部 8 种", "从全部排版样式中随机"), ("SIMPLE", "基础 4 种", "从居中、左右、竖排中随机")],
        default="ALL",
    )
    animation_random_mode: EnumProperty(
        name="动画组合",
        description="控制自动随机动画的整体风格",
        items=[("MIXED", "混合随机", "从全部动画方案中随机组合"), ("GENTLE", "柔和随机", "偏向渐隐、漂浮和缓慢入场"), ("IMPACT", "强烈随机", "偏向弹跳、故障效果"), ("TEXT_FX", "文字特效优先", "偏向故障文字效果")],
        default="MIXED",
    )
    animation_intensity: IntProperty(name="动画强度", default=60, min=0, max=100, description="控制动画位移、旋转和弹性幅度")
    animation_random_enabled: BoolProperty(name="自动随机动画", default=True, description="每句歌词按随机种子选择入场与退场表现")
    generated_count: IntProperty(name="已生成歌词数", default=0)
    hide_lyrics_in_viewport: BoolProperty(
        name="在视口中隐藏字幕",
        description="仅在 3D 视口中隐藏生成的字幕，不影响最终渲染",
        default=False,
        update=update_lyric_viewport_visibility,
    )


class LYRICPV_OT_import_lrc(Operator):
    bl_idname = "lyric_pv.import_lrc"
    bl_label = "导入 LRC"
    bl_description = "单独导入普通 LRC 整句时间歌词"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.lyric_pv_props
        path = bpy.path.abspath(props.lrc_path)
        if not path or not path.lower().endswith(".lrc"):
            self.report({"ERROR"}, "请选择 .lrc 文件。")
            return {"CANCELLED"}
        try:
            content = read_lyric_file(path)
            entries, offset_ms = parse_lrc_text(content)
        except Exception as exc:
            self.report({"ERROR"}, f"无法读取 LRC 文件：{exc}")
            return {"CANCELLED"}
        if not entries:
            self.report({"ERROR"}, "没有找到带时间戳的 LRC 歌词。")
            return {"CANCELLED"}
        scene = context.scene
        scene["lyric_pv_entries"] = json.dumps([[float(t), lyric] for t, lyric in entries], ensure_ascii=False)
        scene["lyric_pv_yrc_entries"] = "[]"
        scene["lyric_pv_source"] = path
        scene["lyric_pv_source_format"] = "LRC"
        scene["lyric_pv_file_offset_ms"] = int(offset_ms)
        props.generated_count = len(entries)
        self.report({"INFO"}, f"已导入 {len(entries)} 句 LRC 歌词。")
        return {"FINISHED"}


class LYRICPV_OT_import_yrc(Operator):
    bl_idname = "lyric_pv.import_yrc"
    bl_label = "导入 YRC"
    bl_description = "导入 YRC 歌词并保留逐字时间信息"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.lyric_pv_props
        path = bpy.path.abspath(props.yrc_path)
        if not path or not path.lower().endswith(".yrc"):
            self.report({"ERROR"}, "请选择 .yrc 文件。")
            return {"CANCELLED"}
        try:
            content = read_lyric_file(path)
            entries, timed_entries = parse_yrc_text(content)
        except Exception as exc:
            self.report({"ERROR"}, f"无法读取 YRC 文件：{exc}")
            return {"CANCELLED"}
        if not entries:
            self.report({"ERROR"}, "没有识别到此格式的 YRC 歌词。")
            return {"CANCELLED"}
        scene = context.scene
        scene["lyric_pv_entries"] = json.dumps([[float(t), lyric] for t, lyric in entries], ensure_ascii=False)
        scene["lyric_pv_yrc_entries"] = json.dumps(timed_entries, ensure_ascii=False)
        scene["lyric_pv_source"] = path
        scene["lyric_pv_source_format"] = "YRC"
        scene["lyric_pv_file_offset_ms"] = 0
        props.generated_count = len(entries)
        token_count = sum(len(item["tokens"]) for item in timed_entries)
        self.report({"INFO"}, f"已导入 {len(entries)} 句 YRC 歌词，保留 {token_count} 段逐字时间。")
        return {"FINISHED"}


def fit_lyric_object_to_camera(obj, frame_width, frame_height, safe_width=0.84, safe_height=0.76, max_animation_scale=1.22):
    bpy.context.view_layer.update()
    dims = obj.dimensions
    width = max(float(dims.x), 1e-6)
    height = max(float(dims.y), 1e-6)
    anim_guard = max(1.0, float(max_animation_scale))
    limit_w = max(1e-5, float(frame_width) * safe_width / anim_guard)
    limit_h = max(1e-5, float(frame_height) * safe_height / anim_guard)
    factor = min(1.0, limit_w / width, limit_h / height)
    if factor < 1.0:
        obj.scale = obj.scale * factor
        bpy.context.view_layer.update()
    half_w = max(0.0, float(frame_width) * 0.5 - float(obj.dimensions.x) * 0.5)
    half_h = max(0.0, float(frame_height) * 0.5 - float(obj.dimensions.y) * 0.5)
    loc = obj.location.copy()
    loc.x = max(-half_w, min(half_w, loc.x))
    loc.y = max(-half_h, min(half_h, loc.y))
    obj.location = loc
    return factor
class LYRICPV_OT_generate(Operator):
    bl_idname = "lyric_pv.generate"
    bl_label = "生成歌词 PV"
    bl_description = "生成逐字排版、弹入、淡入淡出与空间入场动画"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        props = scene.lyric_pv_props
        raw_entries = scene.get("lyric_pv_entries", "")
        if not raw_entries:
            self.report({"ERROR"}, "请先导入 LRC 歌词文件。")
            return {"CANCELLED"}
        try:
            decoded = json.loads(raw_entries) if isinstance(raw_entries, str) else raw_entries
            entries = [(float(item[0]), str(item[1])) for item in decoded]
        except (TypeError, ValueError, IndexError, json.JSONDecodeError) as exc:
            self.report({"ERROR"}, f"歌词数据无效，请重新导入 LRC：{exc}")
            return {"CANCELLED"}
        if not entries:
            self.report({"ERROR"}, "没有可用的歌词，请重新导入 LRC。")
            return {"CANCELLED"}
        camera = props.target_camera or scene.camera
        if camera is None or camera.type != "CAMERA" or camera.name not in scene.objects:
            self.report({"ERROR"}, "请选择当前场景中的有效摄像机。")
            return {"CANCELLED"}

        entries.sort(key=lambda item: item[0])
        source_format = str(scene.get("lyric_pv_source_format", "LRC")).upper()
        try:
            yrc_timed_entries = json.loads(scene.get("lyric_pv_yrc_entries", "[]")) if source_format == "YRC" else []
        except (TypeError, ValueError, json.JSONDecodeError):
            yrc_timed_entries = []
        # Match YRC records to sentence order; LRC keeps its original sentence timing.
        yrc_timing_by_text = {}
        if source_format == "YRC":
            for timed in yrc_timed_entries:
                if isinstance(timed, dict):
                    yrc_timing_by_text.setdefault(str(timed.get("text", "")), []).append(timed)
        layouts = load_layout_records(scene, entries, props)
        remove_generated_collection()
        remove_legacy_generated_background()
        collection = get_or_create_collection(scene)
        material = make_text_material("LPV_Text_Material", props.text_color, props.glow_strength)

        glitch_mats = {}
        if props.glitch_enabled:
            glitch_mats["C"] = make_text_material("LPV_Glitch_Mat_C", (0.1, 0.85, 1.0, 1.0), max(0.6, props.glow_strength))
            glitch_mats["M"] = make_text_material("LPV_Glitch_Mat_M", (1.0, 0.12, 0.48, 1.0), max(0.6, props.glow_strength))

        font = None
        if props.font_path:
            try:
                font = bpy.data.fonts.load(bpy.path.abspath(props.font_path), check_existing=True)
            except Exception as exc:
                self.report({"WARNING"}, f"字体加载失败，改用默认字体：{exc}")

        fps = scene.render.fps / scene.render.fps_base
        start_frame = scene.frame_start
        distance = get_occlusion_safe_distance(scene, camera, props)
        min_x, max_x, min_y, max_y = camera_frame_bounds(scene, camera, distance)
        frame_width, frame_height = max_x-min_x, max_y-min_y
        controller = bpy.data.objects.new("LPV_字幕位置控制器", None)
        collection.objects.link(controller)
        controller.empty_display_type = "PLAIN_AXES"
        controller.empty_display_size = 0.12
        controller.parent = camera
        controller.location = (min_x + frame_width*(props.display_x+0.5), min_y + frame_height*(props.display_y+0.5), -distance)
        controller.scale = (1.0, 1.0, 1.0)
        controller["lyric_base_distance"] = float(distance)
        controller[PV_TAG] = True
        controller["lyric_pv_controller"] = True
        controller.hide_render = True
        if props.hide_lyrics_in_viewport:
            controller.hide_set(True, view_layer=context.view_layer)

        created = 0
        for index, (seconds, lyric) in enumerate(entries):
            if not lyric.strip():
                continue
            record = layouts[str(index)]
            next_seconds = entries[index+1][0] if index+1 < len(entries) else seconds + props.hold_gap
            start_seconds = max(0.0, seconds + props.time_offset)
            end_seconds = max(start_seconds+0.05, next_seconds + props.time_offset)
            frame_in = start_frame + round(start_seconds*fps)
            frame_out = max(frame_in+1, start_frame + round(end_seconds*fps))
            fade = min(props.fade_frames, max(0, (frame_out-frame_in)//2))
            style = record["style"]
            center_aligned_styles = {"CLEAN_CENTER", "VERTICAL", "DIAGONAL", "WIDE_SPACING", "PER_CHARACTER", "EMPHASIS"}
            if props.layout_alignment == "CENTER" and style in center_aligned_styles:
                record = dict(record)
                record["x"] = 0.0
                record["rotation"] = 0.0
            # PV-style placement: each lyric line gets a deterministic, varied
            # camera-local position. Keep a generous safe margin; final text-fit
            # and character-occlusion checks below still clamp/nudge the result.
            # This applies identically to LRC and YRC because both use this generator.
            if props.random_layout_enabled:
                record = dict(record)
                pos_rng = random.Random(int(props.random_seed) + index * 104729 + 31)
                # Avoid repeatedly pinning every line to the exact screen centre.
                x_choices = (-0.34, -0.22, 0.22, 0.34)
                y_choices = (-0.27, -0.16, 0.16, 0.27)
                record["x"] = pos_rng.choice(x_choices) * frame_width
                record["y"] = pos_rng.choice(y_choices) * frame_height
                # Small per-line variation makes consecutive lines feel less templated.
                record["x"] += pos_rng.uniform(-0.035, 0.035) * frame_width
                record["y"] += pos_rng.uniform(-0.025, 0.025) * frame_height
            # 副歌/段落位置交替（可选）：position_cycle > 0 时每 N 句上下交替
            cycle = int(props.position_cycle)
            extra_y = 0.0
            if cycle > 0 and (index // cycle) % 2 == 1:
                extra_y += float(props.chorus_y_offset)
            multiplier = float(record["font_multiplier"])
            base_size = float(props.font_size) * multiplier
            effective_spacing = max(1.05, min(1.35, float(record.get("spacing", 1.0))))
            direction = "NONE" if record["animation"] == "FADE" else record["entrance"]
            reveal_enabled = bool(props.character_pop or record["animation"] in {"POP", "FADE"})
            pop_motion = bool(props.character_pop or record["animation"] == "POP")
            # LRC and YRC share the same layout/animation controls. YRC timing
            # only drives per-character reveal when the selected layout is per-character;
            # ordinary layouts keep the entire sentence in one FONT object.
            per_char = style in {"PER_CHARACTER", "EMPHASIS"}
            yrc_timing = None
            if source_format == "YRC":
                candidates = yrc_timing_by_text.get(lyric, [])
                if candidates:
                    yrc_timing = candidates.pop(0)
            yrc_char_frames = yrc_character_frame_map(yrc_timing, fps, start_frame, props.time_offset) if yrc_timing else []
            glyphs = []
            line_fit = 1.0
            if per_char:
                display_units = lyric_display_units(lyric)
                # Create all glyph objects first, then evaluate the view layer once.
                # The previous implementation forced a depsgraph/view-layer update
                # for every character, which became extremely expensive on long lyrics.
                for ci, (unit_text, source_char_index) in enumerate(display_units):
                    cu = bpy.data.curves.new(f"LPV_Lyric_{index+1:03d}_{ci+1:03d}_Curve", type="FONT")
                    cu.body = unit_text if unit_text.strip() else " "
                    cu.size = base_size
                    cu.align_x = "LEFT"
                    cu.align_y = "CENTER"
                    cu.extrude = props.text_extrude
                    cu.bevel_depth = props.text_bevel
                    cu.space_character = effective_spacing
                    if font: cu.font = font
                    ob = bpy.data.objects.new(f"LPV_Lyric_{index+1:03d}_Glyph_{ci+1:03d}", cu)
                    collection.objects.link(ob)
                    ob.parent = controller
                    ob.data.materials.append(material)
                    ob[PV_TAG] = True
                    glyphs.append((ob, 0.0, ci, 0.0))
                bpy.context.view_layer.update()
                cursor = 0.0
                measured_glyphs = []
                depsgraph = context.evaluated_depsgraph_get()
                for ob, _cursor_x, ci, _width in glyphs:
                    unit_text = display_units[ci][0]
                    # FONT dimensions can be stale/near-zero for newly linked glyphs,
                    # especially with CJK fallback fonts. Use evaluated bounds first,
                    # then a conservative typographic advance so glyphs never stack
                    # at the same cursor position.
                    try:
                        evaluated = ob.evaluated_get(depsgraph)
                        measured_width = float(evaluated.dimensions.x)
                    except Exception:
                        measured_width = 0.0
                    estimated_width = estimate_lyric_unit_advance(unit_text, base_size)
                    minimum_width = estimated_width * 0.72
                    width = measured_width if measured_width >= minimum_width else estimated_width
                    width = max(width, base_size * 0.18)
                    measured_glyphs.append((ob, cursor, ci, width, display_units[ci][1]))
                    # LRC uses sentence timestamps but may display the sentence as
                    # individual glyph objects. EMPHASIS enlarges the first glyph;
                    # include that visual width in the layout advance so later glyphs
                    # do not overlap it. Keep YRC's existing per-character layout/timing.
                    lrc_emphasis_scale = 1.35 if source_format == "LRC" and style == "EMPHASIS" and ci == 0 else 1.0
                    advance_width = width * lrc_emphasis_scale
                    gap = max(base_size * 0.075, advance_width * 0.10) * effective_spacing
                    # Spaces are real layout units: their measured advance already carries
                    # the separation, so never add an extra synthetic gap around them.
                    current_is_space = display_units[ci][0].isspace()
                    next_is_space = (ci + 1 < len(display_units) and display_units[ci + 1][0].isspace())
                    has_space = current_is_space or next_is_space
                    cursor += advance_width + (gap if ci < len(display_units) - 1 and not has_space else 0.0)
                glyphs = measured_glyphs
                total_width = cursor
                animation_peak = 1.18 if record.get("animation") in {"POP", "BOUNCE"} else 1.04 if record.get("animation") == "GLITCH" else 1.0
                emphasis_peak = 1.35 if style == "EMPHASIS" else 1.0
                peak_scale = animation_peak * emphasis_peak
                fit = min(1.0, (frame_width*0.84)/(max(total_width, 1e-6)*peak_scale), (frame_height*0.76)/(max(base_size, 1e-6)*peak_scale))
                line_fit = fit
                start_x = -total_width*fit*0.5
                for ob, cursor_x, ci, width, source_char_index in glyphs:
                    bx = start_x + cursor_x*fit
                    if style == "EMPHASIS" and ci == 0:
                        scale_factor = 1.35
                    else:
                        scale_factor = 1.0
                    ob.scale = (fit*scale_factor, fit*scale_factor, fit*scale_factor)
                    ob.location = (bx, 0.0, 0.0)
                    ob.rotation_euler.z = math.radians(float(record["rotation"]))
                    ob["lyric_font_multiplier"] = multiplier
                    ob["lyric_base_x"] = bx + float(record["x"])
                    ob["lyric_base_y"] = float(record["y"])
                    ob["lyric_base_z"] = 0.0
                    ob["lyric_index"] = index
                    ob["lyric_text"] = lyric
                    ob["lyric_entrance_enabled"] = True
                    ob["lyric_entrance_direction"] = direction
                    if yrc_char_frames and source_char_index < len(yrc_char_frames):
                        char_frame_in = max(frame_in, min(frame_out - 1, int(yrc_char_frames[source_char_index])))
                    else:
                        char_frame_in = int(frame_in + (ci*props.character_stagger if reveal_enabled else 0))
                    ob["lyric_frame_in"] = char_frame_in
                    ob["lyric_frame_out"] = int(frame_out)
                    ob["lyric_fade_frames"] = int(fade)
                    ob["lyric_pop_enabled"] = reveal_enabled
                    ob["lyric_pop_frames"] = max(2, fade)
                    ob["lyric_pop_y"] = -base_size*0.22 if pop_motion else 0.0
                    ob["lyric_pop_z"] = props.spatial_depth if pop_motion else 0.0
                    char_start = int(ob["lyric_frame_in"])
                    _key_object_scale(ob, char_start, frame_out, fade, reveal_enabled)
                    apply_text_animation(ob, record, char_start, frame_out, props, random.Random(int(props.random_seed) + index*997 + ci))
                    created += 1
                group_center_x = float(record["x"])
                max_center_x = max(0.0, frame_width * 0.5 - total_width * fit * 0.5 - frame_width * 0.06)
                group_center_x = max(-max_center_x, min(max_center_x, group_center_x))
                group_y = max(-frame_height * 0.18, min(frame_height * 0.18, float(record["y"]) + extra_y))
                group_center_x, group_y = nudge_lyric_away_from_character(
                    scene, camera, props,
                    min_x + frame_width*0.5 + group_center_x,
                    min_y + frame_height*0.5 + group_y,
                    total_width*fit, base_size*fit, distance,
                    (min_x, max_x, min_y, max_y))
                group_center_x -= min_x + frame_width*0.5
                group_y -= min_y + frame_height*0.5
                for ob, cursor_x, ci, width, source_char_index in glyphs:
                    ob.location.x = start_x + cursor_x * fit + group_center_x
                    ob.location.y = group_y
                    ob["lyric_base_x"] = float(ob.location.x)
                    ob["lyric_base_y"] = float(ob.location.y)
            else:
                cu = bpy.data.curves.new(f"LPV_Lyric_{index+1:03d}_Curve", type="FONT")
                cu.body = lyric
                cu.size = base_size
                cu.align_x = {"CLEAN_CENTER":"CENTER", "LEFT_TITLE":"LEFT", "RIGHT_TITLE":"RIGHT", "VERTICAL":"CENTER", "DIAGONAL":"CENTER", "WIDE_SPACING":"CENTER"}.get(style, props.layout_alignment)
                cu.align_y = "CENTER"
                cu.extrude = props.text_extrude
                cu.bevel_depth = props.text_bevel
                cu.space_character = effective_spacing
                if style == "VERTICAL": cu.body = "\n".join(list(lyric))
                if font: cu.font = font
                ob = bpy.data.objects.new(f"LPV_Lyric_{index+1:03d}_Line", cu)
                collection.objects.link(ob); ob.parent = controller; ob.data.materials.append(material)
                ob[PV_TAG] = True
                ob["lyric_index"] = index; ob["lyric_text"] = lyric
                ob["lyric_font_multiplier"] = multiplier
                ob["lyric_base_x"] = float(record["x"])
                ob["lyric_base_y"] = float(record["y"]) + extra_y
                ob["lyric_base_z"] = 0.0
                safe_x = max(-frame_width * 0.16, min(frame_width * 0.16, float(record["x"])))
                safe_y = max(-frame_height * 0.16, min(frame_height * 0.16, float(record["y"]) + extra_y))
                ob.location = (safe_x, safe_y, 0.0)
                ob.rotation_euler.z = math.radians(float(record["rotation"]))
                animation_peak = 1.18 if record.get("animation") in {"POP", "BOUNCE"} else 1.04 if record.get("animation") == "GLITCH" else 1.0
                line_fit = fit_lyric_object_to_camera(ob, frame_width, frame_height, max_animation_scale=animation_peak)
                abs_x, abs_y = nudge_lyric_away_from_character(
                    scene, camera, props,
                    min_x + frame_width*0.5 + float(ob.location.x),
                    min_y + frame_height*0.5 + float(ob.location.y),
                    max(float(ob.dimensions.x), base_size*0.12),
                    max(float(ob.dimensions.y), base_size*0.12),
                    distance, (min_x, max_x, min_y, max_y))
                ob.location.x = abs_x - (min_x + frame_width*0.5)
                ob.location.y = abs_y - (min_y + frame_height*0.5)
                ob["lyric_base_x"] = float(ob.location.x)
                ob["lyric_entrance_enabled"] = True
                ob["lyric_entrance_direction"] = direction
                ob["lyric_frame_in"] = int(frame_in)
                ob["lyric_frame_out"] = int(frame_out)
                ob["lyric_fade_frames"] = int(fade)
                ob["lyric_pop_enabled"] = reveal_enabled
                ob["lyric_pop_frames"] = max(2, fade)
                ob["lyric_pop_y"] = -base_size*0.22 if pop_motion else 0.0
                ob["lyric_pop_z"] = props.spatial_depth if pop_motion else 0.0
                _key_object_scale(ob, frame_in, frame_out, fade, reveal_enabled)
                line_rng = random.Random(int(props.random_seed) + index*997)
                apply_text_animation(ob, record, frame_in, frame_out, props, line_rng)
                created += 1
            if props.glitch_enabled:
                for suffix, color, sign in (("C", (0.1,0.85,1.0,1.0), -1.0), ("M", (1.0,0.12,0.48,1.0), 1.0)):
                    gc = bpy.data.curves.new(f"LPV_Glitch_{index+1:03d}_{suffix}_Curve", type="FONT")
                    gc.body=lyric; gc.size=base_size; gc.align_x="CENTER"; gc.align_y="CENTER"
                    if font: gc.font=font
                    go=bpy.data.objects.new(f"LPV_Glitch_{index+1:03d}_{suffix}",gc); collection.objects.link(go); go.parent=controller
                    go.data.materials.append(glitch_mats[suffix])
                    go.location=(float(record["x"])+sign*props.glitch_strength,float(record["y"])+extra_y,-0.002)
                    go.scale=(0.001,0.001,0.001); go[PV_TAG]=True; go["lyric_glitch_overlay"]=True
                    go.keyframe_insert(data_path="scale",frame=max(frame_in-1,scene.frame_start))
                    go.scale=(line_fit,line_fit,line_fit); go.keyframe_insert(data_path="scale",frame=frame_in)
                    go.keyframe_insert(data_path="scale",frame=min(frame_in+2,frame_out))
                    go.scale=(0.001,0.001,0.001); go.keyframe_insert(data_path="scale",frame=min(frame_in+3,frame_out))
                    created += 1
        scene["lyric_pv_layouts"] = json.dumps(layouts, ensure_ascii=False, sort_keys=True)
        props.generated_count = len(entries)
        invalidate_entrance_cache()
        update_lyric_entrance_positions(scene)
        self.report({"INFO"}, f"已生成 {len(entries)} 句歌词（{created} 个文字对象），集合：{PV_ROOT_NAME}。")
        return {"FINISHED"}


class LYRICPV_OT_reroll_all(Operator):
    bl_idname = "lyric_pv.reroll_all"
    bl_label = "重抽未锁定歌词排版"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        scene=context.scene; props=scene.lyric_pv_props
        if not scene.get("lyric_pv_entries"):
            self.report({"WARNING"}, "请先导入歌词并生成一次排版。"); return {"CANCELLED"}
        reroll_layout_records(scene, props)
        bpy.ops.lyric_pv.generate()
        return {"FINISHED"}


class LYRICPV_OT_reroll_one(Operator):
    bl_idname = "lyric_pv.reroll_one"
    bl_label = "重抽指定句"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        scene=context.scene; props=scene.lyric_pv_props; idx=int(props.layout_line_index)-1
        try: records=json.loads(scene.get("lyric_pv_layouts", "{}"))
        except Exception: records={}
        if str(idx) not in records:
            self.report({"WARNING"}, "该句尚无排版记录，请先生成一次。"); return {"CANCELLED"}
        if records[str(idx)].get("locked", False):
            self.report({"WARNING"}, "该句已锁定，请先解锁。"); return {"CANCELLED"}
        reroll_layout_records(scene, props, [idx])
        bpy.ops.lyric_pv.generate()
        return {"FINISHED"}


class LYRICPV_OT_toggle_lock(Operator):
    bl_idname = "lyric_pv.toggle_lock"
    bl_label = "锁定/解锁指定句"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        scene=context.scene; idx=int(scene.lyric_pv_props.layout_line_index)-1
        try: records=json.loads(scene.get("lyric_pv_layouts", "{}"))
        except Exception: records={}
        rec=records.get(str(idx))
        if rec is None:
            self.report({"WARNING"}, "该句尚无排版记录，请先生成一次。"); return {"CANCELLED"}
        rec["locked"] = not bool(rec.get("locked", False))
        scene["lyric_pv_layouts"] = json.dumps(records, ensure_ascii=False, sort_keys=True)
        self.report({"INFO"}, "已锁定该句。" if rec["locked"] else "已解锁该句。")
        return {"FINISHED"}


class LYRICPV_OT_clear(Operator):
    bl_idname = "lyric_pv.clear"
    bl_label = "清除已生成内容"
    bl_description = "仅删除 LYRIC PV STUDIO 创建的对象和数据"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        props = scene.lyric_pv_props

        # Remove generated scene objects and legacy generated background.
        removed = remove_generated_collection()
        legacy_background_removed = remove_legacy_generated_background()

        # Clear imported lyric payload and all per-import layout/source metadata.
        # This makes the next LRC/YRC import a completely fresh project.
        lyric_keys = (
            "lyric_pv_entries",
            "lyric_pv_yrc_entries",
            "lyric_pv_source",
            "lyric_pv_source_format",
            "lyric_pv_file_offset_ms",
            "lyric_pv_layouts",
            "lyric_pv_reroll",
        )
        cleared = 0
        for key in lyric_keys:
            if key in scene:
                del scene[key]
                cleared += 1

        # Reset file selectors and visible counters as well.
        props.lrc_path = ""
        props.yrc_path = ""
        props.generated_count = 0

        # Drop cached object references so a later generation cannot reuse stale data.
        _ENTRANCE_CACHE.clear()
        if removed or legacy_background_removed or cleared:
            self.report({"INFO"}, "已彻底清理：生成内容、LRC/YRC 歌词、逐字时间、排版记录和导入路径。")
        else:
            self.report({"INFO"}, "歌词项目已经是空的，无需清理。")
        return {"FINISHED"}


class LYRICPV_PT_main(Panel):
    bl_label = "LYRIC PV STUDIO"
    bl_idname = "LYRICPV_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "歌词PV"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = scene.lyric_pv_props

        layout.label(text="歌词项目")
        lrc_box = layout.box()
        lrc_box.label(text="普通歌词（整句时间）")
        lrc_box.prop(props, "lrc_path", text="LRC 文件")
        lrc_box.operator("lyric_pv.import_lrc", text="导入 LRC", icon="FILE_TEXT")
        yrc_box = layout.box()
        yrc_box.label(text="逐字歌词（保留字级时间）")
        yrc_box.prop(props, "yrc_path", text="YRC 文件")
        yrc_box.operator("lyric_pv.import_yrc", text="导入 YRC", icon="FILE_TEXT")

        stored_entries = scene.get("lyric_pv_entries", "")
        try:
            loaded_count = len(json.loads(stored_entries)) if stored_entries else 0
        except (TypeError, ValueError, json.JSONDecodeError):
            loaded_count = 0

        if loaded_count:
            layout.label(text=f"已导入歌词：{loaded_count} 句")
        else:
            layout.label(text="尚未导入歌词")

        layout.separator()
        layout.label(text="场景识别")
        layout.prop(props, "target_camera")
        if props.target_camera is None and scene.camera:
            layout.label(text=f"当前使用场景摄像机：{scene.camera.name}")
        layout.prop(props, "occlusion_target")
        layout.prop(props, "keep_behind_target", toggle=True)
        if props.keep_behind_target and props.occlusion_target:
            layout.prop(props, "occlusion_margin")

        layout.separator()
        layout.label(text="字幕外观与位置")
        layout.prop(props, "font_path")
        layout.prop(props, "font_size")
        layout.separator()
        layout.label(text="随机歌词排版")
        layout.prop(props, "random_layout_enabled")
        if props.random_layout_enabled:
            layout.prop(props, "random_seed")
            layout.prop(props, "random_amount", slider=True)
            layout.prop(props, "layout_mode")
            layout.prop(props, "layout_pool")
            layout.prop(props, "layout_line_index")
            layout.prop(props, "animation_random_enabled")
            layout.prop(props, "animation_random_mode")
            layout.prop(props, "animation_intensity")
            row = layout.row(align=True)
            row.operator("lyric_pv.reroll_all", text="重抽未锁定")
            row.operator("lyric_pv.reroll_one", text="只重抽此句")
            layout.operator("lyric_pv.toggle_lock", text="锁定/解锁此句")
        layout.prop(props, "layout_alignment", expand=True)
        layout.prop(props, "text_extrude")
        layout.prop(props, "text_bevel")
        layout.prop(props, "glow_strength")
        layout.prop(props, "display_x", slider=True)
        layout.prop(props, "display_y", slider=True)
        layout.prop(props, "position_cycle")
        if props.position_cycle > 0:
            layout.prop(props, "chorus_y_offset")
        layout.prop(props, "text_color")

        layout.separator()
        layout.label(text="时间与动画")
        layout.prop(props, "camera_distance")
        layout.label(text="自动随机镜头外入场")
        layout.prop(props, "slide_frames", slider=True)
        layout.prop(props, "entrance_distance", slider=True)
        layout.prop(props, "fade_frames")
        layout.prop(props, "character_pop")
        if props.character_pop:
            layout.prop(props, "character_stagger")
            layout.prop(props, "spatial_depth")
        layout.prop(props, "glitch_enabled")
        if props.glitch_enabled:
            layout.prop(props, "glitch_strength")
        layout.prop(props, "hold_gap")
        layout.prop(props, "time_offset")

        layout.separator()
        layout.label(text="视口显示")
        layout.prop(props, "hide_lyrics_in_viewport", toggle=True)
        layout.separator()
        layout.operator("lyric_pv.generate", text="生成歌词排版与动画", icon="FONT_DATA")
        layout.operator("lyric_pv.clear", text="彻底清理歌词项目", icon="TRASH")
        layout.label(text=f"已生成字幕：{props.generated_count} 条")


CLASSES = (
    LYRICPV_Properties,
    LYRICPV_OT_import_lrc,
    LYRICPV_OT_import_yrc,
    LYRICPV_OT_generate,
    LYRICPV_OT_reroll_all,
    LYRICPV_OT_reroll_one,
    LYRICPV_OT_toggle_lock,
    LYRICPV_OT_clear,
    LYRICPV_PT_main,
)


def register():
    """Register the add-on safely, including repeated enable/reload attempts."""
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
        if getattr(handler, "__name__", "") == "lyric_pv_frame_change_handler" and handler is not lyric_pv_frame_change_handler:
            handlers.remove(handler)
    if lyric_pv_frame_change_handler not in handlers:
        handlers.append(lyric_pv_frame_change_handler)


def unregister():
    """Unregister in reverse dependency order; tolerate partial registration."""
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