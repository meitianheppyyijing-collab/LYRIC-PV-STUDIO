# LYRIC PV STUDIO

[English](README_EN.md) | [简体中文](README.md)

A Blender add-on for creating animated lyric PVs from LRC/YRC lyric files, featuring automatic typography layout, camera occlusion avoidance, and spatial motion animations.

- **Blender:** 5.2 or newer (targets Blender 5.2 LTS)
- **Author / project attribution:** 静意
- **License:** GPL-3.0

## Project Structure

The add-on is organized as a clean, modular Python package located in [`lyric_pv_studio/`](./lyric_pv_studio):

```text
lyric_pv_studio/
├── __init__.py          # Add-on metadata (bl_info) & lifecycle registration
├── constants.py         # Global tags, collections, and styling presets
├── core/                # Parsing, typography advance, layout planning & spatial math
├── animation/           # Scale/motion keyframing & real-time frame handlers
├── blender/             # Collection hierarchy, object cleanup & materials
└── ui/                  # Properties, operators, callbacks & 3D view sidebar panels
```

## Installation

### From Releases (.zip)

1. Download the latest release package `lyric_pv_studio_vx.x.x.zip` from the [Releases](https://github.com/SOR2171/LYRIC-PV-STUDIO/releases) page.
2. In Blender, open **Edit → Preferences → Add-ons**.
3. Click the dropdown in the top-right and choose **Install from Disk…**.
4. Select the downloaded `.zip` file.
5. Enable **LYRIC PV STUDIO** in the add-ons list.
6. In the 3D Viewport, press `N` to open the sidebar and switch to the **歌词PV / Lyric PV** tab.

### From Source

Clone the repository and zip the `lyric_pv_studio` directory into a `.zip` file (or symlink `lyric_pv_studio` into your Blender addons directory).

## Usage

1. Prepare an `.lrc` or `.yrc` lyric file with timestamps.
2. Open the **歌词PV** sidebar panel in Blender.
3. Import your lyric file using the **导入 LRC** or **导入 YRC** button.
4. Adjust typography, alignment, camera, and animation settings as needed.
5. Click **生成歌词排版与动画** to generate the lyric objects and animations in your scene.

For detailed setup notes, see [the installation guide](docs/installation.md) and [user guide](docs/user_guide.md).

## License

Copyright (C) 2026 静意, SOR2171

Licensed under the GNU General Public License v3.0 (GPL-3.0). See [LICENSE](LICENSE).
