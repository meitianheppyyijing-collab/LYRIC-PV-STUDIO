# LYRIC PV STUDIO

A Blender add-on for creating animated lyric PVs from LRC lyric files.

- **Version:** 0.5.15
- **Blender:** 5.2 or newer (the add-on metadata targets Blender 5.2)
- **Author / project attribution:** 静意
- **License:** GPL-3.0-or-later

## Source

The add-on is provided as a single Python file: [`LYRIC_PV_STUDIO_v0_5_15_LRC_spacing_fix.py`](./LYRIC_PV_STUDIO_v0_5_15_LRC_spacing_fix.py).

This is the user's supplied v0.5.15 LRC spacing-fix source. The source file is published without editing.

## Installation

1. Download the `.py` file from this repository.
2. In Blender, open **Edit → Preferences → Add-ons**.
3. Choose **Install from Disk…** and select the downloaded `.py` file.
4. Enable **LYRIC PV STUDIO** in the add-ons list.
5. Open the 3D View sidebar and locate the **Lyric PV** panel.

If the add-on does not appear, check the Blender system console for registration or Python errors and confirm that the installed file is the v0.5.15 source above.

## Usage

Prepare an LRC lyric file with timestamps, install and enable the add-on, then use its Lyric PV panel to import and generate lyric content. Exact controls and supported options are defined by the add-on UI and source code; consult [the installation notes](docs/installation.md) and [user guide](docs/user_guide.md).

## Versioning

Version history is recorded in [CHANGELOG.md](CHANGELOG.md). Published source snapshots should remain intact; use a new versioned file and Git tag for future releases.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
