"""Unit tests for lyric parsing, document caching, and layout logic without requiring Blender."""

import json
import random
import unittest

from lyric_pv_studio.core.document import (
    LyricDocument,
    SCENE_DOC_KEY,
    SCENE_DOC_REV_KEY,
    clear_lyric_document,
    get_lyric_document,
    invalidate_lyric_cache,
    save_lyric_document,
)
from lyric_pv_studio.core.layout import (
    _choose_animation,
    _new_layout_record,
    get_random_amount,
    _split_sections,
    _weighted_choice,
)
from lyric_pv_studio.core.parser import (
    detect_lyric_format,
    estimate_lyric_unit_advance,
    lyric_display_units,
    parse_lrc_text,
    parse_srt_text,
    parse_yrc_text,
    yrc_character_frame_map,
)


class TestParser(unittest.TestCase):
    def test_parse_lrc_basic(self):
        text = """[offset:500]
[00:01.00]First line
[00:03.50]Second line
"""
        entries, offset = parse_lrc_text(text)
        self.assertEqual(offset, 500)
        self.assertEqual(len(entries), 2)
        self.assertAlmostEqual(entries[0][0], 1.5, places=2)
        self.assertEqual(entries[0][1], "First line")
        self.assertAlmostEqual(entries[1][0], 4.0, places=2)
        self.assertEqual(entries[1][1], "Second line")

    def test_parse_yrc_basic(self):
        text = "[1000,2500](1000,500,0)Hello (1500,1000,0)World\n"
        sentences, detailed = parse_yrc_text(text)
        self.assertEqual(len(sentences), 1)
        self.assertEqual(sentences[0][1], "Hello World")
        self.assertEqual(len(detailed), 1)
        self.assertEqual(detailed[0]["duration_ms"], 2500)

        frames = yrc_character_frame_map(detailed[0], fps=24.0, start_frame=1)
        self.assertEqual(len(frames), len("Hello World"))

        shifted = yrc_character_frame_map(detailed[0], fps=24.0, start_frame=1, time_offset=1.0)
        self.assertEqual(shifted[0], frames[0] + 24)
        earlier = yrc_character_frame_map(detailed[0], fps=24.0, start_frame=1, time_offset=-0.5)
        self.assertEqual(earlier[0], frames[0] - 12)

    def test_lyric_display_units(self):
        units = lyric_display_units("Can't stop 音乐!")
        texts = [u[0] for u in units]
        self.assertEqual(texts, ["Can't", " ", "stop", " ", "音", "乐", "!"])

        multiline_units = lyric_display_units("Hello\n世界")
        self.assertEqual([u[0] for u in multiline_units], ["Hello", "\n", "世", "界"])

    def test_detect_lyric_format(self):
        self.assertEqual(detect_lyric_format("song.lrc"), "LRC")
        self.assertEqual(detect_lyric_format("SONG.YRC"), "YRC")
        self.assertEqual(detect_lyric_format("/tmp/sub.SRT"), "SRT")
        self.assertIsNone(detect_lyric_format("notes.txt"))

    def test_parse_srt_formatting_and_simultaneous_merge(self):
        srt_text = (
            "\ufeff1\n"
            "00:00:01,000 --> 00:00:03,500 X1:100 X2:500\n"
            "{\\an8\\b1\\i1}<i>Top &amp; Bold</i><br/>Line two\n\n"
            "2\n"
            "00:00:01.000 --> 00:00:04.000\n"
            "{\\an2}<font color=\"#ffcc00\">Bottom Yellow</font>\n\n"
            "3\n"
            "00:00:06,000 --> 00:00:08,000\n"
            "English line\n\n"
            "4\n"
            "00:00:06,000 --> 00:00:09,000\n"
            "<u>中文翻译</u>\n"
        )
        cues = parse_srt_text(srt_text)
        # Cues 1 & 2 share start_ms=1000 but have distinct explicit placement (TOP vs BOTTOM).
        # Cues 3 & 4 share start_ms=6000 with no conflicting placement -> merged with newline.
        self.assertEqual(len(cues), 3)

        self.assertEqual(cues[0]["start_ms"], 1000)
        self.assertEqual(cues[0]["duration_ms"], 2500)
        self.assertEqual(cues[0]["text"], "Top & Bold\nLine two")
        self.assertEqual(cues[0]["align"], "CENTER")
        self.assertEqual(cues[0]["valign"], "TOP")
        self.assertTrue(cues[0]["bold"])
        self.assertTrue(cues[0]["italic"])

        self.assertEqual(cues[1]["align"], "CENTER")
        self.assertEqual(cues[1]["valign"], "BOTTOM")
        self.assertEqual(cues[1]["color"], "#FFCC00")

        self.assertEqual(cues[2]["start_ms"], 6000)
        self.assertEqual(cues[2]["duration_ms"], 3000)
        self.assertEqual(cues[2]["text"], "English line\n中文翻译")
        self.assertTrue(cues[2]["underline"])

    def test_estimate_advance(self):
        adv_cjk = estimate_lyric_unit_advance("字", 1.0)
        adv_i = estimate_lyric_unit_advance("i", 1.0)
        self.assertGreater(adv_cjk, adv_i)


class TestLayout(unittest.TestCase):
    def test_split_sections(self):
        entries = [(1.0, "a"), (3.0, "b"), (10.0, "c"), (12.0, "d")]
        sections = _split_sections(entries, gap=4.0)
        self.assertEqual(sections, [[0, 1], [2, 3]])

    def test_new_layout_record(self):
        rng = random.Random(12345)
        rec = _new_layout_record(rng)
        self.assertIn("style", rec)
        self.assertIn("font_multiplier", rec)
        self.assertIn("animation", rec)
        self.assertIn("entrance", rec)
        self.assertFalse(rec["locked"])


class TestAnimation(unittest.TestCase):
    def test_smooth_action_fcurves_mock(self):
        from lyric_pv_studio.animation.keyframing import smooth_action_fcurves

        # Non-animated object
        class DummyEmpty:
            animation_data = None

        smooth_action_fcurves(DummyEmpty())

        # Mock object with action and fcurves
        class KeyPoint:
            interpolation = "LINEAR"
            handle_left_type = "FREE"
            handle_right_type = "FREE"

        class FCurve:
            keyframe_points = [KeyPoint(), KeyPoint()]

        class Action:
            fcurves = [FCurve()]

        class AnimData:
            action = Action()

        class DummyObj:
            animation_data = AnimData()

        obj = DummyObj()
        smooth_action_fcurves(obj)
        for kp in obj.animation_data.action.fcurves[0].keyframe_points:
            self.assertEqual(kp.interpolation, "BEZIER")
            self.assertEqual(kp.handle_left_type, "AUTO_CLAMPED")
            self.assertEqual(kp.handle_right_type, "AUTO_CLAMPED")


class TestLyricDocumentCache(unittest.TestCase):
    def setUp(self):
        invalidate_lyric_cache()

    def tearDown(self):
        invalidate_lyric_cache()

    def test_yrc_document_units_and_roundtrip(self):
        yrc_text = (
            "[1000,2000](1000,200,0)Hel(1200,300,0)lo (1500,500,0)世(2000,1000,0)界\n"
            "[8000,1500](8000,1500,0)尾声\n"
        )
        sentences, detailed = parse_yrc_text(yrc_text)
        doc = LyricDocument.from_yrc_entries(sentences, detailed, source_path="demo.yrc")
        self.assertTrue(doc.is_yrc)
        self.assertEqual(doc.line_count, 2)

        first = doc.lines[0]
        self.assertEqual(first.duration_ms, 2000)
        self.assertEqual([u.text for u in first.units], ["Hello", " ", "世", "界"])
        # Multi-token English word merges start/end cleanly ("lo " = 3 chars -> "lo" ends at 1400ms).
        self.assertEqual(first.units[0].start_ms, 1000)
        self.assertEqual(first.units[0].end_ms, 1400)
        self.assertEqual(first.units[1].start_ms, 1400)
        self.assertEqual(first.units[1].end_ms, 1500)
        self.assertEqual(first.units[2].start_ms, 1500)
        self.assertEqual(first.units[2].duration_ms, 500)

        restored = LyricDocument.from_dict(doc.to_dict(), revision=doc.revision)
        self.assertEqual(restored.lines, doc.lines)
        self.assertEqual(restored.source_format, "YRC")

    def test_timeline_cache_yrc_tail_and_time_offset(self):
        yrc_text = (
            "[1000,2000](1000,1000,0)你(2000,1000,0)好\n"
            "[10000,1000](10000,1000,0)再见\n"
        )
        sentences, detailed = parse_yrc_text(yrc_text)
        doc = LyricDocument.from_yrc_entries(sentences, detailed)

        t1 = doc.get_timeline(fps=24.0, start_frame=1, time_offset=0.0, hold_gap=3.0, fade_frames=8)
        t2 = doc.get_timeline(fps=24.0, start_frame=1, time_offset=0.0, hold_gap=3.0, fade_frames=8)
        self.assertIs(t1, t2)

        # First line sings 1s..3s (frames 25..73), ends at sing_end + fade_frames (81),
        # well before the next line at 10s (frame 241).
        self.assertEqual(t1[0].frame_in, 25)
        self.assertEqual(t1[0].sing_end_frame, 73)
        self.assertEqual(t1[0].frame_out, 81)
        self.assertEqual(t1[0].unit_frames[0].frame_in, 25)
        self.assertEqual(t1[0].unit_frames[1].frame_in, 49)

        # Positive time_offset shifts both sentence and per-character frames forward together.
        t_shifted = doc.get_timeline(fps=24.0, start_frame=1, time_offset=2.0, hold_gap=3.0, fade_frames=8)
        self.assertIsNot(t1, t_shifted)
        self.assertEqual(t_shifted[0].frame_in, 25 + 48)
        self.assertEqual(t_shifted[0].unit_frames[0].frame_in, 25 + 48)
        self.assertEqual(t_shifted[0].unit_frames[1].frame_in, 49 + 48)

    def test_scene_cache_revision_undo_and_legacy_fallback(self):
        scene = {}
        doc1 = LyricDocument.from_lrc_entries([(1.0, "第一句"), (3.0, "第二句")], source_path="a.lrc")
        save_lyric_document(scene, doc1)

        # Fast-path hit returns exact cached instance.
        self.assertIs(get_lyric_document(scene), doc1)

        # Simulate Blender Undo restoring an older revision in scene IDProperties.
        old_payload = scene[SCENE_DOC_KEY]
        old_rev = scene[SCENE_DOC_REV_KEY]
        doc2 = LyricDocument.from_lrc_entries([(2.0, "新歌词")], source_path="b.lrc")
        save_lyric_document(scene, doc2)
        self.assertIs(get_lyric_document(scene), doc2)

        scene[SCENE_DOC_KEY] = old_payload
        scene[SCENE_DOC_REV_KEY] = old_rev
        rehydrated = get_lyric_document(scene)
        self.assertIsNotNone(rehydrated)
        self.assertEqual(rehydrated.line_count, 2)
        self.assertEqual(rehydrated.lines[0].text, "第一句")
        self.assertIs(get_lyric_document(scene), rehydrated)

        clear_lyric_document(scene)
        self.assertIsNone(get_lyric_document(scene))
        self.assertNotIn(SCENE_DOC_KEY, scene)

        # Legacy .blend compatibility fallback + cache reuse.
        legacy_scene = {
            "lyric_pv_entries": json.dumps([[1.5, "旧版歌词"]]),
            "lyric_pv_source_format": "LRC",
        }
        legacy_doc = get_lyric_document(legacy_scene)
        self.assertIsNotNone(legacy_doc)
        self.assertEqual(legacy_doc.lines[0].text, "旧版歌词")
        self.assertIs(get_lyric_document(legacy_scene), legacy_doc)

    def test_srt_document_roundtrip_and_timeline_tail(self):
        srt_text = (
            "1\n"
            "00:00:01,000 --> 00:00:03,000\n"
            "{\\an7}<font color=\"cyan\">左上角</font>\n\n"
            "2\n"
            "00:00:01,000 --> 00:00:03,000\n"
            "{\\an3}右下角\n\n"
            "3\n"
            "00:00:03,100 --> 00:00:05,000\n"
            "紧接下一句\n"
        )
        cues = parse_srt_text(srt_text)
        doc = LyricDocument.from_srt_entries(cues, source_path="demo.srt")
        self.assertTrue(doc.is_srt)
        self.assertEqual(doc.line_count, 3)

        restored = LyricDocument.from_dict(doc.to_dict(), revision=doc.revision)
        self.assertEqual(restored.lines, doc.lines)
        self.assertEqual(restored.lines[0].align, "LEFT")
        self.assertEqual(restored.lines[0].valign, "TOP")
        self.assertEqual(restored.lines[0].color, "#00FFFF")

        # Line 0 & 1 both start at 1.0s (frame 25), end at 3.0s (frame 73);
        # next strictly later line starts at 3.1s (frame 75), so both clamp cleanly to 75
        # instead of collapsing to 1 frame against each other.
        # Last line (3.1s..5.0s = frames 75..121) extends by fade_frames (8 -> 129).
        timeline = doc.get_timeline(fps=24.0, start_frame=1, time_offset=0.0, hold_gap=3.0, fade_frames=8)
        self.assertEqual(timeline[0].frame_in, 25)
        self.assertEqual(timeline[0].frame_out, 75)
        self.assertEqual(timeline[1].frame_in, 25)
        self.assertEqual(timeline[1].frame_out, 75)
        self.assertEqual(timeline[2].frame_in, 75)
        self.assertEqual(timeline[2].sing_end_frame, 121)
        self.assertEqual(timeline[2].frame_out, 129)

    def test_even_per_char_timeline_for_lrc_and_srt(self):
        # LRC: 4 characters over 1.0s..3.0s at 24fps (frames 25..73, span 48 -> 12 frames each).
        lrc_doc = LyricDocument.from_lrc_entries([(1.0, "你好世界"), (3.0, "尾声")])
        lrc_tl = lrc_doc.get_timeline(fps=24.0, start_frame=1, time_offset=0.0, hold_gap=3.0, fade_frames=8)
        self.assertEqual(len(lrc_tl[0].unit_frames), 4)
        self.assertEqual(
            [(u.frame_in, u.frame_out) for u in lrc_tl[0].unit_frames],
            [(25, 37), (37, 49), (49, 61), (61, 73)],
        )

        # SRT: spaces & newlines do not consume singing time; visible units divide [frame_in, sing_end_frame].
        cues = parse_srt_text(
            "1\n00:00:01,000 --> 00:00:03,000\nHi 世\n界\n"
        )
        srt_doc = LyricDocument.from_srt_entries(cues)
        srt_tl = srt_doc.get_timeline(fps=24.0, start_frame=1, time_offset=0.0, hold_gap=3.0, fade_frames=8)
        # Units: ["Hi", " ", "世", "\n", "界"] -> 3 visible units dividing frames 25..73 (16 frames each).
        self.assertEqual(len(srt_tl[0].unit_frames), 5)
        self.assertEqual((srt_tl[0].unit_frames[0].frame_in, srt_tl[0].unit_frames[0].frame_out), (25, 41))
        self.assertEqual((srt_tl[0].unit_frames[2].frame_in, srt_tl[0].unit_frames[2].frame_out), (41, 57))
        self.assertEqual((srt_tl[0].unit_frames[4].frame_in, srt_tl[0].unit_frames[4].frame_out), (57, 73))


if __name__ == "__main__":
    unittest.main()
