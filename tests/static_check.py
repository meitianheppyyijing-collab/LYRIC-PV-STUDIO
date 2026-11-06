"""Basic syntax/static check for the LYRIC PV STUDIO add-on.

Run with: python tests/static_check.py [path-to-addon.py]
This does not replace enabling and testing the add-on inside Blender.
"""
from pathlib import Path
import ast
import sys

DEFAULT_SOURCE = Path(__file__).resolve().parents[1] / "LYRIC_PV_STUDIO_v0_5_15_LRC_spacing_fix.py"
source = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_SOURCE

if not source.is_file():
    raise SystemExit(f"Source file not found: {source}")

text = source.read_text(encoding="utf-8")
ast.parse(text, filename=str(source))
print(f"Syntax OK: {source}")
print("Note: this is a Python syntax check, not a Blender runtime test.")
