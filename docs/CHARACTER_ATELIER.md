# Unified character atelier · v0.22

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
