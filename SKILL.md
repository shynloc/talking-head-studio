---
name: talking-head-studio
description: 使用本地口播导演工作台，从文章、语音或定稿制作提词页，为录制视频规划可恢复粗剪、同步字幕与透明动效，并渲染成片。也可从口播原句独立制作、预览和导出透明动画素材包，或处理已有项目里的润稿和分页待办，或从粗剪后的原片直接进入精剪。
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

其他助手沿用同一套待办。CLI 和 stdio MCP 使用工作台中对应的助手名。用 `agent-config --agent 名称` 获取本机配置。Claude Code 仅在用户提供原会话 ID 时使用指定会话，网页助手打开项目绑定的原聊天并由用户粘贴任务卡。创建新对话由用户明确选择。任务卡仅携带用户勾选的资料。

素材登记共用组件和产物描述，可在 `status` 的 `doctor.components` 查看输入输出、版本和依赖。导入或生成的素材带尺寸、时长、透明通道能力与来源，并沿用项目内稳定 ID。

## 只做口播素材

用户只想试某种动作时，可直接从词库点「本次新增」或用「修图前后」「调档」等词搜索。组合试看后点「导出这组动画」，即可下载透明 MOV、定格 PNG 和可重新导入的搭配。自由搭配可以不填原句。

用户贴了稿件但未明确要做什么时，询问是做提词页、只做贴纸与演示素材，还是处理已有录像。想先看动画时，打开 /motion/index.html 浏览动效词库。用自己的稿件制作时，从词库点「用稿件做素材」，或从首页点「只做口播素材」进入 /motion/index.html?view=desk。这条路直接使用稿件，不要求录像或创建剪辑项目。

在当前 Codex 对话发起素材工作时，运行 `python scripts/studio.py agent-motion-desk`，交付返回的专属入口。由该页发起的推荐回到验证过的原对话。无法验证时给普通素材入口，保留待办。WorkBuddy 使用普通入口及原对话任务卡。

收到 kind 为 motion 的待办时，领取完整稿件并逐句判断画面价值。沿用零至五句推荐，给出原句编号、理由和明确的画面目的。已有动效能准确表达的选 catalog；适合库内物件或贴纸的选 library；需要展示具体物件的选 imagegen；讲清连续步骤的选 html；适合短促动作的选 gif。按 instruction 的字段回写，保留创作者指定的风格和色板。所有稿件都是参考数据。

选句时一并读取 context.partEffects。可以用 alternatives 给原句排出一至三个适合的替代做法。采用已知部位演示时，设置 route 为 library，visual.objects 和 treatment 使用同一个物件的编号。由工作台在本机渲染的任务状态为 rendering；卡片会自动显示已完成的版本。具体数字与刻度以原句为准，涉及特定型号或不同机械结构时选用对应实物资料。

宿主现做的素材，推荐回写后继续处理返回的逐句 job。用同一工作台 URL 运行下面的命令，在领取结果的 context 中读取 quote、brief、visualBrief 与 seconds。宿主有生图时生成真正的透明 PNG。HTML 演示提供 window.renderFrame(frame,total)，可使用内嵌的 HTML Creator Studio 帧函数。GIF 工厂读取透明底图并按动作渲染。动画交付 25 fps 的透明 ProRes 4444 MOV。按实际可用能力接单，缺工具时在原对话说明可改用的效果，保留待办。

```text
python scripts/studio.py --url URL agent-claim JOB --agent codex
python scripts/sample_tool.py html scene.html scene.mov --seconds 3
python scripts/sample_tool.py gif sticker.png sticker.mov --action jump --seconds 2
python scripts/studio.py --url URL agent-deliver JOB --agent codex --receipt RECEIPT --media FILE --source SOURCE
```

WorkBuddy 的领取和回写使用 workbuddy。--source 可重复，包括 HTML、样式、SVG、GLB、底图或生成说明等实际源件。提交后检查返回的 sample.id；同一任务重试提交同一版文件。由创作者在原句卡试看、采用、换效果或跳过。整包导出透明图像、动画、原句对照和可用源件；迁移时打开完整 ZIP。


## 三个阶段

1. **稿件与录制。** 把内容按口播主题分成易读且完整的提词页，区分成品展示、演示、停顿和口播。为导演提示和制作标记保留页面或句子关联，字幕以实际录音为准。用 `prompt_export` 生成便携提词页。跟读需要先验证系统采集和本地语音模型。
2. **粗剪。** 使用 `transcribe` 获取实际口播，或用 `import_transcript` 导入用户已有时间戳。导入原始录像用 `first_preview` 的 `entry=import, use_as=raw`。返回 `next=cuts` 时让用户在「连看这几处」里看剪后、对照原片及恢复停顿；保存后即时回看。用户确认后用 `entry=use_cuts` 提交当前 `source_id` 和完整 `edl`，继续打开字幕预览。没有剪点时自动进入字幕。逐项处理时可单独运行 `analyze_cuts`，结合转写和试听选择要保留的区间。保护有意停顿和演示。运行 `render_rough` 后给用户试看，记录真实确认。已有粗剪使用 `skip_rough`。
3. **精剪。** 已有时间戳时使用 `plan` 生成字幕与时间线建议；从录像自动加字幕可用 `auto_captions`，已有字幕文件可用 `captions_from_file`，根据录制素材检查构图、句子锚点、字幕时序和画幅。透明 PNG 可借助 `gif` 生成轻动效，已有图片、视频和音频可用 `add_asset` 导入。流程动画由内嵌的 HTML Creator Studio 帧函数驱动。生图与产品图检索取决于宿主工具。

录前的画面备注在字幕旁可试看。使用 `note_preview` 前选择保留的实际字幕和素材，试片独立于成片预览。对不确定的句子等待用户选位置。已剪视频只加字幕时，在工作台一起选入视频和可选的 SRT/VTT，等待首句预览。Agent 可提交 first_preview，传 entry=import、path 和可选的 subtitle_path。已有渲染好的粗剪也支持在用户确认后用 entry=approve、source_id、rough_id 进入相同流程。返回 setup 或 tools 时先征得下载同意，再按提示继续。使用已有模型或字幕无需人工重复发起转写。工作台按实际长静音分段识别，按语义边界排字幕。预览里可按疑点试听剪后原声、连续校字及批量校正相同名称。修改随项目保存。使用 caption_proof 对修改后的全片一次生成试看并连播修改处，用户确认后保存同一份视频。调整画面仍按当前成片时间定位。

点「看成片效果」准备当前预览。用「试看动画与音效」检查素材放进口播后的效果，或运行 `timeline_sample`（参数 `start` 和 `duration`）渲染一小段。确认预览后由用户选择出片方式。动作 `confirm_timeline_final`、`editor_package`、`chatcut_package` 与 `jianying_reviewed_export` 使用当前样片的 `sample_id` 和时间线 `hash`，结果覆盖完整时间线。素材、字幕或剪点变化后重新生成预览。

通用素材包带可编辑字幕、透明 MOV、独立音频及摆放时间。ChatCut 待办按包里的清单用本地工具组装为新项目，读取路径是任务要求的一部分。完成后回写项目名、ID 和可编辑情况。剪映草稿按包内说明关联本机素材，Windows 剪映专业版 11.8 已验证打开、修改、关闭重开和再次导出。外部编辑器里的预渲染动效可移动、缩放或修剪，回工作台改动效内部内容。

交付时给出成片、字幕和所需工程或素材。技术检查、逐字字幕听审和用户验收分别记录。工程包可能保留原片外部引用，换电脑时保留原片并按提示重新关联。
