"""Unit tests for lyric parsing and layout logic without requiring Blender."""

import random
import unittest

from lyric_pv_studio.core.layout import (
    _choose_animation,
    _new_layout_record,
    _random_amount,
    _split_sections,
    _weighted_choice,
)
from lyric_pv_studio.core.parser import (
    estimate_lyric_unit_advance,
    lyric_display_units,
    parse_lrc_text,
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

    def test_lyric_display_units(self):
        units = lyric_display_units("Can't stop 音乐!")
        texts = [u[0] for u in units]
        self.assertEqual(texts, ["Can't", " ", "stop", " ", "音", "乐", "!"])

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


if __name__ == "__main__":
    unittest.main()
