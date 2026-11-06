"""Basic syntax/static check for the LYRIC PV STUDIO add-on.

Run with: python tests/static_check.py [path-to-addon-file-or-dir]
This does not replace enabling and testing the add-on inside Blender.
"""
from pathlib import Path
import ast
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
PKG_DIR = REPO_ROOT / "lyric_pv_studio"
DEFAULT_SOURCE = REPO_ROOT / "LYRIC_PV_STUDIO_v0_5_15_LRC_spacing_fix.py"

target = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None

if target:
    files = list(target.rglob("*.py")) if target.is_dir() else [target]
else:
    files = []
    if PKG_DIR.is_dir():
        files.extend(PKG_DIR.rglob("*.py"))
    if DEFAULT_SOURCE.is_file():
        files.append(DEFAULT_SOURCE)

if not files:
    raise SystemExit("No Python files found to check.")

for py_path in sorted(files):
    if not py_path.is_file():
        raise SystemExit(f"Source file not found: {py_path}")
    text = py_path.read_text(encoding="utf-8")
    ast.parse(text, filename=str(py_path))
    print(f"Syntax OK: {py_path.relative_to(REPO_ROOT)}")

print(f"Successfully checked {len(files)} file(s).")
print("Note: this is a Python syntax check, not a Blender runtime test.")
