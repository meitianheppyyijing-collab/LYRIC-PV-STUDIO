# LYRIC PV STUDIO

[English](README_EN.md) | [简体中文](README.md)

一个用于从 LRC/YRC 歌词文件创建动态歌词 PV 的 Blender 插件，具备自动字体排版、摄像机遮挡避让与空间动态动画功能。

- **Blender：** 5.2 或更高版本（目标版本 Blender 5.2 LTS)
- **作者 / 项目归属：** 静意
- **许可证：** GPL-3.0-or-later

## 项目结构

本插件组织为模块化 Python 包，位于 [`lyric_pv_studio/`](./lyric_pv_studio)：

```text
lyric_pv_studio/
├── __init__.py          # 插件元数据 (bl_info) 与生命周期注册
├── constants.py         # 全局标签、集合名称与样式预设
├── core/                # 解析、字体排版步进、布局规划与空间计算
├── animation/           # 缩放/运动关键帧烘焙与实时帧处理器
├── blender/             # 集合层级、对象清理与材质
└── ui/                  # 属性、操作符、回调与 3D 视图侧边栏面板
```

## 安装

### 从 Releases 安装 (.zip)

1. 从 [Releases](https://github.com/SOR2171/LYRIC-PV-STUDIO/releases) 页面下载最新的发布包 `lyric_pv_studio_vx.x.x.zip`。
2. 在 Blender 中，打开 **编辑 → 偏好设置 → 插件**。
3. 点击右上角下拉菜单，选择 **从磁盘安装…**。
4. 选择下载的 `.zip` 文件。
5. 在插件列表中启用 **LYRIC PV STUDIO**。
6. 在 3D 视图中按 `N` 打开侧边栏，切换到 **歌词PV / Lyric PV** 选项卡。

### 从源码安装

克隆本仓库并将 `lyric_pv_studio` 目录压缩为 `.zip` 文件（或将 `lyric_pv_studio` 软链接到你的 Blender 插件目录）。

## 使用方法

1. 准备带有时间戳的 `.lrc` 或 `.yrc` 歌词文件。
2. 在 Blender 中打开 **歌词PV** 侧边栏面板。
3. 点击 **导入 LRC** 或 **导入 YRC** 按钮导入歌词文件。
4. 根据需要调整排版、对齐、摄像机与动画设置。
5. 点击 **生成歌词排版与动画** 在场景中生成歌词对象与动画。

详细设置说明请参阅 [安装指南](docs/installation.md) 和 [用户指南](docs/user_guide.md)。

## 许可证

GPL-3.0-or-later。详见 [LICENSE](LICENSE)。
