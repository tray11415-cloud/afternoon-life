# Afternoon Life player encyclopedia · v0.24

[繁體中文](PLAYER_GUIDE.zh-TW.md) · [简体中文](PLAYER_GUIDE.zh-CN.md) · [日本語](PLAYER_GUIDE.ja.md) · **English**

One character, one saved recipe. The town keeps living. Screenshots show an isolated offline world, labelled SD mocks and credited LPC art, not private characters or newly generated SD artwork. Existing screenshots show the Traditional Chinese interface; the instructions below use your selected language.

## Start your afternoon

![Start menu](../prototype/web/assets/guide-v22-start.png)

### Choose an entry

Use Continue for existing progress. New game opens character templates before you explicitly create a save; the previous save is archived and can be restored from the atelier. Character atelier edits the male player or any of the ten residents.

### First play

The offline demo needs neither a chat API nor SD. It uses fixed sample dialogue and local schedules. Live AI requires configured model access; SD artwork requires a running local SD service. The visible offline label identifies the current mode.

### Save and restore

Progress saves automatically; Save also creates a manual version. Loading does not reverse API usage. Creating a new game preserves the old save, and restoration brings back its characters and world progress.

## Complete a character in one editor

![Character editor](../prototype/web/assets/guide-v22-character.png)

### Name, prompt, save

Choose the player or a resident, enter a unique name and character prompt, then press Save and complete character. The profile saves immediately; portrait expressions, four-direction walking sprites and one CG enter the same SD queue and are applied automatically when matching outputs are ready.

### Write a stable identity prompt

Describe fixed features, for example adult woman, long black hair, brown eyes, round glasses, casual long-sleeved clothes. Put backgrounds and actions in generation details and the CG scene, so a café background does not appear in every walking sprite. Age and gender come from the character fields; characters must be adults.

### LoRA is optional

Use a checkpoint and prompt alone, or select a local character LoRA. Explicit tags such as `<lora:filename:0.8>` resolve a unique local filename: first character, second clothing. Missing, ambiguous or incompatible resources produce an explanation rather than a guessed replacement. Use the trigger words specified by the model author.

### Existing fallback controls

The same editor retains face, eyes, skin colour, height, build, eight hairstyles, hair and starter-clothing colours, personality, voice, goal, optional backstory, AI drafts and cards. Enabling appearance details adds them to SD identity and updates the native pixel fallback; otherwise the character prompt leads.

### Names and backstory

The player and every resident can have a unique name of up to 32 characters. Rosters, dialogue, invitations and SD/TTS selectors use it; fixed actor IDs and existing memories remain. Backstory is private authored information and cannot create income, relationships or past events.

### Cards and AI drafts

Drafting is optional and manual. The result enters the same editor; live mode uses the existing model and budget, while offline mode gives a labelled example. JSON character cards contain appearance and background settings, not keys, world memories, wallets, weights or images.

## Progress, retry and artwork selection

![Generation progress](../prototype/web/assets/guide-v22-results.png)

### Track every stage

The left panel shows portraits/sprites, CG and application status. Busy GPUs wait in the queue. A disconnected SD service, missing checkpoint or missing native bindings leaves the profile saved with an explanation; fix it and retry unfinished stages.

### Automatic application

Application checks the actor, saved profile, LoRA recipe and actual outfit. Changing the character or clothing during generation makes old work stale; it cannot overwrite the new appearance. Old files remain. A name-only edit can reuse compatible finished artwork.

### Choose another result

Open Artwork results and inspect thumbnails for portraits, expressions, sprites or CG. Choose a different expression or historical result, or regenerate a single item. Individually regenerated results are selected manually after completion.

### Stop and restore

Cancel stops only that character's current jobs, not other residents' SD work. Restoring native/imported artwork keeps generated files. A new save supersedes the previous automatic application plan; ready materials can survive a partial failure.

## Movement, conversation and public venues

![Town exploration](../prototype/web/assets/guide-v22-world.png)

### Move and interact

Move with WASD or arrow keys, or click the ground to find a path. Venue buttons plan real walking routes; enter buildings through doors. Press E near a person or object. Private off-screen activities do not become player knowledge.

### Talk

Walk near a character, press E and enter your message. Dialogue uses the configured model; offline sample lines are local rules, not LLM replies. Residents have their own voices, goals, needs and memories, and can work, walk or refuse an invitation.

### Places to visit

Read linked sources in the library, buy café drinks, observe zoo animals, view gallery exhibits, watch publicly available films, eat at the restaurant, walk in the park, trade at the market, buy clothes and swim. Choose an available object or item on arrival; costs and duration appear in the interface.

### Understanding external content

Venues store source links, written descriptions and summaries. Residents understand activities they actually attended through that text. Catalogues are snapshots, not live inventory or guaranteed current exhibitions. Books, films and websites open at their original sources.

## Shared activities, neighbours and town events

![Shared activities](../prototype/web/assets/guide-v22-social.png)

### Invite several people

Open Shared activities, name the activity, choose a venue and item, select companions and set a meeting time. Each person independently accepts or declines, walks there and pays their own share. The inviter and at least one companion must actually arrive before it starts.

### Absences and cancellation

The group waits up to ten minutes after the start time. Absent characters receive no activity content, group-chat or payment memory. Cancellation before the start costs nothing; leaving afterwards does not automatically refund purchases. Free walks also support shared activities.

### NPCs and events

Town activities lists festivals, exhibitions, scripted neighbours and autonomous conversations. AI residents can meet other AI residents or ordinary NPCs. Only attendees or listeners receive the relevant memories. Import NPC scripts and public-event definitions through the component workshop.

## Inventory, income, market and wardrobe

![Inventory and economy](../prototype/web/assets/guide-v22-inventory.png)

### Player inventory

Expand Pockets and daily life to see coins, needs, income and item quantities. Use one consumes one unit; crafting materials feed recipes. Whether a purchase enters the inventory or starts an activity depends on the item's interaction.

### Work and create

Complete a shift at a workplace to receive wages. At home, use materials to craft goods and consign them at the market. Residents have their own income, inventory, desires and work; they do not share the player's wallet.

### Market trading

Consign a work with a quantity and price; income goes to its seller only after a real purchase. Buy residents' works or withdraw your own listings. Listing an item does not guarantee an immediate sale.

### Wardrobe and swimming pool

Bought clothing enters your own wardrobe. Change in a suitable room with Wear this outfit. Sprites and SD recipes follow the actual outfit. Swimming requires swimwear; its SD art also needs the matching clothing LoRA binding. Owning an outfit does not mean wearing it.

## Advanced SD and native fixed templates

![SD configuration](../prototype/web/assets/guide-v22-sd.png)

### Connect for the first time

Use Game settings → AI and generation → API key and SD paths to choose an installation or add its path, enter the actual local URL, connect it and select a checkpoint. Test the saved connection separately. Finding a model file does not mean the service is running. The character atelier reuses this configuration.

### Already configured native SD?

Saving the outer game settings does not capture the embedded SD form. Download an original PNG generated with your settings, collapse the SD window and import the PNG, PNG Info or complete API JSON under Save a new template from native SD. Save the template, assign portrait/pixel/CG purposes and save those selections once.

### ADetailer and postprocessing

Native templates preserve extension parameters expressible through their API. PNGs contain only metadata SD wrote; omitted ADetailer or other values require a full API payload. The game replaces prompt, negative prompt, seed, checkpoint and selected identity in copied requests. Unified jobs make WebUI ADetailer positive text follow the character/expression while retaining detectors, masks, negatives and other settings. Original templates and the native SD form are not rewritten.

### ComfyUI and purposes

Import an Export (API) workflow or finished history and bind identity, checkpoint, LoRAs, reference image and denoise. A native workflow containing a character LoRA node still requires that LoRA; prompt-only generation can use the built-in workflow. Portraits, sprites and CG may use separate templates because an illustration composition does not fit every walking direction.

### Template variables

Built-in templates support `{identity}`, `{outfit}`, `{expression}`, `{direction}`, `{pose}` and `{scene}`. Identity comes from the character prompt, clothing from the actual outfit, variations change expression, and CG adds a scene. Portrait variations are reusable; CG represents one composition.

## Speech, language and usage

![Speech settings](../prototype/web/assets/guide-v22-tts.png)

### A voice for each person

Open Voice settings and choose Windows/browser local voices, Kokoro or a compatible local TTS service. Set the actor, reading language and voice, then save or listen. Neural TTS requires a running compatible service; selecting a model does not install weights.

### Speech is not translation

TTS language controls voice and pronunciation. Traditional Chinese, Simplified Chinese, Japanese and English apply to the interface, documentation and future dialogue guidance. Names, authored backstories, historical speech, source articles and native SD prompts stay in their original language.

### Control usage

Actions, dialogue, memory, SD and TTS have separate interfaces. Local SD and local speech do not spend chat API quota; AI drafting and actual model dialogue use the existing limits. Usage and game information shows the ledger. Cancellation or loading cannot erase calls that already occurred.

## Replace maps, artwork, interactions and AI

![Component workshop](../prototype/web/assets/guide-v22-components.png)

### Replace by instruction

Open Component workshop, select a type and target, and enter an instruction such as Rename to Afternoon Garden. Prepare the replacement, inspect field differences and compatibility, then apply. The example screenshot shows a preview, not a changed world.

### Replaceable components

Map collisions, doors, objects, backgrounds, PNGs, venue catalogues, items, clothing recipes, actors, NPC scripts, events, rules, model services, custom tools and interface colours are replaceable. Full JSON and component packages can be imported or exported.

### Undo and custom tools

History retains old values for a previewed undo. Stable IDs preserve memories, transactions and inventory. Built-in instruction parsing supports defined operations; complex requests can use a local replacement AI service. Text instructions cannot execute arbitrary computer programs.

## Game settings and common questions

![Game settings](../prototype/web/assets/guide-v22-settings.png)

### Display and controls

Set view zoom, names, minimap, reduced animation and larger text. These do not change collisions or memories. Pausing allows observation; explicit game actions still advance according to the rules.

### Saved but no artwork?

Read the stage's explanation. Missing checkpoint, offline SD, incompatible LoRA family, missing swimwear binding or missing ComfyUI bindings block rendering while preserving the profile. Fix settings and retry. Duplicate names, underage characters and invalid prompts are rejected before saving.

### Unexpected artwork

Edit the character prompt or LoRA and save again. Change expressions and pose templates in Advanced SD. Seeds and references reduce variation but cannot guarantee the same face or perfect animation. Name, appearance and personality are separate; artwork cannot invent backstory.

### What the screenshots prove

The screenshots come from a separate offline world. The artwork pipeline uses clearly labelled SD mocks and credited LPC images to demonstrate controls and automatic application, not real SD quality. Private actors, models, saves and workflows are excluded.

## Interface references and credits

The atelier's roster, preview, categories and cards refer to the organisation of the AI＊Shoujo manual. This project uses its own interface and pixel/SD workflow, without that game's code, artwork or 3D character assets.

[AI＊Shoujo manual](https://aisteam.illusion.rip/manual/readme_jp.html) · [Artwork licences](../ASSET_LICENSES.md)

## Per-character checkpoint and style · v0.23

Select a character, then choose Character checkpoint and Style LoRA below the prompt. The checkpoint can inherit the global default; style is optional. Use the author's weight and trigger guidance, then Save and complete character. Portrait variations, sprites and CG use the same recipe without altering other actors. Select Use global checkpoint and save to remove an override.

![Per-character model and style](../prototype/web/assets/guide-v23-character-style.png)

This isolated UI screenshot uses credited LPC mock outputs. Selectors show usable resources in the current installation. Known architecture mismatches block generation. Native ComfyUI requires `style_lora`/`style_weight` bindings; otherwise use the built-in template.

## Multiple styles, Refiner, ADetailer and Hires.fix · v0.24

1. Select the character. The upper selector holds the first style; expand Multiple style LoRAs to add others with weights, triggers, switches and order. Up to eight styles are supported. Adjust a weight instead of adding a duplicate.
2. Expand Refinement and high resolution. Refresh local capabilities to read the connected service's detectors, samplers and local upscalers.
3. Choose Inherit native template, Use this character's settings or Explicitly disable, then select purposes. Refiner selects checkpoint/switch ratio. ADetailer adds ordered detector passes with optional identity/expression following and additional validated JSON parameters.
4. Hires.fix selects local upscaler, scale, steps, denoise, CFG and sampler. Text-to-image uses native Hires.fix. Reference variations and CG upscale and run a second diffusion pass; ADetailer runs only in the final stage. Walking sprites are excluded by default but can be selected.
5. Press Save and complete character once. All options save with one recipe and apply to their selected purposes; old files and original templates remain.

Output is limited to 2048px; absent upscalers are not downloaded. Native ComfyUI multiple styles need `style_lora_2/style_weight_2` through `style_lora_8/style_weight_8`. The Refiner/ADetailer/Hires.fix panels target WebUI/Forge; ComfyUI must inherit and configure its own native workflow.

![Multiple styles](../prototype/web/assets/guide-v24-loras.png)

![Refiner](../prototype/web/assets/guide-v24-refiner.png)

![ADetailer](../prototype/web/assets/guide-v24-adetailer.png)

![Hires.fix](../prototype/web/assets/guide-v24-hires.png)

## API key and SD folder setup

Open Game settings → AI and generation → API key and SD paths. Enter your xAI key, select dialogue/action models and save. Windows can encrypt the remembered key; leave the input blank to retain the existing key. Saving applies immediately without generating dialogue. Test the saved connection with its separate button.

Choose a detected SD installation, browse for a folder or paste its absolute path. Select the folder containing `webui.py`, or `main.py` and `comfy`, not only the models folder. Enter your actual local URL: WebUI commonly uses `http://127.0.0.1:7860`, this project's reForge uses `7861`, and ComfyUI commonly uses `8188`. Save and connect, choose a checkpoint, then test. Local SD needs no API key and uses weights in their original folder.

[Full connection instructions](CONNECTION_SETTINGS.en.md)
