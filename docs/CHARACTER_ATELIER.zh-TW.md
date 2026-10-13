# 統一人物工坊 · v0.24

**繁體中文** · [简体中文](CHARACTER_ATELIER.zh-CN.md) · [日本語](CHARACTER_ATELIER.ja.md) · [English](CHARACTER_ATELIER.en.md)

一份表單包含名字、成人年齡／性別、角色 prompt、可選 LoRA、觸發詞、Seed、外觀、個性、目標、可選背景、手動 AI 草擬與人物卡。保存會驗證並確定本人設定，再以同一份身份與穿著快照排入立繪差分／行走圖和一張 CG。一致的完成素材會自動套用。部件驗證與歷史支援還原，這個明確保存流程不需另外按套用。

可只用 prompt 生成。`<lora:filename:0.8>` 只解析所選安裝內唯一同名資源，第一個為人物、第二個為衣服，最多兩個。整理後的身份存於人物設定與 SD 綁定。保留本機 SD、原生模板、其他人物與人類玩家身分，不猜模型、不下載權重。

原生 SD 是獨立的嵌入介面，不擷取未保存表單。匯入原始生成 PNG／PNG Info／完整 API payload，保存模板後選用途。PNG 只能恢復寫入的資訊；未記錄擴充需完整 payload。統一人物流程在副本中替換 WebUI ADetailer 正向身份與表情，保留偵測器、遮罩、負向與其他參數，不改保存模板或原生視窗。含 LoRA 節點的原生 ComfyUI 仍需明確選 LoRA；純 prompt 可用相容內建流程。品質取決於模型與模板。

## 受保護的本機 API

POST `/api/art` 需 `X-Play-Token`、既有 Host／Origin 檢查及 `operation: "atelier"`。

- `params.command: "state"`：SD 設定、各人物當前／模板指紋及最新生成包。
- `save_character`：精確欄位為 `command, actor, mode, profile, before, sd, binding_before, scene, description`。沿用成人人物 schema；`before` 與 `binding_before` 拒絕其他頁造成的過期編輯。保存當前人物保留事件前綴、錢包、物品、關係及他人。模板只更新未來人物，不生成舊世界素材。
- `build_saved_character`：`command, actor`；建立新存檔後以已保存 prompt 排入美術，不寫人物事件。
- `retry_character`／`cancel_character`：`command, actor, id`；ID 須屬於本人當前生成包。重試保留完成結果；滿佇列會等候並自動恢復。
- 舊的 `binding`、`generate`、`apply`、`restore` 保留。restore 取消本人待自動套用工作並保留文件。

流程存於忽略的 `work/character-pipelines.json`。每包持有兩個任務與已套用階段。背景協調核對人物／綁定／衣服指紋；新保存取代舊計畫，人物或衣服改變則失效，不悄悄套用。取消只影響本人任務；重啟中斷工作可重試。未變美術配方可重用結果，包括單純改名。

玩家由人操作。背景是私有作者文字，不能創造過去事件。選 CG 不移動人物、不生成經歷記憶。美術、保存、讀檔不重置 API 用量；人物美術流程不呼叫付費 LLM。

## 保留的人物工具

成人年齡18–120，唯一名字最多32字，口調／個性500、目標100、背景2000、prompt1000字。`look` 包含八髮型、髮／肌／眼色、柔和／橢圓／角形臉、身高150–205、纖細／一般／運動／豐滿體型與初始衣色。這是可選原生像素控制與 SD 描述，不是3D造型；購買服裝用實際衣櫃配方。

AI 草擬手動且限本人，沿用用量上限，離線例子有標示。卡片為 UTF-8 `lifebox.character.v1` JSON，介面上限64KiB，只含設定，不含圖、模型、金鑰、世界記憶。舊預覽／準備／套用與部件還原接口保留。外觀圖層保留 LPC 署名，可用 `tools/build_look_layers.py` 與署名來源包重建。

歷史21項流程檢查涵蓋改名、狀態保留、純prompt、本機標籤、人物隔離、過期編輯、自動套用、佇列、重試、取消、新遊戲模板、重用、代替素材復原。後續模型／畫風版增至30項。SD／原生／介面檢查採隔離或模擬服務；百科圖片為明示 LPC 模擬素材，不主張新SD品質。

[玩法百科](PLAYER_GUIDE.zh-TW.md) · [素材授權](../ASSET_LICENSES.md)。介面分類參考 [AI＊少女手冊](https://aisteam.illusion.rip/manual/readme_jp.html)，程式與介面原創，無同作素材。

## 每人的底模與畫風

既有九個必需 SD 綁定欄位保留，另接受 `checkpoint`、`style_lora`、`style_weight`（0–1.5，預設0.8）、`style_trigger`（SFW，最多1600字）。ID 須是目前安裝內可選本機資源。空底模沿用全局，空畫風停用畫風載入。空覆寫在驗證時移除以保持舊指紋／快取；保存別人不改此人選擇。統一與進階編輯器共用綁定。

底模、人物／衣服／畫風 LoRA、權重與觸發詞進入每份立繪／步行／CG配方、快取與素材身份簽章。配方改變會產生新素材。WebUI／內建ComfyUI即使沒有身份LoRA也套用已選LoRA。WebUI按要求覆寫並恢復底模。原生ComfyUI需 `style_lora/style_weight` 綁定；缺少時在排程前阻擋。存在但未使用的衣服／畫風權重歸零，保留節點結構。原工作流與未保存表單不改。

模型／畫風版新增九項（流程共30項）：四用途獨立配方、持久化、舊快取一致、變更失效、無效資源／權重不改狀態、架構不合、模擬WebUI要求、ComfyUI對映／預檢、清空畫風權重。該版未生真SD圖或付費請求。

## 多畫風與精修

`style_loras` 是第一畫風後最多七筆有序 `{lora, weight, trigger, enabled}`。權重0–1.5，啟用ID不可重複，停用筆保留編輯但不送渲染。原生ComfyUI需 `style_lora_2/style_weight_2` 至 `_8`；未用對映歸零。內建ComfyUI與WebUI套用整個選定堆疊。

`render_options` 包含 refiner／hires／adetailer，各有 `mode` inherit/on/off 與 `targets` portrait/pixel/cg。預設值與空陣列標準化移除以保留舊快取。Refiner選本機底模與切換0.01–0.99；Hires選本機擴大器、倍率1–2、步數1–80、denoise0–1、CFG1–20、採樣器。ADetailer最多四段且受實際script-info容量限制，可分別設偵測器、信心、遮罩、採樣器、prompt、身份追隨與驗證後追加參數。沿用與明確關閉有區別，不改原模板／視窗。

只有 `command` 的 `refresh_sd_capabilities` 重新讀取能力，不改保存設定。WebUI讀偵測器、script容量、採樣器、本機擴大器與實際OpenAPI欄位。不支援／不適合的選項排程前阻擋；神經擴大器呼叫extras前再次確認本機權重，不下載。

文字生成用原生Hires.fix；WebUI參考圖img2img沒有原生Hires階段，先基本解析度身份／姿勢生成，再用已存擴大器縮放，最後第二次img2img依倍率／Steps／denoise／CFG重繪。ADetailer只在最後，不執行兩次；未選修補段明確停用，避免插件預設補入。步行用途需勾選，最大2048px；兩次副本保留進階參數、身份與ControlNet參考。

精修控制屬WebUI／Forge。ComfyUI要求明確開／關時會阻擋並解釋，需沿用原生品質流程，不能悄悄忽略。多LoRA兩種後端皆支援。

v0.24新增16項隔離要求檢查：排序、用途、沿用、關閉、實際欄位、第二次生成、最後ADetailer、不寫世界的驗證、模型／插件／容量／尺寸、持久化、原生綁定。匿名本機SFW小測試取得384px PNG，使用兩畫風、同底模Refiner、ADetailer與兩種Hires路徑，只確認接收／輸出，不證明臉部偵測、另一Refiner品質或長期身份一致。實SD結果保持私有。
