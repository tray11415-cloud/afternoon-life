# Character atelier / 人物工坊 / 人物工坊

Current profiles are private actor settings, not public world facts. The player is human controlled. Characters must be adults (18–120). Editing a profile does not fabricate income, relationships or past events.

## Workflow / 操作

1. Select current character or new-game template, then select the person.
2. Enable a custom pixel look to change native appearance. Inspect front, back, sides and walking. Imported artwork takes precedence; remove that override in Art assets if you want the native look visible.
3. Current profile: Preview changes → Apply. Undo from Component workshop history. Templates: Save template, or confirm a new game; the old save is archived.
4. AI draft is one manual request and stays in the editor. Offline gives a local example, clearly labelled. If you edit or switch people while a request is running, the result does not overwrite the new draft.
5. Cards export/import profile data only. No images or models are included. Import validates the adult profile and look without applying to the world.

繁中：目前人物先預覽再套用；新遊戲模板另存。外觀修改與卡片匯入不生成世界事件，套用後只修改該人物設定。已匯入圖片優先於原生外觀，可在美術素材入口恢復。背景故事可不啟用，未啟用的內容不傳給人物草擬模型。

简中：当前人物先预览再应用；新游戏模板单独保存。卡片不包含图片或模型。外观草稿不改钱包、背包、记忆或他人的背景。人物草拟仅在手动点击时调用，离线示范会明确标记。

## Portable card

`{"format":"lifebox.character.v1","profile":{...}}`, UTF-8 JSON, at most 64 KiB in the UI. Profile fields: name, age, gender, voice, goal, background_enabled, background, appearance, look. `look` has enabled, hair, hair_color, skin_color, eye_color, face, height, build, top_color, bottom_color. Six-digit hex colours; height 150–205 cm; hair: short, pixie, bob, long, curly, bun, side_bob, wavy; build: slim, average, athletic, curvy; face: soft, oval, angular.

## Protected local API

GET `/api/characters` exposes templates/current profiles to the local player. POST requires the existing `X-Play-Token` and same-origin write guard:

- `{"operation":"preview_look","actor":"player","profile":{...}}` → sprite/portrait URLs, frames, look, sd_identity, preview_only. Writes derivative PNG cache only.
- `{"operation":"draft","actor":"member-01","profile":{...},"brief":"..."}` → profile, source (`model` or `offline-example`), applied:false, usage. Brief 1–800 characters. Sends one profile only, no world memory. Existing model budget applies.
- `prepare_current` uses the current profile fingerprint and returns a component proposal. Apply/rollback use the existing component API.

Preferences are saved separately from world and TTS. `ui_hold` resets heartbeat timing only; it does not alter simulation tick, events or the usage ledger. A second page or explicit action can still advance the shared world.

## Art and limits

Native derivatives use credited clothed LPC layers (see LPC-CREDITS.txt). Face/eye choices become SD notes; pixel silhouettes are approximate bounded scaling. SD character LoRA binding is still explicit. Cached SD looks from a different enabled look are hidden until a matching image is applied. Imported player artwork remains a deliberate override. No 3D body editor, nude base sprites, model weights, or automated live image generation is bundled.

## Rebuild the credited pixel layers

Bundled layers are ready to use. To rebuild, obtain the attributed LPC source and run `python tools/build_look_layers.py --source /path/to/LPC/spritesheets --project .` after the existing LPC art builder. `CREDITS.csv` must be beside `spritesheets`. The builder checks coverage and appends every used author/licence; it publishes clothed composites and colour masks, not raw nude body layers. See LPC-CREDITS.txt. No automatic source/model download is performed.

The title/menu/creator interface is original work. It adopts familiar game-category organisation; no AI Shoujo artwork or code is included. This is a pixel/SD atelier, not a 3D avatar editor.
