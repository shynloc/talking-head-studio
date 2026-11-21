# 口播导演工作台 · Talking Head Studio

从稿件、提词和录制计划开始，把一条口播做成可发布的视频。你可以使用完整的三阶段流程，也可以从已有定稿或已经粗剪好的视频开始。

**Windows 11 x64 / Python 3.12 已完成运行验证。** Windows 提供从源码安装的独立工作台入口。macOS 提供源码安装脚本与 Finder 启动入口的实现，原生运行和正式签名安装包待验收。

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
- **从 HTML 渲染透明叠加层。** 内嵌 HTML Creator Studio 的帧函数驱动流程动画，Playwright 按帧截取画面，FFmpeg 合成视频、字幕和音轨。GIF 工厂轻动效把用户提供的 PNG 转为 GIF。
- **工作台在本机运行。** 服务默认监听 `127.0.0.1:8765`。项目、原片引用、导出和模型配置由本机管理。AI 润稿可以由用户选择的 Agent 领取待办，也可配置兼容的 Chat Completions 服务，将稿件发往指定模型。

## 安装部署

### Windows

准备 Python 3.12、完整 FFmpeg 和 Edge 或 Chrome。确认终端能找到 `python`、`ffmpeg` 和 `ffprobe`。FFmpeg 需要提供 `libass` 和 `libx264`，可用 `winget install --exact --id Gyan.FFmpeg` 安装。 [FFmpeg 官方下载](https://ffmpeg.org/download.html)

下载并解压本仓库，双击 `安装工作台.cmd`。脚本创建独立的 Python 环境、安装核心依赖、实际验证中文渲染和编码，然后添加开始菜单「口播导演工作台」。应用默认安装在当前用户的 `%LOCALAPPDATA%\TalkingHeadStudio` 下。项目保存在独立的数据目录。

### macOS

以下是待实机验收的 Apple 芯片 Mac 源码部署步骤。终端进入本仓库，使用 Homebrew 安装 Python 和带 `libass` 的完整 FFmpeg。启动器会查找 Homebrew 的 FFmpeg 路径。 [Python 3.12](https://formulae.brew.sh/formula/python@3.12) · [FFmpeg Full](https://formulae.brew.sh/formula/ffmpeg-full)

```bash
brew install python@3.12 ffmpeg-full
/bin/bash ./install_macos.command
```

脚本把应用部署到 `~/Library/Application Support/TalkingHeadStudio`，生成 `~/Applications/口播导演工作台.app`，可在 Finder 中打开。需要语音跟读时，先在系统设置和浏览器中允许麦克风访问，再试读一句。正式签名并公证的 DMG 属于后续发布产物。

### 项目数据与源码直接运行

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

这组 PowerShell 命令适用于从源码目录直接运行。macOS 可用 `python3.12 -m venv .venv` 和 `.venv/bin/python` 执行相同 Python 脚本，也可在准备好依赖后用 `/bin/bash ./launch_macos.command` 打开源码版。初次安装需要联网。启动后打开 [本机工作台](http://127.0.0.1:8765)，两个平台默认项目目录都是 `Documents/TalkingHeadStudio`。

安装和启动都支持指定 `--data` 与 `--port`。同一数据目录会复用已运行的实例；端口被其他服务使用时会提示换端口。关闭浏览器后服务仍在运行，可用 `scripts/launch.py --data <项目目录> --stop` 结束。存在未完成的任务时，先等任务结束。

```powershell
.\.venv\Scripts\python.exe scripts/launch.py --data "D:\TalkingHeadStudio" --port 8767
```

安装后首次启用可选模型时，使用安装器输出的「应用 Python」路径运行表中的命令。已有 Codex 安装可以用 `scripts/install.py` 更新 Skill，并保留旧代码备份。安装独立工作台时可指定原项目目录，先停止正在使用它的旧实例。

### 按需启用

| 功能 | 如何启用 |
| --- | --- |
| 录音转写与自动字幕 | 运行 `.\.venv\Scripts\python.exe scripts/setup.py --speech` 安装 Whisper。在工作台转写时选择模型，并允许首次下载。已有 SRT 也可直接导入。 |
| 麦克风跟读 | 运行 `.\.venv\Scripts\python.exe scripts/setup_speech.py`，约下载 190 MiB 中文/英文流式模型。自定义了项目目录时，给这条命令传入相同的 `--data`。安装好后可本地识别。 |
| AI 润稿与语义分页 | 默认提交 Codex 待办，由 Agent 领取。也可在首页配置自己的 Chat Completions 地址、模型和密钥。手动编辑和基础规则排页可以直接使用。 |
| GIF 工厂轻动效 | 随仓库提供所需导出器。第三阶段导入透明 PNG，再生成 GIF。 |
| HTML Creator Studio | 授权嵌入文档提取与逐帧动画模块，无需另行安装。安装了 `pdftotext` 时使用 HTML Creator Studio 的 PDF 路径，否则使用内置 pypdf 提取。 |
| 剪映草稿 · 实验 | 运行 `.\.venv\Scripts\python.exe -m pip install pyJianYingDraft==0.3.1`。可生成草稿及素材 ZIP，目标剪映版本的打开、轨道与效果兼容性仍需验证。 |

Whisper 用于录制后的转写。提词器的实时跟读使用另一套本地模型，可以分别安装。

## 使用步骤

首页可以选现有稿件、AI 润稿或新建项目。已经录好的人可以点「从视频开始」，直接进入第二步。项目会记住上次停留的步骤。

### 1. 写稿与录制

导入已有稿件后可点「用现稿分页」，也可以等 AI 提供润稿或分页建议。在每页的「画面备注」写下将来要插入的演示、贴纸或动画。需要精确安排时，展开底部时间线。

点击「打开提词器」，用翻页或定速滚动配合外部相机录制。需要跟读时，可以先点「测试麦克风」，再在提词器中开启语音跟随。长稿可用全屏或「下一屏」继续读。

### 2. 整理视频

导入录制后，按实际情况选择「查找长停顿」或「已经剪好，直接用这版」。查找后可勾选要保留的片段，生成预览并确认。只导入一段录音时，可以先识别文字，再用来写稿。

### 3. 字幕与导出

可以「识别视频里的说话」，也可以导入对应这条视频的字幕文件。生成字幕后，点击「检查字幕」改字。素材、位置、时长和音量等操作可在展开后的时间线里调整。只想先看画面也可以选「暂不加字幕，去预览」。

点击「预览与导出」，直接生成一小段预览。需要指定位置时再展开「挑选要预览的片段」。看完确认，工作台会导出完整视频，也可以从「下载」页找到视频。

继续修改时，重新生成与当前时间线对应的样片。点击顶部「打包工程」可导出稿件、字幕、轨道和素材。跨电脑继续剪辑时，勾选「同时打包当前原片和已有粗剪文件」。使用轻量包时，请在目标工作台重新关联原片。

## 与 Agent 协作

本仓库根目录包含 [主 Skill](SKILL.md)。你可以直接使用浏览器工作台，也可以把整个仓库作为本地 Skill 安装到 Codex，并保持本机工作台运行。

### 把项目交给 Codex 或 WorkBuddy

1. 在项目上方点「交给 AI」，选 Codex 或 WorkBuddy，写下要处理的事，存为待办。
2. 点「复制任务卡」，粘贴到要继续的原对话。能访问本机工作台的 Agent 可以领取、读取任务当时的稿件和字幕，再把文字建议写回来。工具连不上时，可直接在原对话继续，回来点「粘贴 AI 的结果」保存。
3. 回首页的「AI 待办」查看结果。建议供你校对并复制使用。项目在这期间有改动时会提示先对照当前版本。

Codex 用户还可点「连接 Codex 原对话」，把连接指令粘贴到项目原来的 Codex 对话。核验成功后可点「继续原对话」，把任务排入该会话。排队后可打开原对话查看，等 Agent 实际领取才显示「AI 已领取」。WorkBuddy 可在原对话粘贴任务卡。只有工作台本机可访问的项目内容才会交给 Agent 工具。

### 可选的本机工具连接

任务卡包含可供 Agent 执行的终端命令。也可以将 `scripts/agent_mcp.py` 配置为 stdio MCP，命令使用工作台的 Python，参数如下。Codex 选 `codex`，WorkBuddy 选 `workbuddy`。使用自定义端口时替换地址。 [WorkBuddy MCP 配置](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/MCP-Guide)

```text
/绝对路径/scripts/agent_mcp.py --agent workbuddy --url http://127.0.0.1:8765
```

稿件编辑器中原有的润稿和分页建议也可继续使用。提交这类待办后，可在 Codex 聊天内让它处理，再回到稿件编辑器确认采用。

```powershell
.\.venv\Scripts\python.exe scripts/studio.py status
.\.venv\Scripts\python.exe scripts/studio.py agent-list --agent codex
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

按「预览与导出」里当时的提示准备视频或补素材。生成预览并在同一窗口确认后，即可导出完整视频。改过字幕、片段或画面后，先生成一段新的预览。

### 我的原片会被覆盖或上传吗？

工作台生成新的粗剪和成片文件，原素材保留在本机。使用外部模型服务进行润稿或分页时，提交的稿件会发送至自行配置的服务地址。使用其他 Agent 的在线工具时，按需明确选择要交接的资料。

### 已经有精剪软件，能继续在那里编辑吗？

可以带走原片、字幕和工程所用素材。剪映目前提供实验性草稿导出。ChatCut 接入和自动继续其他 Agent 对话属于后续集成方向。

### macOS 已经通过实机验收了吗？

当前已提供安装与启动实现。Apple 芯片 Mac 上的实际依赖安装、麦克风跟读、三阶段导出和工程互迁仍待现场测试。

### 重装后找不到项目怎么办？

确认启动使用原来的数据目录。默认是 `Documents/TalkingHeadStudio`。如果以前使用了 `--data`，继续传入同一目录。工程包中的外部原片可通过设置中的「重新定位原片」恢复关联。

## 第三方组件

- [GIF 工厂](https://github.com/WoYun520/gif-factory) 的轻动效导出器，保留 [MIT 许可](vendor/gif-factory/LICENSE)。
- [Vditor](https://github.com/Vanessa219/vditor) 的本地静态资源，保留 [MIT 许可](assets/workbench/vendor/vditor/LICENSE) 及其分发文件中的第三方声明。
- HTML Creator Studio 核心模块经维护者授权嵌入，来源和版本见 [NOTICE](vendor/html-creator-studio-core/NOTICE)。
- 字幕、GIF、流程卡片和提词器使用随工程分发的 Noto Sans CJK SC。字体来源见 [NOTICE](assets/workbench/fonts/NOTICE)，许可见 [OFL 1.1](assets/workbench/fonts/OFL.txt)。分享离线提词时请使用完整 ZIP。
- Whisper 模型、sherpa-onnx 模型、FFmpeg 和 Chromium 按需从各自渠道安装。

第三方组件的许可适用于对应文件。主项目的源码公开可查看，主项目许可由维护者另行声明。
