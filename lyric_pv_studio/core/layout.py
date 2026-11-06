"""Layout planning, section splitting, and randomization logic."""

import json
import random

from ..constants import (
    ANIMATION_SCHEMES,
    ENTRANCE_DIRECTIONS,
    LAYOUT_STYLES,
)


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
    amount = get_random_amount(props)
    pools = {
        "GENTLE": (("FADE", "SLIDE", "FLOAT", "ROTATE"), (1.35, 1.25, 0.8, 0.65)),
        "IMPACT": (("POP", "BOUNCE", "GLITCH", "SLIDE"), (1.15, 0.9, 0.45, 1.3)),
        "TEXT_FX": (("GLITCH",), (1.0,)),
        "MIXED": (ANIMATION_SCHEMES, (1.35, 0.9, 1.15, 0.75, 0.45, 0.65, 0.85)),
    }
    pool, weights = pools.get(mode, pools["MIXED"])
    return _weighted_choice(rng, pool, weights, amount)


def get_random_amount(props):
    """0 = 完全稳定，100 = 最大随机偏移。"""
    return 1.0 if props is None else max(0.0, min(1.0, props.random_amount / 100.0))


# 向下兼容历史别名
_random_amount = get_random_amount


def _new_layout_record(rng, props=None):
    amount = get_random_amount(props)
    animation = _choose_animation(rng, props) if props and props.animation_random_enabled else "SLIDE"
    style_pool = (
        "CLEAN_CENTER",
        "LEFT_TITLE",
        "RIGHT_TITLE",
        "WIDE_SPACING",
        "VERTICAL",
        "DIAGONAL",
        "EMPHASIS",
        "PER_CHARACTER",
    )
    style_weights = (1.45, 1.2, 1.2, 0.9, 0.55, 0.55, 0.5, 0.28)
    style = _weighted_choice(rng, style_pool, style_weights, amount)
    return {
        "style": style,
        "font_multiplier": round(1.0 + rng.uniform(-0.18, 0.22) * amount, 3),
        "x": round(rng.uniform(-0.14, 0.14) * amount, 4),
        "y": round(rng.uniform(-0.08, 0.08) * amount, 4),
        "rotation": round(rng.uniform(-10.0, 10.0) * amount, 2),
        "spacing": round(1.0 + rng.uniform(-0.10, 0.15) * amount, 3),
        "animation": animation,
        "entrance": _weighted_choice(rng, ENTRANCE_DIRECTIONS, (1.15, 1.15, 0.85, 0.85), amount),
        "locked": False,
    }


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
        if isinstance(record, dict) and all(
            k in record for k in ("style", "font_multiplier", "x", "y", "rotation", "spacing", "animation", "entrance")
        ):
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
                record.update({
                    "style": "CLEAN_CENTER",
                    "font_multiplier": 1.0,
                    "x": 0.0,
                    "y": 0.0,
                    "rotation": 0.0,
                    "spacing": 1.0,
                    "animation": "SLIDE",
                    "entrance": "LEFT",
                })
            else:
                record = _new_layout_record(rng, props)
            if not props.random_layout_enabled:
                record.update({
                    "style": "CLEAN_CENTER",
                    "font_multiplier": 1.0,
                    "x": 0.0,
                    "y": 0.0,
                    "rotation": 0.0,
                    "spacing": 1.0,
                    "animation": "SLIDE",
                    "entrance": "LEFT",
                })
            elif props.layout_pool != "ALL":
                record["style"] = _weighted_choice(
                    rng, styles, (1.45, 1.2, 1.2, 0.9), get_random_amount(props)
                )
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
            new.update({
                "style": "CLEAN_CENTER",
                "font_multiplier": 1.0,
                "x": 0.0,
                "y": 0.0,
                "rotation": 0.0,
                "spacing": 1.0,
                "animation": "SLIDE",
                "entrance": "LEFT",
            })
        elif props.layout_pool != "ALL":
            new["style"] = _weighted_choice(
                rng, LAYOUT_STYLES[:4], (1.45, 1.2, 1.2, 0.9), get_random_amount(props)
            )
        records[key] = new
    scene["lyric_pv_reroll"] = int(scene.get("lyric_pv_reroll", 0)) + 1
    scene["lyric_pv_layouts"] = json.dumps(records, ensure_ascii=False, sort_keys=True)
    return records
