# Changelog

## Unreleased

### 新增与优化
- 更新默认歌词材质与默认几何节点配置：
  - 主歌词材质（`LPV_Text_Material`）升级为 `RGB -> Reroute -> Principled BSDF (Base Color + Emission Color, Roughness=0.5)` 节点结构，默认字幕颜色调整为暖橙色 `(1.0, 0.504, 0.162)`。
  - 新增无影自发光描边材质（`LPV_Text_Outline`，通过 `Light Path.Is Shadow Ray` 混合 `Emission` 与 `Transparent BSDF`）以及默认 `lyc_solidify` 几何节点组（提供 `Text Depth=0.02`、`Outline Thickness=0.0055`、`Z Offset=-0.0015`、`Outline Material` 接口），生成文字对象时自动挂载，并在清理时同步回收孤立的带标记节点组。

## v0.6.0 — SRT support & unified lyric cache

### 新增与优化
- 新增 SRT 字幕格式支持与统一文件导入入口：
  - 将侧边栏导入入口合并为统一文件选择框与「导入歌词 / 字幕」按钮，按 `.lrc` / `.yrc` / `.srt` 扩展名自动识别格式。
  - 新增 `parse_srt_text` 解析器与 `LyricDocument.from_srt_entries`：支持多行字幕、HTML（`<i>`/`<b>`/`<u>`/`<font color>`/`<br>`）及 ASS 覆写标签（`{\an1..9}`/`{\a1..11}`/`\b`/`\i`/`\u`/`\c`），保留格式化对齐/位置/颜色/样式排版；同一开始时间的多条普通字幕自动按换行合并。
  - SRT 退场帧与 YRC 一致，按 `min(下一句开始帧, 结束时间帧 + fade_frames)` 计算，并在同时刻存在不同定位字幕时自动避开 1 帧压缩；逐字排版模式同步支持多行换行显示。
- 新增统一歌词缓存模型与场景存储层（`lyric_pv_studio/core/document.py`）：
  - 通过 `LyricDocument`、`LyricLine`、`LyricUnit` 在导入时一次性完成歌词解析、显示单元切分与 YRC 逐字时间聚合，避免重复解析与按文本反查配对。
  - 引入基于场景标识与版本号（`lyric_pv_doc_rev`）的内存缓存，消除侧边栏 UI 每次重绘时的重复 `json.loads` 开销，并自动适配 Blender Undo/Redo 与 `.blend` 工程切换（`load_post` 自动清理缓存）。
  - 在 `LyricDocument` 内增加派生帧时间缓存（`get_timeline`），同一时间参数下重复生成或重抽排版直接复用计算结果。
  - 统一持久化为单份 `scene["lyric_pv_document"]`，同时兼容读取旧版工程中的 `lyric_pv_entries` / `lyric_pv_yrc_entries`。
  - YRC 整句退场帧改为按 `min(下一句开始帧, 本句唱完帧 + fade_frames)` 计算，直接复用现有淡出帧数设置，避免尾字未唱完即淡出或长间奏滞留。

### 修复
- 修复 `yrc_character_frame_map` 中 `time_offset` 符号取反的问题，确保调整「手动时间偏移」时整句与逐字时间方向一致。

## v0.5.15 — LRC spacing fix

- Fixes LRC EMPHASIS layout so that enlarging the first character accounts for its actual expanded width when spacing subsequent characters.
- Retains the existing per-character text objects and animation approach.
- Does not change YRC per-character timing.
- This repository snapshot is the supplied `LYRIC_PV_STUDIO_v0_5_15_LRC_spacing_fix.py` source and is published unchanged.

Earlier release notes are not reconstructed here because the verified source provided for this repository is v0.5.15.
