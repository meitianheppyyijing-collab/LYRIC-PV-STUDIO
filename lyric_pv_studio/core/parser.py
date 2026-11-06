"""Lyric text parsing and typography unit calculation."""

import re


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
