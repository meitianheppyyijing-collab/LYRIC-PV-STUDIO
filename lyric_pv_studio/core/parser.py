"""Lyric and subtitle text parsing and typography unit calculation."""

import html
import os
import re

_SRT_NAMED_COLORS = {
    "white": "#FFFFFF",
    "black": "#000000",
    "red": "#FF0000",
    "green": "#00FF00",
    "blue": "#0000FF",
    "yellow": "#FFFF00",
    "cyan": "#00FFFF",
    "aqua": "#00FFFF",
    "magenta": "#FF00FF",
    "fuchsia": "#FF00FF",
    "orange": "#FFA500",
    "pink": "#FFC0CB",
    "gray": "#808080",
    "grey": "#808080",
}

_SRT_TIMESTAMP_RE = re.compile(
    r"^\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*"
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})(?:\s+.*)?$"
)
_SRT_HTML_BR_RE = re.compile(r"<br\s*/?>", re.I)
_SRT_HTML_TAG_RE = re.compile(r"</?(?:i|b|u|s|em|strong|font|span|div|p|ruby|rt|rp)\b[^>]*>", re.I)
_SRT_FONT_COLOR_RE = re.compile(r"<font\b[^>]*\bcolor\s*=\s*['\"]?([^'\"\s>]+)['\"]?", re.I)
_SRT_ASS_BLOCK_RE = re.compile(r"\{\\[^}]*\}")
_SRT_ASS_AN_RE = re.compile(r"\\an([1-9])")
_SRT_ASS_A_RE = re.compile(r"\\a(10|11|[1-9])(?!\d)")
_SRT_ASS_COLOR_RE = re.compile(r"\\(?:1?c)&H([0-9A-Fa-f]{6})&")
_SRT_ASS_BOLD_RE = re.compile(r"\\b(\d+)")
_SRT_ASS_ITALIC_RE = re.compile(r"\\i([01])")
_SRT_ASS_UNDERLINE_RE = re.compile(r"\\u([01])")


def detect_lyric_format(path):
    """Detect supported lyric/subtitle format from file extension."""
    ext = os.path.splitext(str(path or ""))[1].lower()
    return {
        ".lrc": "LRC",
        ".yrc": "YRC",
        ".srt": "SRT",
    }.get(ext)


def read_lyric_file(path):
    """Read a lyric file with fallback encoding support (utf-8-sig / gb18030)."""
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            return handle.read()
    except UnicodeDecodeError:
        with open(path, "r", encoding="gb18030") as handle:
            return handle.read()


def parse_lrc_text(text):
    """Parse standard LRC lyric text into timestamped entries.

    Returns:
        (entries, offset_ms): entries is a list of (seconds, lyric) tuples.
    """
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
        if not line or (line.startswith("[") and not header_re.match(line)):
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


def _srt_time_to_ms(hours, minutes, seconds, fraction):
    frac = str(fraction or "0")
    if len(frac) == 1:
        ms = int(frac) * 100
    elif len(frac) == 2:
        ms = int(frac) * 10
    else:
        ms = int(frac[:3])
    return ((int(hours) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + ms


def _normalize_srt_color(raw_color):
    value = str(raw_color or "").strip().lower()
    if not value:
        return None
    if value in _SRT_NAMED_COLORS:
        return _SRT_NAMED_COLORS[value]
    if value.startswith("#"):
        value = value[1:]
    if len(value) == 3 and all(ch in "0123456789abcdef" for ch in value):
        value = "".join(ch * 2 for ch in value)
    if len(value) == 6 and all(ch in "0123456789abcdef" for ch in value):
        return f"#{value.upper()}"
    return None


def _parse_srt_formatting(raw_text):
    """Extract SRT/ASS inline formatting metadata and return cleaned display text."""
    align = None
    valign = None
    bold = False
    italic = False
    underline = False
    color = None

    for block in _SRT_ASS_BLOCK_RE.findall(raw_text):
        an_match = _SRT_ASS_AN_RE.search(block)
        if an_match:
            code = int(an_match.group(1))
            align = ("LEFT", "CENTER", "RIGHT")[(code - 1) % 3]
            valign = ("BOTTOM", "MIDDLE", "TOP")[(code - 1) // 3]
        else:
            a_match = _SRT_ASS_A_RE.search(block)
            if a_match:
                code = int(a_match.group(1))
                align = {
                    1: "LEFT", 5: "LEFT", 9: "LEFT",
                    2: "CENTER", 6: "CENTER", 10: "CENTER",
                    3: "RIGHT", 7: "RIGHT", 11: "RIGHT",
                }.get(code, align)
                valign = {
                    1: "BOTTOM", 2: "BOTTOM", 3: "BOTTOM",
                    5: "TOP", 6: "TOP", 7: "TOP",
                    9: "MIDDLE", 10: "MIDDLE", 11: "MIDDLE",
                }.get(code, valign)
        color_match = _SRT_ASS_COLOR_RE.search(block)
        if color_match:
            bgr = color_match.group(1)
            color = f"#{bgr[4:6]}{bgr[2:4]}{bgr[0:2]}".upper()
        bold_match = _SRT_ASS_BOLD_RE.search(block)
        if bold_match and int(bold_match.group(1)) > 0:
            bold = True
        italic_match = _SRT_ASS_ITALIC_RE.search(block)
        if italic_match and italic_match.group(1) == "1":
            italic = True
        underline_match = _SRT_ASS_UNDERLINE_RE.search(block)
        if underline_match and underline_match.group(1) == "1":
            underline = True

    if re.search(r"<(?:b|strong)\b[^>]*>", raw_text, re.I):
        bold = True
    if re.search(r"<(?:i|em)\b[^>]*>", raw_text, re.I):
        italic = True
    if re.search(r"<u\b[^>]*>", raw_text, re.I):
        underline = True
    font_color_match = _SRT_FONT_COLOR_RE.search(raw_text)
    if font_color_match and color is None:
        color = _normalize_srt_color(font_color_match.group(1))

    cleaned = _SRT_HTML_BR_RE.sub("\n", raw_text)
    cleaned = cleaned.replace("\\N", "\n")
    cleaned = _SRT_ASS_BLOCK_RE.sub("", cleaned)
    cleaned = _SRT_HTML_TAG_RE.sub("", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned_lines = [line.strip() for line in cleaned.splitlines()]
    cleaned_lines = [line for line in cleaned_lines if line]
    text = "\n".join(cleaned_lines)

    return text, {
        "align": align,
        "valign": valign,
        "bold": bold,
        "italic": italic,
        "underline": underline,
        "color": color,
    }


def parse_srt_text(text):
    """Parse SubRip (.srt) subtitle text into timed cue dicts.

    Preserves explicit multi-line formatting and inline SRT/ASS styling
    metadata, and merges simultaneous cues (same start_ms without conflicting
    explicit placement) with line breaks.
    """
    raw_lines = text.replace("\ufeff", "").splitlines()
    cues = []
    i = 0
    total_lines = len(raw_lines)
    while i < total_lines:
        match = _SRT_TIMESTAMP_RE.match(raw_lines[i])
        if not match:
            i += 1
            continue
        start_ms = _srt_time_to_ms(*match.group(1, 2, 3, 4))
        end_ms = max(start_ms, _srt_time_to_ms(*match.group(5, 6, 7, 8)))
        i += 1
        payload = []
        while i < total_lines:
            current = raw_lines[i]
            if not current.strip():
                i += 1
                break
            if _SRT_TIMESTAMP_RE.match(current):
                break
            if (
                current.strip().isdigit()
                and i + 1 < total_lines
                and _SRT_TIMESTAMP_RE.match(raw_lines[i + 1])
            ):
                i += 1
                break
            payload.append(current)
            i += 1
        cleaned_text, fmt = _parse_srt_formatting("\n".join(payload))
        if not cleaned_text:
            continue
        cues.append(
            {
                "start_ms": start_ms,
                "end_ms": end_ms,
                "duration_ms": max(0, end_ms - start_ms),
                "text": cleaned_text,
                **fmt,
            }
        )

    cues.sort(key=lambda item: item["start_ms"])

    merged = []
    for cue in cues:
        if (
            merged
            and merged[-1]["start_ms"] == cue["start_ms"]
            and merged[-1]["align"] == cue["align"]
            and merged[-1]["valign"] == cue["valign"]
        ):
            prev = merged[-1]
            prev["text"] = f"{prev['text']}\n{cue['text']}"
            prev["end_ms"] = max(prev["end_ms"], cue["end_ms"])
            prev["duration_ms"] = max(0, prev["end_ms"] - prev["start_ms"])
            prev["bold"] = prev["bold"] or cue["bold"]
            prev["italic"] = prev["italic"] or cue["italic"]
            prev["underline"] = prev["underline"] or cue["underline"]
            if prev["color"] is None:
                prev["color"] = cue["color"]
        else:
            merged.append(cue)

    return merged


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
        token_start = float(token.get("start_ms", 0)) + offset_ms
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
    """Group Latin words while preserving newlines, spaces, and CJK per-character units."""
    units = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\n":
            units.append(("\n", i))
            i += 1
            continue
        if ch.isspace():
            j = i + 1
            while j < len(text) and text[j].isspace() and text[j] != "\n":
                j += 1
            units.append((text[i:j], i))
            i = j
            continue
        # Apostrophes at the start of a contraction fragment (e.g. 'n')
        # belong to the following Latin letters; internal apostrophes stay joined.
        if ch.isascii() and (
                ch.isalnum() or (ch in "'’" and i + 1 < len(text) and text[i + 1].isascii() and text[i + 1].isalnum())):
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
