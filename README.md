# 口播导演工作台 · Talking Head Studio

从稿件、提词和录制计划开始，把一条口播做成可发布的视频。你可以使用完整的三阶段流程，也可以从已有定稿或已经粗剪好的视频开始。

**当前版本为 2.0.2。Windows 11 x64 / Python 3.12 已完成运行验证。** 当前提供源码部署。macOS 的安装包、中文渲染和实机语音跟随待验证。

[功能](#功能) · [实现原理](#实现原理) · [安装部署](#安装部署) · [使用步骤](#使用步骤) · [与-agent-协作](#与-agent-协作) · [faq](#faq)

## 功能

| 阶段 | 可以做什么 |
| --- | --- |
| **1. 稿件与录制** | Dashboard 提供导入已有稿件、AI 稿件润色和新建项目。Markdown 编辑器支持对比并采用 AI 建议。口播、展示、演示和停顿页可增删与排序，可给句子加制作标记。提词器支持整页适配、镜像、滚动、重录标记和可选的麦克风跟读。 |
| **2. 粗剪与校准** | 从实际录音转写，或导入已有字幕。根据静音和相似重录提出剪点，在确认前可以调整保留区间。已有粗剪可以直接采用，原素材文件保留。 |
| **3. 精剪与交付** | 在时间线上安排字幕、画中画、透明贴纸、流程动画、额外视频、音效和背景乐。支持片段拖拽、精确设置起止、锁轨和静音。预览当前时间线后确认，导出同画幅 MP4。可另存字幕、工程 ZIP 和实验性剪映草稿。 |

## 实现原理

```mermaid
flowchart LR
    A["浏览器工作台"] <-->|本机接口| B["Python 服务"]
    C["主 Skill / Agent CLI"] <-->|项目与待办| B
    B <--> D["本机项目、时间线、素材"]
    B --> E["Whisper 转写 / sherpa-onnx 跟读"]
    B --> F["Playwright / FFmpeg / GIF 工厂"]
    F --> G["样片 → 用户确认 → MP4"]
```

- **稿件、实际转写和字幕分开保存。** 提词页用页面和句子 ID 关联制作标记。前期用预计时间做编排，后期以实际转写和剪点映射为准，把标记校准到成片时间线。
- **粗剪记录保留和删除区间。** 渲染粗剪时根据记录读取原片，用户可以恢复被剪掉的片段。精剪则从当前主轨和辅助轨道重新合成。变更字幕、素材或剪辑后，旧样片的确认会失效。
- **从 HTML 渲染透明叠加层。** Playwright 按帧截取流程、文字和素材画面，FFmpeg 合成视频、字幕和音轨。GIF 工厂轻动效把用户提供的 PNG 转为 GIF。普通文档提取和流程动画由内置实现提供，也可接入经授权的 HTML Creator Studio。
- **工作台在本机运行。** 服务默认监听 `127.0.0.1:8765`。项目、原片引用、导出和模型配置由本机管理。AI 润稿可以由用户选择的 Agent 领取待办，也可配置兼容的 Chat Completions 服务，将稿件发往指定模型。

## 安装部署

### Windows 快速开始

准备 Git、Python 3.12、FFmpeg 和 Edge 或 Chrome。确保 PowerShell 能找到 `ffmpeg` 和 `ffprobe`。选用包含 `libass` 和 `libx264` 的 FFmpeg 构建。 [FFmpeg 官方下载](https://ffmpeg.org/download.html)

```powershell
git clone https://github.com/shynloc/talking-head-studio.git
cd talking-head-studio
python --version
ffmpeg -version
ffprobe -version
python -m venv .venv
.\.venv\Scripts\python.exe scripts/setup.py --install --smoke
.\.venv\Scripts\python.exe scripts/launch.py
```

安装命令会装入 Python 依赖和 Playwright Chromium，并实际编码一段 MP4 检查渲染环境。首次安装需要联网。启动后打开 [本机工作台](http://127.0.0.1:8765)，默认数据目录是用户的 `Documents/TalkingHeadStudio`。

项目目录和端口可自定义。已有实例运行时，可用独立目录和端口试用新版本。

```powershell
.\.venv\Scripts\python.exe scripts/launch.py --data "D:\TalkingHeadStudio" --port 8767
```

从 GitHub 下载源码 ZIP 也可以。Windows 快捷方式包括 `安装依赖.cmd`、`启动工作台.cmd` 和 `安装语音模型.cmd`，它们使用当前 PATH 中的 Python。已有 Codex 安装需要升级时，先完成正在跑的任务。使用同一 Python 环境运行 `scripts/install.py` 可更新默认 Skill 目录并保留一份旧代码备份。

### 按需启用

| 功能 | 如何启用 |
| --- | --- |
| 录音转写与自动字幕 | 运行 `.\.venv\Scripts\python.exe scripts/setup.py --speech` 安装 Whisper。在工作台转写时选择模型，并允许首次下载。已有 SRT 也可直接导入。 |
| 麦克风跟读 | 运行 `.\.venv\Scripts\python.exe scripts/setup_speech.py`，约下载 190 MiB 中文/英文流式模型。自定义了项目目录时，给这条命令传入相同的 `--data`。安装好后可本地识别。 |
| AI 润稿与语义分页 | 默认提交 Codex 待办，由 Agent 领取。也可在首页配置自己的 Chat Completions 地址、模型和密钥。手动编辑和基础规则排页可以直接使用。 |
| GIF 工厂轻动效 | 随仓库提供所需导出器。第三阶段导入透明 PNG，再生成 GIF。 |
| HTML Creator Studio | 将你有权使用的兼容组件放到 `vendor/html-creator-studio/`。工作台识别 `scripts/extract_resume.py` 和 `shared/frame-styles.mjs`。重新启动后可用 `scripts/setup.py` 查看检测结果；PDF 的该适配路径还需要 `pdftotext`。 |
| 剪映草稿 · 实验 | 运行 `.\.venv\Scripts\python.exe -m pip install pyJianYingDraft==0.3.1`。可生成草稿及素材 ZIP，目标剪映版本的打开、轨道与效果兼容性仍需验证。 |

Whisper 用于录制后的转写。提词器的实时跟读使用另一套本地模型，可以分别安装。

## 使用步骤

### 1. 把稿件变成提词页

从首页选择「导入已有稿件」「AI 稿件润色」或「新建项目」。已有定稿可以直接排页；文章可以先改成适合口语的短句。敲定内容后，把每个主题分成一页，在对应句子上标记演示、贴纸或动画需求。有屏幕录制或展示画面时，可单独放入主轨或画中画，并预设时长。

点击「进入提词」。用翻页或定速滚动配合外部相机录制。需要跟读时，先在首页点「麦克风与语音测试」，选择设备、检查音量和识别结果，再在提词器中开启语音跟随。长稿默认尝试整页排布，还可以使用全屏、折叠时间线或「下一屏」继续读。

### 2. 导入录制并确认粗剪

进入第二阶段，选择原片。已经剪好节奏的素材选择「已粗剪」；需要整理的素材先转写，再检查静音和重录候选，调整要保留的区间。生成粗剪后试听、检查剪点，确认满意的版本。用已有字幕时，确认时间戳对应当前导入的视频。

### 3. 校准时间线并出片

按实际口播校准时间线，检查字幕断句、时序与构图。把演示、贴纸和音效放到对应句子附近，试听原声与配乐。点击「成片检查与导出」，选择一段代表性区间生成样片。在同一窗口观看后，点击「确认样片并导出成片」。成片也可在第三阶段的输出列表下载。

继续修改时，重新生成与当前时间线对应的样片。需要备份或换软件时，可以导出项目和字幕，并保留原片及素材。工程 ZIP 可能保留原片外部引用，迁移前备份原片，导入后按界面提示重新关联。

## 与 Agent 协作

本仓库根目录包含 [主 Skill](SKILL.md)。你可以直接使用浏览器工作台，也可以把整个仓库作为本地 Skill 安装到 Codex，并保持本机工作台运行。

通过首页提交润稿或分页待办后，在 Codex 聊天里说「使用口播导演工作台，处理当前稿件待办」。Agent 用 CLI 查看待办，按要求回写建议。回到工作台后可比较、编辑并采用结果。控制终端的其他 Agent 也可以按同一 CLI 读取工程。当前的待办由用户在相应聊天中主动交接。

```powershell
.\.venv\Scripts\python.exe scripts/studio.py status
.\.venv\Scripts\python.exe scripts/studio.py drafts
.\.venv\Scripts\python.exe scripts/studio.py --help
```

使用自定义端口时，把 `--url http://127.0.0.1:8767` 放在子命令之前。项目编号与任务编号由 CLI 返回。

## FAQ

### 没有模型密钥，能工作吗？

可以手动编稿、用规则分页、编辑时间线，并用已有字幕出片。AI 润稿可以由当前 Agent 处理待办；本地转写和实时跟读各自使用本地模型。

### 麦克风有音量，但文字不亮怎么办？

先检查跟读模型是否安装，然后在「麦克风与语音测试」里选择实际使用的设备并试读一句。若内嵌浏览器无法采集，改用 Edge 或 Chrome 打开工作台的本机网址。长段稿件可手动定位或翻页。

### 为何不能直接点「导出成片」？

先完成原片导入和粗剪准备，校准实际时间线并绑定需要展示的素材。随后从「成片检查与导出」生成并观看当前样片，在窗口内确认后可以导出。时间线变更后需要一份对应的新样片。

### 我的原片会被覆盖或上传吗？

工作台生成新的粗剪和成片文件，原素材保留在本机。使用外部模型服务进行润稿或分页时，提交的稿件会发送至自行配置的服务地址。使用其他 Agent 的在线工具时，按需明确选择要交接的资料。

### 已经有精剪软件，能继续在那里编辑吗？

可以带走原片、字幕和工程所用素材。剪映目前提供实验性草稿导出。ChatCut 接入和自动继续其他 Agent 对话属于后续集成方向。

### 为什么只有 Windows 部署步骤？

当前发布的是已在 Windows 验证的源代码版本。macOS 是后续部署目标，需完成依赖安装、中文字体、实机麦克风和完整导出验收。

### 重装后找不到项目怎么办？

确认启动使用原来的数据目录。默认是 `Documents/TalkingHeadStudio`。如果以前使用了 `--data`，继续传入同一目录。工程包中的外部原片可通过设置中的「重新定位原片」恢复关联。

## 第三方组件

- [GIF 工厂](https://github.com/WoYun520/gif-factory) 的轻动效导出器，保留 [MIT 许可](vendor/gif-factory/LICENSE)。
- [Vditor](https://github.com/Vanessa219/vditor) 的本地静态资源，保留 [MIT 许可](assets/workbench/vendor/vditor/LICENSE) 及其分发文件中的第三方声明。
- HTML Creator Studio 通过可选本地目录接入。Whisper 模型、sherpa-onnx 模型、FFmpeg 和 Chromium 按需从各自渠道安装。

第三方组件的许可适用于对应文件。主项目的源码公开可查看，主项目许可由维护者另行声明。
