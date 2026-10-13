# Unified character atelier · v0.24

One form combines name, adult age/gender, one art prompt, optional LoRA, trigger, seed, appearance controls, personality, goals, optional background, manual AI drafts and cards. A character save validates and commits that actor's profile, then schedules portrait expressions + sprites and one CG with the same applied identity/outfit snapshot. Matching ready outputs are auto-applied. Internal component validation/history supports undo; no separate Apply click is required for this explicitly requested save workflow.

Prompt-only manual generation is supported. `<lora:filename:0.8>` tags resolve exact local resources within the selected installation (first character, second clothing; at most two). The normalised identity is stored once in the character profile and SD binding. Local SD configuration, native templates, all other profiles and the human player role are retained. No models are guessed/downloaded.

Native SD is an independent embedded UI. Its unsaved form is not scraped. Import an original generated PNG/PNG Info or full API payload once, save a native template and select its purpose. PNG restores only written metadata; unwritten extensions require full payloads. Unified character jobs override WebUI ADetailer positive identity text in copied payloads/PNG Info using the current identity and expression, while preserving detectors, masks, negatives and other extension settings. Saved/native UI workflows are never rewritten. A native ComfyUI template with a LoRA node still needs its explicit LoRA; prompt-only uses a compatible built-in workflow. Actual quality remains dependent on the supplied model and template.

## Protected local API

POST `/api/art` requires `X-Play-Token`, the existing Host/Origin guard and `operation: "atelier"`.

- `params.command: "state"`: selected SD configuration plus per-actor current/template fingerprints and latest pipeline pack.
- `save_character`: exact fields `command, actor, mode, profile, before, sd, binding_before, scene, description`. Profile uses existing adult character schema. `before` and `binding_before` reject stale edits from another page. Current saves preserve event prefixes, wallets, inventory, relationships and other actors; templates only update future character templates and do not render the old world.
- `build_saved_character`: `command, actor`, for an existing committed art prompt after creating a new save. This schedules only art and does not write profile events.
- `retry_character` / `cancel_character`: `command, actor, id`; the ID must match the actor's current pack. Retry preserves ready outputs. Full queues wait and resume automatically.
- Legacy `binding`, `generate`, `apply`, `restore` remain available. Restore cancels that actor's pending automatic application and retains generated files.

The pipeline persists under ignored `work/character-pipelines.json`. Each pack owns two jobs and tracks applied stages. Background reconciliation checks profile/binding/outfit fingerprints before application. A newer save supersedes the old plan; changed character/outfit is marked stale, never silently applied. Cancel affects only owned jobs. Restarted interrupted jobs show a retryable state. Unchanged art recipes reuse compatible results, including name-only changes.

The player is human controlled. Backstory remains private authored input and never creates past life events. CG image selection does not move actors or create experience memories. API budget is not reset by art, save or load operations. No paid LLM call is part of the character art pipeline.

## All retained character tools

Adult age 18–120; name up to32 characters, unique; voice/personality 500; goal100; background2000; art prompt1000. Existing `look` controls include eight hair styles, hair/skin/eye colours, soft/oval/angular face, height150–205, slim/average/athletic/curvy shape and initial clothing colours. They are optional native-pixel controls and SD notes, not a 3D avatar editor. Purchased clothing follows its actual wardrobe recipe.

AI drafts are manual and actor-scoped, with normal usage limits and an explicit offline example. Cards are UTF-8 `lifebox.character.v1` JSON (64KiB UI limit) with profile data only, no images/models/keys/world memory. Old preview/prepare/apply endpoints and component rollback remain for tools. The authored body/portrait assets retain LPC credits; rebuild with tools/build_look_layers.py and the attributed source pack.

21 pipeline tests cover rename/state preservation, pure prompt generation, local tag resolution, profile isolation, stale edits, automatic application, queue waiting, retry, cancellation, new-save templates, compatible art reuse and fallback restoration. SD/native/UI tests use isolated or mocked services. Guide screenshots use packaged credited LPC assets with explicit mock labels, never claim fresh SD render quality.

See [illustrated player guide](PLAYER_GUIDE.zh-TW.md) and [artwork licences](../ASSET_LICENSES.md). Interface organisation references [AI＊少女's manual](https://aisteam.illusion.rip/manual/readme_jp.html); the code/interface are original and no AI Shoujo assets are included.

## Per-character model and style overrides

The SD binding retains its existing nine required fields and accepts optional `checkpoint`, `style_lora`, `style_weight` (0–1.5, default 0.8), and `style_trigger` (SFW text, at most 1600 characters). IDs must reference selectable local resources from the current installation. Blank checkpoint inherits the global default; blank style LoRA disables the style loader. Empty overrides are removed during validation to retain old saved-binding fingerprints and render cache keys. Saving another actor does not change these choices. Both unified and advanced SD editors use this same binding.

Selected checkpoint, all three LoRAs, their weights and style trigger are captured in every portrait/sprite/CG recipe, cache key and material identity signature. Changing a recipe schedules new materials. Built-in WebUI and ComfyUI renderers apply every selected LoRA even without an identity LoRA. WebUI uses request-scoped checkpoint overrides and restore-afterwards. Native ComfyUI requires additional `style_lora`/`style_weight` bindings; missing style bindings block at preflight before any job starts. Optional unused clothing/style weights are set to zero when their bindings exist, preserving the native node topology. Original workflow snapshots and unsaved native UI forms remain untouched.

Verification adds nine model/style cases (30 pipeline tests total): independent saved recipes across all four kinds, persistence, legacy cache equivalence, recipe-change invalidation, malformed resources/weights without mutation, architecture mismatch, actual mocked WebUI payload and native ComfyUI mapping/preflight, and cleared native style weights. No real SD render or paid request was made.

## Multiple styles and quality options

Optional `style_loras` is an ordered array of up to seven additional `{lora, weight, trigger, enabled}` entries after the legacy first style. Weights are 0–1.5; active style IDs must be unique. Disabled entries remain editable and do not reach the render chain. Native ComfyUI needs numbered style_lora_2/style_weight_2 through _8 bindings; unused mapped weights are zeroed. Built-in ComfyUI and WebUI apply the whole selected stack.

Optional `render_options` contains refiner/hires/adetailer objects. Each has `mode` inherit/on/off and `targets` chosen from portrait/pixel/cg. Default options and empty extra arrays canonicalise away to preserve old bindings/cache keys. Refiner chooses local checkpoint and switch (.01–.99). Hires chooses local upscaler, scale (1–2), steps (1–80), denoise (0–1), CFG (1–20) and sampler. ADetailer has up to four passes bounded by script-info capacity, individual detector, confidence, mask, sampler, prompts, follow-identity and validated supplemental parameters. Native template inheritance and explicit-off override are intentional; original template files/native UI are never rewritten.

`refresh_sd_capabilities` with only command re-probes the connected service without changing saved config. WebUI reads installed detector names, script argument capacity, samplers, local upscalers and actual OpenAPI fields. Unavailable or incompatible choices block at preflight before enqueueing. Neural upscalers are checked again against local weight paths before extras; no model download is requested.

For text-to-image, Hires.fix uses native WebUI fields. For references, WebUI img2img has no native Hires.fix pass: first render identity/pose at base resolution, resize with built-in/local upscaler, then a second img2img diffusion at the requested scale/steps/denoise/CFG. ADetailer runs in the final stage, not twice. Unused ADetailer slots are explicitly disabled so installed script defaults cannot add unselected passes. Pixel use is opt-in; output cap 2048px. Native advanced settings and reference identity/control remain in both copied requests.

These quality controls are WebUI/Forge-specific. Explicit on/off requests for them on ComfyUI block with an explanation; its quality workflow must remain native, not silently ignored. Multiple LoRAs work on both renderers.

Sixteen new isolated request-level tests cover stack ordering, scopes, inheritance, off, actual emitted fields, second pass, final-only ADetailer, validation without world writes, model/plugin/capacity/size checks, persistence and native bindings. An anonymous local SFW acceptance test returned 384px PNGs for txt2img Hires and img2img second-pass Hires, using two style LoRAs, same-checkpoint Refiner and ADetailer. This confirms API acceptance/output, not successful face detection, alternate Refiner quality or long-term identity consistency. Real SD outputs remain private and outside release assets.
