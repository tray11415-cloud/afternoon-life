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

## v0.24 Multi-LoRA and local WebUI quality controls

- Up to eight style slots including the legacy first style. Additional entries are ordered with their own weights/triggers/switches; active duplicates are rejected. Both unified and advanced editors preserve the same profile, with all extra controls edited in the unified form. Empty defaults preserve legacy hashes.
- Refiner, ADetailer and Hires.fix have inherit/on/off and per-purpose scopes. Quality controls target WebUI/Forge; ComfyUI must inherit its native workflow. Multiple LoRAs work on both renderers; native ComfyUI needs numbered bindings. Never silently ignore explicit unsupported controls.
- Probe actual OpenAPI fields, detector models, script argument capacity and local upscalers. No implicit model downloads. ADetailer unused slots are disabled; reference-based Hires uses upscale plus second diffusion with final-stage ADetailer. Maximum output 2048px. Native templates and unsaved user SD UI remain unchanged.
- Sixteen additional mock request tests and two small anonymous local reForge SFW acceptance renders succeeded, with same-checkpoint Refiner. API acceptance/output does not prove successful face detection, alternate Refiner quality or character consistency. Exclude real SD renders and inventory from public packages.
