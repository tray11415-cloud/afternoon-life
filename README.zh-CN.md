# 午后共居 · Afternoon Life

[繁體中文](README.zh-TW.md) · **简体中文** · [日本語](README.ja.md) · [English](README.md)

首次启动默认为 **English**；已有存档中的语言选择会保留。

俯视角像素生活沙箱：十位成年共居角色、一位由你控制的玩家，以及持续运作的小镇。每位 AI 只取得自己的观察、目标与记忆；可以共用模型服务，但不共用全知人格。

**目前是可玩的 alpha：v0.24.0。** 这是生活模拟实验，尚非完成的商业 galgame，也尚未验证成熟的长期故事品质。露骨内容入口关闭。

[![简体中文操作导览](docs/media/guide.zh-CN.png)](https://github.com/tray11415-cloud/afternoon-life/releases/download/v0.20.0/afternoon-life-guide.zh-CN.mp4)

[简体解说导览](https://github.com/tray11415-cloud/afternoon-life/releases/download/v0.20.0/afternoon-life-guide.zh-CN.mp4) · [下载版本](https://github.com/tray11415-cloud/afternoon-life/releases/tag/v0.24.0)

简体影片展示 v0.20 开始菜单、设置、人物工坊和实际游戏操作；使用独立离线世界、合成配音与字幕，没有现场付费模型请求或 SD 生图。[其他语言及拍摄说明](docs/WALKTHROUGH.zh-CN.md)。

## 多画风 LoRA 与精修设置（v0.24）

人物工坊支持八个画风槽，各自保存权重、触发词、开关；额外画风可调整顺序。**Refiner／ADetailer／Hires.fix** 放在可折叠的进阶区，跟同一份人物配方保存。每项功能可“沿用原生模板”“使用此人物设置”或“明确关闭”，并各选立绘、行走图、CG 用途。

WebUI／Forge 可选 Refiner 模型与切换比例；ADetailer 最多四个修补顺序（依本机实际容量），支持检测器、正负提示、遮罩、采样器及其他参数 JSON。Hires.fix 的文字生图用原生流程，图生图差分与 CG 会放大后二次重绘。放大器必须已在本机，输出上限 2048px。ComfyUI 支持多 LoRA，原生模板需编号绑定；三项 WebUI 专用面板须沿用 ComfyUI 原生工作流。

![精修与高分辨率设置](prototype/web/assets/guide-v24-refiner.png)

截图是明示模拟 SD 的隔离世界，使用已署名 LPC 素材。新增16项请求测试通过；本机 reForge 另成功产出两张小尺寸匿名成年 SFW 图，使用双画风、ADetailer、同一底模作 Refiner 及两种高分辨率流程。此实测确认 API 接受设置与返回 PNG，未评估脸部检测成功或长期身份质量。真实本机 SD 图片、模型清单及私人存档不公开。

## 角色底模与画风 LoRA（v0.23）

人物工坊的角色 prompt 下方新增 **此角色底模**、**画风 LoRA**、**权重（0–1.5）**及**画风触发词**。每人独立保存；选择“沿用全局底模”即可保持原本默认。人物与服装 LoRA 仍分开。按 **保存并完成这位人物**，立绘、行走图与 CG 都使用此配方，旧文件保留。

选单列出已连接 SD 安装内的本机可选资源。已知底模与 LoRA 架构不符会显示原因并阻挡生成；未知训练信息需自行确认。WebUI／Forge 生图后恢复原服务底模；ComfyUI 内置模板依序叠加三类 LoRA。原生 ComfyUI 模板须把 `style_lora`、`style_weight` 绑定到画风节点，或改回该用途的内置模板。

![角色画风设置](prototype/web/assets/guide-v23-character-style.png)

图为隔离界面测试；成果使用已署名 LPC 模拟素材，并非本次 SD 实际出图。

## 统一人物工坊（v0.22）

选人物、输入自定义名字与一份角色 prompt，按 **保存并完成这位人物**。一次保存人物设置，自动排程立绘差分、四方向行走图与一张 CG；相符的完成素材自动应用，失败项目可重试。原美术、角色记忆、物品与其他人物保留。

发型、体形、配色、个性、目标、可选背景、AI 草拟与人物卡都在同一个编辑器。LoRA 可选；支持明确的本地 `<lora:文件名:0.8>` 标签，不猜绑定。高级／原生 SD 配置保留；新游戏模板在建立新存档后制作素材。旧影片展示较早版本。

[附截图的玩法百科（繁中，10章）](docs/PLAYER_GUIDE.zh-CN.md) · [人物流程与接口](docs/CHARACTER_ATELIER.zh-CN.md)。游戏内百科：`http://127.0.0.1:8765/guide.html`。

## 开始玩

安装 **Python 3.12 以上**与 **Pillow**。离线试玩不需要游戏引擎、Node.js、API 金钥或 SD 模型。

```powershell
git clone https://github.com/tray11415-cloud/afternoon-life.git
cd afternoon-life
python -m pip install -r prototype/requirements.txt
cd prototype
python -m lifebox.play --demo
```

打开 **http://127.0.0.1:8765/**。Windows 安装依赖后也能双击 `prototype/play-demo.cmd`，此启动器使用 **8766**，与正式游戏分开。`play.cmd` 在有金钥时使用 xAI，没有则使用离线示范；两者存档分开。用命令开第二个游戏时，请指定另一个 `--port`。

**WASD／方向键**移动、点地面寻路、靠近人物或物件按 **E** 互动。走到门口即可进屋；场所按钮会安排实际路线，不会瞬移。

「游戏设置」可选 **繁体中文／简体中文／日本语／English**，保存后影响界面与新生成的 AI 台词。人物名字、自订背景、历史台词、来源文章和原生 SD 画面保留原文。TTS 声线与朗读语言另行选择。

离线示范有明确标示，使用本机日程及固定示范台词，**没有呼叫 LLM，也没有付费模型请求**。

## 开始选单与人物工坊（v0.20）

开始画面提供继续、新游戏、人物工坊、游戏设置及手动读档。「继续」保留最新位置；「新游戏」先编辑模板，勾选建立存档后才开始，原存档会封存，可在工坊恢复。

人物工坊按基本资料、脸与身形、发型、服装、个性、背景及 AI／人物卡分类。男主与十位角色各自编辑；原人物未启用自订外观时沿用原素材。启用后可调整八种发型、发色、肤色、初始衣裤色和简化身形，预览四方向与行走。脸型与眼色供 SD 身份描述使用，没有 3D 捏脸；身高在像素图中是有界的轮廓缩放。已购买衣服继续使用自己的配色。

目前人物先预览再套用；新游戏模板另存。AI 草拟只在手动点击时处理选定人物，使用既有行动模型与共用帐本上限，不传整个世界。离线模式提供明示本机范例。JSON 人物卡只含设置，不含世界记忆、金钥、LoRA 或图片；汇入后仍需预览套用。SD 可由服装分类进入，需另外逐人绑定模型。

游戏设置分为画面、操作、声音、AI、语言与存档。可保存视野缩放、人物名称、小地图、较大文字、减少动画及设置时暂停。主选单一律暂停这个游戏页的心跳；多开另一个页面仍可推进同一个世界。TTS 声线与朗读语言独立选择。[人物卡与预览接口](docs/CHARACTER_ATELIER.zh-CN.md)。

## 可以做什麽

- 探索 **22 张地图、10 个公共场所**：图书馆、咖啡厅、动物园、美术馆、电影院、餐厅、公园、市集、衣服店与泳池。
- 发出共同活动邀约。每人自己回覆、步行集合、分别付款，只记得实际参与的内容。一般 NPC 有独立日程与固定台词。
- 打工、依配方创作、寄售作品、买消耗品与换装。金钱与物品由完成的世界事件产生，不能只靠台词宣称取得。
- 客制玩家和十位共居角色的名字、成年年龄、性别、性格、目标、可选背景与外观描述。现有人物先预览再套用，保留进度，可从工坊历史还原；新游戏模板另存。
- 在「部件工坊」更换图片、场景几何、互动、商品、日程、经济规则和模型／工具接口。固定 ID、相容性验证、预览及还原保护原存档。
- 连接本机 **WebUI／Forge／reForge／ComfyUI**，用角色 LoRA 生成立绘、表情差分、四方向像素图及一般 CG。可盘点资源、汇入完整原生模板，确认结果后按人物与穿着套用；不附模型权重。
- 选择 Windows／浏览器本机声线或相容本机 TTS。只朗读玩家实际听到的台词，读档不重播全部历史。

## 真实 AI 与本机服务

可直接在 **游戏设置 → AI 与生成 → API 密钥与 SD 路径设置** 填入 xAI 密钥、选择模型及挂载本机 SD。保存立即生效，测试连接另有按钮；详见[连接设置说明](docs/CONNECTION_SETTINGS.zh-CN.md)。以下环境变量方式仍可使用。

在程序环境设置 `XAI_API_KEY`，不加 `--demo` 启动：

```powershell
cd prototype
python -m lifebox.play
```

不要把金钥写进原始码。也支援既有的 Windows DPAPI 金钥格式。预设对话用 **Grok 4.3**、行动决策用 **grok-build-0.1**，仍取决於帐号与服务可用性。帐本预设最多 50 次／估计 US$0.05；读档与重启不重置。金额按 adapter 的价格表估算，不代表帐单保证。

固定日程不呼叫模型；自主 AI 公共会话预设关闭。对话、行动、记忆与替换工具可分别选 adapter，不会因此换掉人格或重置记忆。

SD 是可选功能。启动本机服务，在「生图设置」选安装资料夹，再逐人绑定 LoRA。泳装生成另需泳装 LoRA。找到权重不代表服务与工作流相容；神经去背也需现有相容环境及本机权重，不会自动下载。

本机工具契约为 `lifebox.decide.v1`、`lifebox.interact.v1`、`lifebox.replace.v1`。`GET /api/components/schema` 提供六种替换函数定义；`tools/components_cli.py` 可检查、准备、套用、还原及汇出。API 需要游戏 token，拒绝跨来源写入，不执行汇入的 Python／JavaScript。

## 目前限制

- 长期个性一致性、开放故事品质与大规模效能尚未验证；原生日程、目标与创作仍使用小型规则及配方。
- 预设记忆是本机词汇／事件检索；语意嵌入需要真正的服务。
- 场所目录是来源快照，不是即时库存或保证当期展览。电影理解依剧情／心得文字，没有宣称以视觉看完整部电影。
- 生图的人物、服装、表情与步伐仍需预览。ControlNet 和参考图能改善一致性，不能保证；部分 SD 扩充或模型架构可能不相容。
- 替换目前维持原 32px 格网、场景尺寸和既有 ID；扩张世界格式需另做迁移。
- 主要验证平台为 Windows；Windows 语音和桌面 SD 启动工具限 Windows，不附已训练 TTS 模型。

## 开发与验证

```powershell
cd prototype
python -m unittest discover -s tests
cd ..
python tools/test_atelier.py
python tools/test_release.py
python tools/test_character_customization.py
python tools/test_components.py ComponentsTests
```

测试使用隔离世界、假模型或本机测试服务，不需要真实金钥。详细检查见 [docs/RELEASE_REVIEW.md](docs/RELEASE_REVIEW.zh-CN.md)。

`prototype/lifebox` 管理世界事件、权限、生活规则与接口；`prototype/web` 是 Canvas 界面；`prototype/data` 是目录与素材清单。`tools` 提供建置与验证工具。存档、金钥、生成快取与本机设置都放在不发布的 `work/`。

## 素材与授权

本专案原始程式采 MIT；**美术另有授权**。LPC 人物／场景改作依 CC BY-SA 4.0 分享，完整上游授权选项与署名在 [LPC-CREDITS.txt](prototype/web/assets/LPC-CREDITS.txt) 及 [ASSET_LICENSES.md](ASSET_LICENSES.md)。Kenney 素材保留 CC0 标示。程式授权不涵盖模型权重或外部内容。

对话风格参考 [Lieflat Less AI Tone](https://github.com/larashero3-dotcom/lieflat-less-ai-tone)（MIT）；记忆设计参考 [Spatial Memory Engine](https://github.com/jack66g/spatial-memory-engineagent)（Apache-2.0）。通知保留在 `docs/third-party/`；没有宣称完整整合两个上游系统。
