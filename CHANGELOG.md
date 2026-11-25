# Changelog

## Unreleased

### 新增与优化
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
