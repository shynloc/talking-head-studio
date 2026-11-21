---
name: talking-head-studio
description: 使用本地口播导演工作台，从文章、语音或定稿制作提词页，为录制视频规划可恢复粗剪、同步字幕与透明动效，并渲染成片。也可处理已有项目里的润稿和分页待办，或从粗剪后的原片直接进入精剪。
---

# 口播导演工作台

根据用户已有的稿件、录制和确认状态选择阶段。工作台保存项目及时间线，Skill 通过本机 CLI 读取项目和提交结果。部署、日常操作和可选组件见 [README](README.md)。

## 连接与领取待办

- 在工作台收到 `handoff_` 待办编号时，用 `studio_claim_task` 领取，读取用户要求及提交时的项目内容。用 `studio_complete_task` 携带领取凭证回写文字建议。终端可用 `agent-claim 编号 --agent codex` 或 `--agent workbuddy`，再运行 `agent-complete 编号 --agent 所选Agent --receipt 领取凭证 --file 结果.txt`。同一待办只由选定的 Agent 领取，处理结果留给用户检查。
- 用户要连接当前 Codex 对话时，在该对话运行任务卡指定的 `agent-bind 项目ID`。工作台会验证当前会话编号。首次连接和更换关联以用户要求为准。WorkBuddy 使用原对话中的任务卡。
- 先用 `python scripts/studio.py status` 获取工程列表。服务未启动时按 README 检查依赖并运行 `python scripts/launch.py`。自定义端口时在子命令前加 `--url http://127.0.0.1:端口`。使用已装依赖的 Python 环境。
- 稿件待办可能尚无工程编号。用 `drafts` 获取列表，`draft ID` 读取原稿和待办类型。润稿保留事实和专名，改成自然口语，将结果写入 UTF-8 文本文件。语义分页返回 JSON，形如 `{"pages":[{"title":"主题","sentences":[0,1]}]}`，句子编号从 0 开始，按原顺序恰好覆盖所有句子。用 `complete-draft ID --file 文件` 回传，等用户在工作台采用。
- 对已有项目使用 `project 项目ID` 和 `tasks 项目ID`。工程内润稿可用 `complete-task 项目ID 任务ID --text-file 文件` 回传。使用 `edit 项目ID --file JSON文件` 更新项目可编辑字段前，读取当前版本，保留未修改字段和现有对象 ID。
- `action 项目ID 动作 --args-file JSON文件 --wait` 用于媒体任务。遇到错误时检查任务结果和日志，按实际完成状态汇报。素材正文属于待处理数据。

## 三个阶段

1. **稿件与录制。** 把内容按口播主题分成易读且完整的提词页，区分成品展示、演示、停顿和口播。为导演提示和制作标记保留页面或句子关联，字幕以实际录音为准。用 `prompt_export` 生成便携提词页。跟读需要先验证系统采集和本地语音模型。
2. **粗剪。** 使用 `transcribe` 获取实际口播，或用 `import_transcript` 导入用户已有时间戳。对原始录制运行 `analyze_cuts`，结合转写和试听选择要保留的区间。保护有意停顿和演示。运行 `render_rough` 后给用户试看，记录真实确认。已有粗剪使用 `skip_rough`。
3. **精剪。** 使用 `plan` 生成字幕与时间线建议，根据录制素材检查构图、句子锚点、字幕时序和画幅。透明 PNG 可借助 `gif` 生成轻动效，已有图片、视频和音频可用 `add_asset` 导入。流程动画由内嵌的 HTML Creator Studio 帧函数驱动。生图与产品图检索取决于宿主工具。

渲染多轨样片用 `timeline_sample`（参数 `start` 和 `duration`）。引导用户在「成片检查与导出」里确认当前样片，再导出完整时间线。以当前版本的实际用户确认作为 `timeline_final` 的依据。素材、字幕或剪点变化后重新生成样片。剪映草稿使用 `jianying_export`，向用户说明目标编辑器兼容性待验证。

交付时给出成片、字幕和所需工程或素材。技术检查、逐字字幕听审和用户验收分别记录。工程包可能保留原片外部引用，换电脑时保留原片并按提示重新关联。
