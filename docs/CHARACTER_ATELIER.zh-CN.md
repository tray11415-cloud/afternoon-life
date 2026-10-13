# 统一人物工坊 · v0.24

[繁體中文](CHARACTER_ATELIER.zh-TW.md) · **简体中文** · [日本語](CHARACTER_ATELIER.ja.md) · [English](CHARACTER_ATELIER.en.md)

一份表单包含名字、成人年龄／性别、角色 prompt、可选 LoRA、触发词、Seed、外观、个性、目标、可选背景、手动 AI 草拟与人物卡。保存会验证并确定本人设置，再以同一份身份与穿着快照排入立绘差分／行走图和一张 CG。一致的完成素材会自动套用。部件验证与历史支援还原，这个明确保存流程不需另外按套用。

可只用 prompt 生成。`<lora:filename:0.8>` 只解析所选安装内唯一同名资源，第一个为人物、第二个为衣服，最多两个。整理后的身份存於人物设置与 SD 绑定。保留本机 SD、原生模板、其他人物与人类玩家身分，不猜模型、不下载权重。

原生 SD 是独立的嵌入界面，不撷取未保存表单。汇入原始生成 PNG／PNG Info／完整 API payload，保存模板后选用途。PNG 只能恢复写入的资讯；未记录扩充需完整 payload。统一人物流程在副本中替换 WebUI ADetailer 正向身份与表情，保留侦测器、遮罩、负向与其他参数，不改保存模板或原生视窗。含 LoRA 节点的原生 ComfyUI 仍需明确选 LoRA；纯 prompt 可用相容内建流程。品质取决於模型与模板。

## 受保护的本机 API

POST `/api/art` 需 `X-Play-Token`、既有 Host／Origin 检查及 `operation: "atelier"`。

- `params.command: "state"`：SD 设置、各人物当前／模板指纹及最新生成包。
- `save_character`：精确栏位为 `command, actor, mode, profile, before, sd, binding_before, scene, description`。沿用成人人物 schema；`before` 与 `binding_before` 拒绝其他页造成的过期编辑。保存当前人物保留事件前缀、钱包、物品、关系及他人。模板只更新未来人物，不生成旧世界素材。
- `build_saved_character`：`command, actor`；建立新存档后以已保存 prompt 排入美术，不写人物事件。
- `retry_character`／`cancel_character`：`command, actor, id`；ID 须属於本人当前生成包。重试保留完成结果；满伫列会等候并自动恢复。
- 旧的 `binding`、`generate`、`apply`、`restore` 保留。restore 取消本人待自动套用工作并保留文件。

流程存於忽略的 `work/character-pipelines.json`。每包持有两个任务与已套用阶段。背景协调核对人物／绑定／衣服指纹；新保存取代旧计画，人物或衣服改变则失效，不悄悄套用。取消只影响本人任务；重启中断工作可重试。未变美术配方可重用结果，包括单纯改名。

玩家由人操作。背景是私有作者文字，不能创造过去事件。选 CG 不移动人物、不生成经历记忆。美术、保存、读档不重置 API 用量；人物美术流程不呼叫付费 LLM。

## 保留的人物工具

成人年龄18–120，唯一名字最多32字，口调／个性500、目标100、背景2000、prompt1000字。`look` 包含八发型、发／肌／眼色、柔和／椭圆／角形脸、身高150–205、纤细／一般／运动／丰满体型与初始衣色。这是可选原生像素控制与 SD 描述，不是3D造型；购买服装用实际衣柜配方。

AI 草拟手动且限本人，沿用用量上限，离线例子有标示。卡片为 UTF-8 `lifebox.character.v1` JSON，界面上限64KiB，只含设置，不含图、模型、金钥、世界记忆。旧预览／准备／套用与部件还原接口保留。外观图层保留 LPC 署名，可用 `tools/build_look_layers.py` 与署名来源包重建。

历史21项流程检查涵盖改名、状态保留、纯prompt、本机标签、人物隔离、过期编辑、自动套用、伫列、重试、取消、新游戏模板、重用、代替素材复原。后续模型／画风版增至30项。SD／原生／界面检查采隔离或模拟服务；百科图片为明示 LPC 模拟素材，不主张新SD品质。

[玩法百科](PLAYER_GUIDE.zh-CN.md) · [素材授权](../ASSET_LICENSES.md)。界面分类参考 [AI＊少女手册](https://aisteam.illusion.rip/manual/readme_jp.html)，程式与界面原创，无同作素材。

## 每人的底模与画风

既有九个必需 SD 绑定栏位保留，另接受 `checkpoint`、`style_lora`、`style_weight`（0–1.5，预设0.8）、`style_trigger`（SFW，最多1600字）。ID 须是目前安装内可选本机资源。空底模沿用全局，空画风停用画风载入。空覆写在验证时移除以保持旧指纹／快取；保存别人不改此人选择。统一与进阶编辑器共用绑定。

底模、人物／衣服／画风 LoRA、权重与触发词进入每份立绘／步行／CG配方、快取与素材身份签章。配方改变会产生新素材。WebUI／内建ComfyUI即使没有身份LoRA也套用已选LoRA。WebUI按要求覆写并恢复底模。原生ComfyUI需 `style_lora/style_weight` 绑定；缺少时在排程前阻挡。存在但未使用的衣服／画风权重归零，保留节点结构。原工作流与未保存表单不改。

模型／画风版新增九项（流程共30项）：四用途独立配方、持久化、旧快取一致、变更失效、无效资源／权重不改状态、架构不合、模拟WebUI要求、ComfyUI对映／预检、清空画风权重。该版未生真SD图或付费请求。

## 多画风与精修

`style_loras` 是第一画风后最多七笔有序 `{lora, weight, trigger, enabled}`。权重0–1.5，启用ID不可重复，停用笔保留编辑但不送渲染。原生ComfyUI需 `style_lora_2/style_weight_2` 至 `_8`；未用对映归零。内建ComfyUI与WebUI套用整个选定堆叠。

`render_options` 包含 refiner／hires／adetailer，各有 `mode` inherit/on/off 与 `targets` portrait/pixel/cg。预设值与空阵列标准化移除以保留旧快取。Refiner选本机底模与切换0.01–0.99；Hires选本机扩大器、倍率1–2、步数1–80、denoise0–1、CFG1–20、采样器。ADetailer最多四段且受实际script-info容量限制，可分别设侦测器、信心、遮罩、采样器、prompt、身份追随与验证后追加参数。沿用与明确关闭有区别，不改原模板／视窗。

只有 `command` 的 `refresh_sd_capabilities` 重新读取能力，不改保存设置。WebUI读侦测器、script容量、采样器、本机扩大器与实际OpenAPI栏位。不支援／不适合的选项排程前阻挡；神经扩大器呼叫extras前再次确认本机权重，不下载。

文字生成用原生Hires.fix；WebUI参考图img2img没有原生Hires阶段，先基本解析度身份／姿势生成，再用已存扩大器缩放，最后第二次img2img依倍率／Steps／denoise／CFG重绘。ADetailer只在最后，不执行两次；未选修补段明确停用，避免插件预设补入。步行用途需勾选，最大2048px；两次副本保留进阶参数、身份与ControlNet参考。

精修控制属WebUI／Forge。ComfyUI要求明确开／关时会阻挡并解释，需沿用原生品质流程，不能悄悄忽略。多LoRA两种后端皆支援。

v0.24新增16项隔离要求检查：排序、用途、沿用、关闭、实际栏位、第二次生成、最后ADetailer、不写世界的验证、模型／插件／容量／尺寸、持久化、原生绑定。匿名本机SFW小测试取得384px PNG，使用两画风、同底模Refiner、ADetailer与两种Hires路径，只确认接收／输出，不证明脸部侦测、另一Refiner品质或长期身份一致。实SD结果保持私有。
