# Project instructions

- Preserve the player's world, ledger, actor IDs and event history.
- One character's model context must contain only that character's permitted information.
- The human player is not an autonomous AI actor. All romance characters are adults; explicit generation remains disabled.
- Keep offline-demo behaviour clearly labelled. Never present rule-based sample dialogue as a real model response.
- Credentials, local settings, generated caches and saves belong under ignored work/. Never publish them.
- Source artwork has separate licences; preserve LPC/Kenney credits and notices.
- Interface locales are zh-TW, zh-CN, ja and en. Do not translate authored profiles, input values, raw prompts, source quotes or historical speech in place.
- Data/art/tool changes use previews and compatibility checks before application, with history for undo.
- Run meaningful affected tests and the release tests. No live paid model calls in automated tests.

- The explicit Save and complete character action validates and auto-applies its own matching outputs; do not add redundant approval steps. Preserve all existing character controls/cards and native SD workflows.


## v0.23 Per-character SD checkpoint and style

- Optional checkpoint/style_lora/style_weight/style_trigger in the existing per-actor SD binding; unified and advanced editors share them. Blank overrides retain legacy binding and cache hashes. Do not guess assignments or download weights.
- All portrait/sprite/CG recipes use actor overrides and three separate LoRA categories. Native ComfyUI needs explicit style bindings; preflight blocks missing bindings. Clearing mapped style weights uses zero in copied requests. Never rewrite native templates or unsaved SD UI.
- 30 pipeline tests include nine model/style cases; 26 character studio and 18 native template tests join Windows CI. Tests use mock rendering; no fresh SD output or paid model call was made for this update.
