# AGENTS.md

Blender 5.2+ 歌词 PV 插件 **LYRIC PV STUDIO** 的仓库地图与协作约定。

## 代码模块（`lyric_pv_studio/`）

- `__init__.py`：插件元数据（`bl_info`）、类注册，以及 `frame_change_post` / `load_post` 处理器挂载与注销。
- `constants.py`：全局常量——集合名 `PV_ROOT_NAME`、归属标记 `PV_TAG`、版本号 `PV_VERSION`、排版与动画枚举。
- `core/`（核心算法；除 `spatial.py` 外保持零 `bpy` 依赖，便于脱离 Blender 单测）
  - `core/parser.py`：LRC/YRC/SRT 文件读取、格式识别与正则解析、中英文显示单元断词、字宽步进估算。
  - `core/document.py`：`LyricDocument`/`LyricLine`/`LyricUnit` 模型、派生帧缓存（`get_timeline`）、`scene["lyric_pv_document"]` 单源持久化与版本校验内存缓存（兼容旧工程与 Undo）。
  - `core/layout.py`：按时间间隔分段、随机排版/动画权重抽样、`scene["lyric_pv_layouts"]` 读写与重抽。
  - `core/spatial.py`：摄像机视锥边界、安全框缩放、人物深度遮挡距离与二维避让（依赖 `bpy`/`mathutils`）。
- `animation/`
  - `animation/keyframing.py`：缩放、逐字显隐、旋转/弹跳/漂浮关键帧烘焙与贝塞尔曲线防过冲平滑。
  - `animation/runtime.py`：逐帧实时入退场缓动计算、帧事件缓存（`_ENTRANCE_CACHE`）与 `load_post` 缓存清理回调。
- `blender/`
  - `blender/collections.py`：插件专用集合创建、基于 `PV_TAG` 的安全删除与孤立数据块回收、旧背景集合清理。
  - `blender/materials.py`：基于 `Principled BSDF` 的共享发光字幕材质创建与复用。
- `ui/`
  - `ui/properties.py`：挂在 `Scene.lyric_pv_props` 上的全部参数定义（`LYRICPV_Properties`）。
  - `ui/operators.py`：统一导入 LRC/YRC/SRT、生成歌词 PV、全量/单句重抽、锁定/解锁、彻底清理等操作符。
  - `ui/callbacks.py`：视口显隐、字号、摄像机距离/位置与入场速度变化时的实时联动回调。
  - `ui/panels.py`：3D 视图侧边栏（N 面板）「歌词PV」界面绘制。

## 测试（`tests/`）

- `tests/static_check.py`：扫描 `lyric_pv_studio/` 做 Python AST 语法检查。
- `tests/test_units.py`：无 Blender 环境的纯 Python 单元测试（解析、缓存、排版、动画曲线）。

## 文档（Markdown）

- `README.md` / `README_EN.md`：简体中文（默认）与英文项目简介、目录与安装用法；调整对外功能或结构时双语同步。
- `CHANGELOG.md`：累积式版本日志；按 `## vX.Y.Z...` 或 `## Unreleased` 分段，改动用户可见行为时更新。
- `CONTRIBUTING.md`：提 Issue/PR 规范与测试声明要求。
- `docs/installation.md`：Blender 插件安装步骤与面板缺失排查。
- `docs/user_guide.md`：歌词准备、PV 生成流程与版本行为说明。

## GitHub Actions（`.github/workflows/`）

- `.github/workflows/release.yml`：推送 `v*` tag 时触发——将 `lyric_pv_studio/` 打包为 `lyric_pv_studio_<tag>.zip`（剔除 `__pycache__`），从 `CHANGELOG.md` 截取对应 tag 段落（无匹配时回退 `Unreleased`）且**不含 `##` 版本标题行**的正文到 `RELEASE_NOTES.md`，作为 GitHub Release 正文发布并附加自动生成变更列表。

## 关键约定与校验

- **对象安全边界**：插件生成的集合、对象与材质均打上 `PV_TAG`，清理流程仅删除带标记项，保护用户原场景。
- **修改后验证**：运行 `python tests/static_check.py && python -m unittest discover -s tests -p "test_*.py" -v`；汇报结果时明确区分静态/单测通过与 Blender 实机验证。
