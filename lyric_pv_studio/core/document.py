"""Unified lyric document model, derived frame cache, and scene store."""

from dataclasses import dataclass, field
import json
import uuid

from .parser import lyric_display_units

DOC_SCHEMA_VERSION = 1
SCENE_DOC_KEY = "lyric_pv_document"
SCENE_DOC_REV_KEY = "lyric_pv_doc_rev"
LEGACY_SCENE_KEYS = (
    "lyric_pv_entries",
    "lyric_pv_yrc_entries",
    "lyric_pv_source",
    "lyric_pv_source_format",
    "lyric_pv_file_offset_ms",
)

_DOC_CACHE = {}


def _new_revision():
    return uuid.uuid4().hex[:12]


def _scene_cache_key(scene):
    as_pointer = getattr(scene, "as_pointer", None)
    if callable(as_pointer):
        try:
            return int(as_pointer())
        except (TypeError, ValueError):
            pass
    return id(scene)


@dataclass(frozen=True)
class LyricUnit:
    """One display unit (CJK character, Latin word, punctuation, or space)."""

    text: str
    char_index: int
    is_space: bool
    start_ms: int | None = None
    duration_ms: int | None = None

    @property
    def is_timed(self):
        return self.start_ms is not None and self.duration_ms is not None

    @property
    def end_ms(self):
        if not self.is_timed:
            return None
        return self.start_ms + max(0, self.duration_ms)

    def to_dict(self):
        data = {
            "text": self.text,
            "char_index": int(self.char_index),
            "is_space": bool(self.is_space),
        }
        if self.is_timed:
            data["start_ms"] = int(self.start_ms)
            data["duration_ms"] = int(self.duration_ms)
        return data

    @classmethod
    def from_dict(cls, data):
        text = str(data.get("text", ""))
        start_raw = data.get("start_ms")
        dur_raw = data.get("duration_ms")
        start_ms = int(start_raw) if start_raw is not None else None
        duration_ms = max(0, int(dur_raw)) if dur_raw is not None else None
        return cls(
            text=text,
            char_index=int(data.get("char_index", 0)),
            is_space=bool(data.get("is_space", text.isspace())),
            start_ms=start_ms,
            duration_ms=duration_ms,
        )


@dataclass(frozen=True)
class LyricLine:
    """One timestamped lyric or subtitle line with pre-split display units."""

    index: int
    text: str
    start_ms: int
    duration_ms: int | None = None
    units: tuple[LyricUnit, ...] = ()
    align: str | None = None
    valign: str | None = None
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: str | None = None

    @property
    def start_seconds(self):
        return self.start_ms / 1000.0

    @property
    def end_ms(self):
        if self.duration_ms is None:
            return None
        return self.start_ms + max(0, self.duration_ms)

    @property
    def has_word_timing(self):
        return any(unit.is_timed for unit in self.units)

    @property
    def has_explicit_placement(self):
        return self.align is not None or self.valign is not None

    def to_dict(self):
        data = {
            "index": int(self.index),
            "text": self.text,
            "start_ms": int(self.start_ms),
            "units": [unit.to_dict() for unit in self.units],
        }
        if self.duration_ms is not None:
            data["duration_ms"] = int(self.duration_ms)
        if self.align:
            data["align"] = self.align
        if self.valign:
            data["valign"] = self.valign
        if self.bold:
            data["bold"] = True
        if self.italic:
            data["italic"] = True
        if self.underline:
            data["underline"] = True
        if self.color:
            data["color"] = self.color
        return data

    @classmethod
    def from_dict(cls, data, fallback_index=0):
        text = str(data.get("text", ""))
        dur_raw = data.get("duration_ms")
        duration_ms = max(0, int(dur_raw)) if dur_raw is not None else None
        raw_units = data.get("units")
        if isinstance(raw_units, list) and raw_units:
            units = tuple(LyricUnit.from_dict(item) for item in raw_units if isinstance(item, dict))
        else:
            units = _build_plain_units(text)
        align = str(data["align"]).upper() if data.get("align") else None
        valign = str(data["valign"]).upper() if data.get("valign") else None
        color = str(data["color"]) if data.get("color") else None
        return cls(
            index=int(data.get("index", fallback_index)),
            text=text,
            start_ms=max(0, int(data.get("start_ms", 0))),
            duration_ms=duration_ms,
            units=units,
            align=align,
            valign=valign,
            bold=bool(data.get("bold", False)),
            italic=bool(data.get("italic", False)),
            underline=bool(data.get("underline", False)),
            color=color,
        )


@dataclass(frozen=True)
class UnitFrameTiming:
    """Resolved timeline frames for one LyricUnit."""

    frame_in: int
    frame_out: int

    @property
    def duration_frames(self):
        return max(1, self.frame_out - self.frame_in)


@dataclass(frozen=True)
class LineFrameTiming:
    """Resolved timeline frames for one LyricLine and its timed units."""

    frame_in: int
    frame_out: int
    sing_end_frame: int
    fade_frames: int
    unit_frames: tuple[UnitFrameTiming, ...] = ()


def _build_plain_units(text):
    return tuple(
        LyricUnit(
            text=unit_text,
            char_index=char_index,
            is_space=unit_text.isspace(),
        )
        for unit_text, char_index in lyric_display_units(text)
    )


def _build_yrc_units(text, tokens):
    char_intervals = []
    for token in tokens or ():
        if not isinstance(token, dict):
            continue
        value = str(token.get("text", ""))
        if not value:
            continue
        t_start = float(token.get("start_ms", 0))
        t_dur = max(0.0, float(token.get("duration_ms", 0)))
        count = max(1, len(value))
        for char_offset in range(count):
            c_start = t_start + t_dur * (char_offset / count)
            c_end = t_start + t_dur * ((char_offset + 1) / count)
            char_intervals.append((c_start, c_end))

    units = []
    for unit_text, char_index in lyric_display_units(text):
        end_pos = min(len(char_intervals), char_index + len(unit_text))
        if char_index < end_pos:
            start_ms = max(0, round(char_intervals[char_index][0]))
            end_ms = max(start_ms, round(char_intervals[end_pos - 1][1]))
            units.append(
                LyricUnit(
                    text=unit_text,
                    char_index=char_index,
                    is_space=unit_text.isspace(),
                    start_ms=start_ms,
                    duration_ms=end_ms - start_ms,
                )
            )
        else:
            units.append(
                LyricUnit(
                    text=unit_text,
                    char_index=char_index,
                    is_space=unit_text.isspace(),
                )
            )
    return tuple(units)


@dataclass
class LyricDocument:
    """Parsed lyric document with an internal derived-timeline cache."""

    source_path: str = ""
    source_format: str = "LRC"
    file_offset_ms: int = 0
    lines: tuple[LyricLine, ...] = ()
    revision: str = field(default_factory=_new_revision)
    _timeline_key: tuple | None = field(default=None, init=False, repr=False, compare=False)
    _timeline_cache: tuple[LineFrameTiming, ...] | None = field(default=None, init=False, repr=False, compare=False)
    _legacy_signature: tuple[str, str] | None = field(default=None, init=False, repr=False, compare=False)

    @property
    def line_count(self):
        return len(self.lines)

    @property
    def timed_unit_count(self):
        return sum(
            1
            for line in self.lines
            for unit in line.units
            if unit.is_timed and not unit.is_space
        )

    @property
    def is_yrc(self):
        return self.source_format.upper() == "YRC"

    @property
    def is_srt(self):
        return self.source_format.upper() == "SRT"

    def to_entries(self):
        """Return legacy-compatible (seconds, lyric) tuples for layout helpers."""
        return [(line.start_seconds, line.text) for line in self.lines]

    def to_dict(self):
        return {
            "version": DOC_SCHEMA_VERSION,
            "source_path": self.source_path,
            "source_format": self.source_format.upper(),
            "file_offset_ms": int(self.file_offset_ms),
            "lines": [line.to_dict() for line in self.lines],
        }

    @classmethod
    def from_dict(cls, data, revision=None):
        if not isinstance(data, dict):
            raise ValueError("Lyric document payload must be a JSON object.")
        raw_lines = data.get("lines", [])
        if not isinstance(raw_lines, list):
            raise ValueError("Lyric document lines must be a list.")
        parsed_lines = [
            LyricLine.from_dict(item, fallback_index=i)
            for i, item in enumerate(raw_lines)
            if isinstance(item, dict) and str(item.get("text", "")).strip()
        ]
        parsed_lines.sort(key=lambda item: item.start_ms)
        lines = tuple(
            LyricLine(
                index=i,
                text=line.text,
                start_ms=line.start_ms,
                duration_ms=line.duration_ms,
                units=line.units,
                align=line.align,
                valign=line.valign,
                bold=line.bold,
                italic=line.italic,
                underline=line.underline,
                color=line.color,
            )
            for i, line in enumerate(parsed_lines)
        )
        return cls(
            source_path=str(data.get("source_path", "")),
            source_format=str(data.get("source_format", "LRC")).upper(),
            file_offset_ms=int(data.get("file_offset_ms", 0)),
            lines=lines,
            revision=str(revision) if revision else _new_revision(),
        )

    @classmethod
    def from_lrc_entries(cls, entries, source_path="", file_offset_ms=0, revision=None):
        cleaned = [
            (max(0.0, float(seconds)), str(lyric))
            for seconds, lyric in entries
            if str(lyric).strip()
        ]
        cleaned.sort(key=lambda item: item[0])
        lines = tuple(
            LyricLine(
                index=i,
                text=lyric,
                start_ms=round(seconds * 1000.0),
                duration_ms=None,
                units=_build_plain_units(lyric),
            )
            for i, (seconds, lyric) in enumerate(cleaned)
        )
        return cls(
            source_path=str(source_path),
            source_format="LRC",
            file_offset_ms=int(file_offset_ms),
            lines=lines,
            revision=str(revision) if revision else _new_revision(),
        )

    @classmethod
    def from_yrc_entries(cls, sentences, detailed, source_path="", revision=None):
        valid_detailed = [
            item
            for item in (detailed or ())
            if isinstance(item, dict) and str(item.get("text", "")).strip()
        ]
        if not valid_detailed:
            return cls.from_lrc_entries(sentences, source_path=source_path, file_offset_ms=0, revision=revision)

        valid_detailed.sort(key=lambda item: int(item.get("start_ms", 0)))
        lines = []
        for i, item in enumerate(valid_detailed):
            text = str(item.get("text", ""))
            start_ms = max(0, int(item.get("start_ms", 0)))
            dur_raw = item.get("duration_ms")
            duration_ms = max(0, int(dur_raw)) if dur_raw is not None else None
            units = _build_yrc_units(text, item.get("tokens", ()))
            lines.append(
                LyricLine(
                    index=i,
                    text=text,
                    start_ms=start_ms,
                    duration_ms=duration_ms,
                    units=units,
                )
            )
        return cls(
            source_path=str(source_path),
            source_format="YRC",
            file_offset_ms=0,
            lines=tuple(lines),
            revision=str(revision) if revision else _new_revision(),
        )

    @classmethod
    def from_srt_entries(cls, cues, source_path="", revision=None):
        valid_cues = [
            item
            for item in (cues or ())
            if isinstance(item, dict) and str(item.get("text", "")).strip()
        ]
        valid_cues.sort(key=lambda item: int(item.get("start_ms", 0)))
        lines = []
        for i, item in enumerate(valid_cues):
            text = str(item.get("text", ""))
            start_ms = max(0, int(item.get("start_ms", 0)))
            dur_raw = item.get("duration_ms")
            if dur_raw is None and item.get("end_ms") is not None:
                dur_raw = max(0, int(item["end_ms"]) - start_ms)
            duration_ms = max(0, int(dur_raw)) if dur_raw is not None else None
            align = str(item["align"]).upper() if item.get("align") else None
            valign = str(item["valign"]).upper() if item.get("valign") else None
            color = str(item["color"]) if item.get("color") else None
            lines.append(
                LyricLine(
                    index=i,
                    text=text,
                    start_ms=start_ms,
                    duration_ms=duration_ms,
                    units=_build_plain_units(text),
                    align=align,
                    valign=valign,
                    bold=bool(item.get("bold", False)),
                    italic=bool(item.get("italic", False)),
                    underline=bool(item.get("underline", False)),
                    color=color,
                )
            )
        return cls(
            source_path=str(source_path),
            source_format="SRT",
            file_offset_ms=0,
            lines=tuple(lines),
            revision=str(revision) if revision else _new_revision(),
        )

    @classmethod
    def from_legacy_scene(cls, scene):
        raw_entries = scene.get("lyric_pv_entries", "")
        if not raw_entries:
            return None
        try:
            decoded = json.loads(raw_entries) if isinstance(raw_entries, str) else raw_entries
            entries = [(float(item[0]), str(item[1])) for item in decoded]
        except (TypeError, ValueError, IndexError, json.JSONDecodeError):
            return None
        if not entries:
            return None
        source_path = str(scene.get("lyric_pv_source", ""))
        source_format = str(scene.get("lyric_pv_source_format", "LRC")).upper()
        file_offset_ms = int(scene.get("lyric_pv_file_offset_ms", 0))
        if source_format == "YRC":
            raw_yrc = scene.get("lyric_pv_yrc_entries", "[]")
            try:
                detailed = json.loads(raw_yrc) if isinstance(raw_yrc, str) else raw_yrc
            except (TypeError, ValueError, json.JSONDecodeError):
                detailed = []
            if isinstance(detailed, list) and detailed:
                return cls.from_yrc_entries(entries, detailed, source_path=source_path)
        return cls.from_lrc_entries(entries, source_path=source_path, file_offset_ms=file_offset_ms)

    def get_timeline(self, fps, start_frame, time_offset=0.0, hold_gap=3.0, fade_frames=8):
        """Return cached frame timings for all lines and timed units."""
        safe_fps = max(1e-3, float(fps))
        base_frame = int(start_frame)
        offset = float(time_offset)
        gap = max(0.05, float(hold_gap))
        fade_req = max(0, int(fade_frames))
        key = (round(safe_fps, 4), base_frame, round(offset, 4), round(gap, 4), fade_req)
        if self._timeline_key == key and self._timeline_cache is not None:
            return self._timeline_cache

        timings = []
        line_count = len(self.lines)
        for idx, line in enumerate(self.lines):
            start_seconds = max(0.0, line.start_seconds + offset)
            frame_in = base_frame + round(start_seconds * safe_fps)
            next_start_frame = None
            for next_idx in range(idx + 1, line_count):
                if self.lines[next_idx].start_ms > line.start_ms:
                    next_seconds = max(0.0, self.lines[next_idx].start_seconds + offset)
                    next_start_frame = base_frame + round(next_seconds * safe_fps)
                    break

            if line.duration_ms is not None and line.duration_ms > 0:
                sing_end_seconds = max(start_seconds + 0.05, (line.start_ms + line.duration_ms) / 1000.0 + offset)
                sing_end_frame = max(frame_in + 1, base_frame + round(sing_end_seconds * safe_fps))
                tail_end_frame = sing_end_frame + fade_req
                if next_start_frame is not None:
                    frame_out = max(frame_in + 1, min(next_start_frame, tail_end_frame))
                else:
                    frame_out = max(frame_in + 1, tail_end_frame)
            else:
                next_seconds = self.lines[idx + 1].start_seconds if idx + 1 < line_count else line.start_seconds + gap
                end_seconds = max(start_seconds + 0.05, next_seconds + offset)
                frame_out = max(frame_in + 1, base_frame + round(end_seconds * safe_fps))
                sing_end_frame = frame_out

            effective_fade = min(fade_req, max(0, (frame_out - frame_in) // 2))
            clamped_sing_end = min(sing_end_frame, frame_out)

            computed_units = []
            if line.has_word_timing:
                last_end = frame_in
                for unit in line.units:
                    if unit.is_timed:
                        u_start_sec = max(0.0, unit.start_ms / 1000.0 + offset)
                        u_end_sec = max(u_start_sec, unit.end_ms / 1000.0 + offset)
                        u_in = max(frame_in, min(frame_out - 1, base_frame + round(u_start_sec * safe_fps)))
                        u_out = max(u_in + 1, min(frame_out, base_frame + round(u_end_sec * safe_fps)))
                        last_end = u_out
                    else:
                        u_in = max(frame_in, min(frame_out - 1, last_end))
                        u_out = max(u_in + 1, min(frame_out, u_in + 1))
                    computed_units.append(UnitFrameTiming(frame_in=u_in, frame_out=u_out))
            elif line.units:
                span_end = max(frame_in + 1, clamped_sing_end)
                visible_indices = [ui for ui, u in enumerate(line.units) if not u.is_space]
                visible_map = {}
                if visible_indices:
                    total_visible = len(visible_indices)
                    span = max(1, span_end - frame_in)
                    for rank, ui in enumerate(visible_indices):
                        raw_in = frame_in + round(span * rank / total_visible)
                        raw_out = frame_in + round(span * (rank + 1) / total_visible)
                        u_in = max(frame_in, min(span_end - 1, raw_in))
                        u_out = max(u_in + 1, min(frame_out, raw_out))
                        visible_map[ui] = UnitFrameTiming(frame_in=u_in, frame_out=u_out)
                last_end = frame_in
                for ui in range(len(line.units)):
                    if ui in visible_map:
                        timing_u = visible_map[ui]
                        last_end = timing_u.frame_out
                        computed_units.append(timing_u)
                    else:
                        u_in = max(frame_in, min(frame_out - 1, last_end))
                        u_out = max(u_in + 1, min(frame_out, u_in + 1))
                        computed_units.append(UnitFrameTiming(frame_in=u_in, frame_out=u_out))
            unit_frames = tuple(computed_units)

            timings.append(
                LineFrameTiming(
                    frame_in=frame_in,
                    frame_out=frame_out,
                    sing_end_frame=clamped_sing_end,
                    fade_frames=effective_fade,
                    unit_frames=unit_frames,
                )
            )

        self._timeline_key = key
        self._timeline_cache = tuple(timings)
        return self._timeline_cache


def invalidate_lyric_cache(scene=None):
    """Clear in-memory lyric document cache for one scene or all scenes."""
    if scene is None:
        _DOC_CACHE.clear()
        return
    _DOC_CACHE.pop(_scene_cache_key(scene), None)


def save_lyric_document(scene, doc):
    """Persist a LyricDocument onto the scene as a single JSON payload and cache it."""
    scene[SCENE_DOC_KEY] = json.dumps(doc.to_dict(), ensure_ascii=False)
    scene[SCENE_DOC_REV_KEY] = doc.revision
    for legacy_key in LEGACY_SCENE_KEYS:
        if legacy_key in scene:
            del scene[legacy_key]
    _DOC_CACHE[_scene_cache_key(scene)] = doc
    return doc


def get_lyric_document(scene):
    """Return the cached LyricDocument for a scene, hydrating lazily if needed."""
    if scene is None:
        return None
    cache_key = _scene_cache_key(scene)
    cached = _DOC_CACHE.get(cache_key)
    rev = str(scene.get(SCENE_DOC_REV_KEY, "") or "")

    if cached is not None and rev and cached.revision == rev:
        return cached

    raw_doc = scene.get(SCENE_DOC_KEY, "")
    if raw_doc:
        try:
            decoded = json.loads(raw_doc) if isinstance(raw_doc, str) else raw_doc
            doc = LyricDocument.from_dict(decoded, revision=rev or _new_revision())
        except (TypeError, ValueError, json.JSONDecodeError):
            _DOC_CACHE.pop(cache_key, None)
            return None
        _DOC_CACHE[cache_key] = doc
        return doc

    legacy_entries = scene.get("lyric_pv_entries", "")
    if legacy_entries:
        legacy_yrc = scene.get("lyric_pv_yrc_entries", "")
        signature = (
            legacy_entries if isinstance(legacy_entries, str) else str(legacy_entries),
            legacy_yrc if isinstance(legacy_yrc, str) else str(legacy_yrc),
        )
        if cached is not None and cached._legacy_signature == signature:
            return cached
        doc = LyricDocument.from_legacy_scene(scene)
        if doc is None:
            _DOC_CACHE.pop(cache_key, None)
            return None
        doc._legacy_signature = signature
        _DOC_CACHE[cache_key] = doc
        return doc

    _DOC_CACHE.pop(cache_key, None)
    return None


def clear_lyric_document(scene):
    """Remove all persisted lyric document keys (new and legacy) and drop cache."""
    removed = 0
    for key in (SCENE_DOC_KEY, SCENE_DOC_REV_KEY, *LEGACY_SCENE_KEYS):
        if key in scene:
            del scene[key]
            removed += 1
    _DOC_CACHE.pop(_scene_cache_key(scene), None)
    return removed
