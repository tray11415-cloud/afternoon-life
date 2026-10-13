# Afternoon Life

[繁體中文](README.zh-TW.md) · [简体中文](README.zh-CN.md) · **English**

A top-down pixel life sandbox with ten adult residents, a human-controlled player, and a town that keeps moving. Each AI resident receives their own observations, goals and memories. A shared model service is allowed; a shared omniscient character context is not.

**Status: playable alpha, v0.22.0.** This is an experimental life simulation, not a finished commercial galgame or a proven long-term story engine. Explicit content is disabled.

[![Guided walkthrough](docs/media/guide.en.png)](https://github.com/tray11415-cloud/afternoon-life/releases/download/v0.19.0/afternoon-life-guide.en.mp4)

[English narrated walkthrough · 5:28](https://github.com/tray11415-cloud/afternoon-life/releases/download/v0.19.0/afternoon-life-guide.en.mp4) · [中文解說版](https://github.com/tray11415-cloud/afternoon-life/releases/download/v0.19.0/afternoon-life-guide.zh-TW.mp4) · [Download the release](https://github.com/tray11415-cloud/afternoon-life/releases/tag/v0.22.0)

The Traditional Chinese and English tours show v0.19, with synthetic narration, captions, eight chapters and actual gameplay in isolated offline worlds. No live model dialogue or SD generation is claimed. [Chapters, subtitles and recording notes](docs/WALKTHROUGH.md).


[简体新版导览 · v0.20 · 7:37](https://github.com/tray11415-cloud/afternoon-life/releases/download/v0.20.0/afternoon-life-guide.zh-CN.mp4)

## Unified character studio (v0.22)

Select a character, enter a custom name and one character prompt, then **Save and complete character**. The same save commits private character settings and schedules portrait expressions, four-direction walking art and one CG. Matching ready outputs are applied automatically; unfinished stages show their error and can be retried. Existing art files, world progress, inventories and other characters are retained.

Hair, body, colours, personality, goal, optional background, AI drafts and cards are now in one editor. LoRA is optional for prompt-only generation; explicit local `<lora:filename:0.8>` tags are resolved without guessing. Advanced/native SD configuration is retained. Templates are built after creating their new save. The existing videos show earlier versions.

[Illustrated player encyclopedia (Traditional Chinese, 10 chapters)](docs/PLAYER_GUIDE.zh-TW.md) · [Character workflow and API](docs/CHARACTER_ATELIER.md). In-game guide: `http://127.0.0.1:8765/guide.html`.

## Play

You need **Python 3.12+** and **Pillow**. No game engine installation, Node.js, API key or SD model is required for the offline demo.

```powershell
git clone https://github.com/tray11415-cloud/afternoon-life.git
cd afternoon-life
python -m pip install -r prototype/requirements.txt
cd prototype
python -m lifebox.play --demo
```

Open **http://127.0.0.1:8765/**. On Windows, you can also double-click `prototype/play-demo.cmd` after installing the dependency; that launcher uses **8766** to stay separate from a live game. `play.cmd` uses xAI if a key is configured; otherwise it opens the offline demo. Demo and live saves are separate. For a second CLI instance, supply a different `--port`.

Move with **WASD / arrows**, click the ground to walk, and press **E** near people or objects. Walk through doors to enter buildings. Place buttons plan a route rather than teleporting you.

Open **Game settings** for **繁體中文 / 日本語 / English**. The choice is saved and guides future AI dialogue. Character names, authored profiles, historical speech, source articles and native SD interfaces keep their original text. TTS voices and speech language are selected separately.

The offline demo is visibly labelled. It uses local schedules and fixed sample dialogue, **not an LLM**. It makes no paid model calls.

## Start menu and character atelier (v0.20)

The title screen offers Continue, New game, Character atelier, Game settings and manual-save loading. Continue keeps the latest position. New game opens templates first; explicit confirmation creates the world and archives the previous save for restoration.

Edit the player and ten residents separately through identity, face/build, hair, clothing, personality, optional backstory, and AI/cards. Custom looks are opt-in, preserving existing artwork by default. Eight hairstyles, hair/skin/starter-clothing colours and bounded silhouette scaling have real four-direction walking previews. Face and eye settings guide SD identity; this is not a 3D morph editor. Purchased clothing keeps its own palette.

Preview current-character changes before applying; new-game templates are separate. Manual AI drafting sends only the selected profile and brief, uses the existing action model and shared budget, and does not apply automatically. Offline mode gives an explicitly labelled local example. Portable JSON cards contain profile settings, without world memories, keys, LoRA weights or images. Import still requires preview and apply. The clothing category links to SD, where each character needs an explicit model binding.

Settings group display, controls, speech, AI, language and saves. Persist zoom, names, minimap, larger text, reduced animation and pause while settings are open. The main menu always suspends this page's heartbeat; another open game page can still advance the shared world. TTS voices and reading language are separate. [Character cards and preview API](docs/CHARACTER_ATELIER.md).

## What you can do

- Explore **22 maps and 10 public venues**: library, café, zoo, gallery, cinema, restaurant, park, market, clothing shop and swimming pool.
- Invite residents to shared activities. Each accepts or declines, walks to the meeting point, pays individually and records only what they attended. Scripted NPCs have separate schedules and fixed lines.
- Work shifts, craft from recipes, consign goods, buy consumables and change clothes. Money and items come from completed engine events; a character cannot create them by claiming to have done something.
- Edit the player and ten residents: name, adult age, gender, personality, goals, optional backstory and appearance notes. Preview current-character edits before applying; keep progress and undo through workshop history. New-game templates are separate.
- Replace art, scene geometry, interactions, catalogues, calendars, economy rules and model/tool adapters in the **Component workshop**. Stable IDs, compatibility checks, previews and rollback protect existing saves.
- Connect local **WebUI / Forge / reForge / ComfyUI** for character LoRA portraits, expression variations, four-direction sprites and SFW CG. Inventory installed resources, import full native templates, preview results and apply them by character/outfit. Model weights are not bundled.
- Choose optional Windows/browser voices or compatible local TTS. Audio is limited to lines the player heard; loading a save does not replay all dialogue.

## Real AI and local services

Set `XAI_API_KEY` in the process environment, then run without `--demo`:

```powershell
cd prototype
python -m lifebox.play
```

Keep credentials out of source files. The existing Windows DPAPI key format is also supported. Defaults are **Grok 4.3 for dialogue** and **grok-build-0.1 for action decisions**, subject to account/provider availability. The persisted usage ledger defaults to 50 requests / US$0.05 estimated spend; loading or restarting does not reset it. Estimates use the adapter's price table and are not a billing guarantee.

Local schedules do not call a model. Optional autonomous AI conversations are off by default. Dialogue, action, memory and replacement tools can use different adapters without creating new personalities or resetting memories.

SD is optional. Start your local service, select its installation folder in **Image generation**, then bind character LoRAs individually. Swimwear art also requires a swimwear LoRA. Merely finding a weight file does not mean its service or workflow is compatible. Neural background removal requires an existing compatible runtime and local weights; nothing is downloaded automatically.

Local tools use explicit project contracts: `lifebox.decide.v1`, `lifebox.interact.v1` and `lifebox.replace.v1`. `GET /api/components/schema` exposes six replacement function schemas. `tools/components_cli.py` supports inspect, prepare, apply, undo and export. Local HTTP APIs require the game's token and reject cross-origin writes; they do not execute uploaded Python or JavaScript.

## Limits you should know

- Long-term personality consistency, open-ended narrative quality and large-scale performance are not yet validated. Native routines, goals and crafting currently use small authored rules and recipes.
- Default memory retrieval is local lexical/event retrieval. Semantic embeddings are optional and need an actual embedding service.
- Venue catalogues are sourced snapshots, not live inventory or guaranteed current exhibits. Public film understanding uses plot/review text, not visual comprehension of the whole film.
- Generated identity, expressions, clothing and walking animation need human preview. ControlNet and references improve consistency but cannot guarantee it. Local SD extensions and model architectures may be incompatible.
- Replacements currently preserve the original 32px grid, scene dimensions and existing IDs. Expanding the world format needs a separate migration.
- Windows is the primary tested platform. Windows speech and desktop SD launch helpers are Windows-specific. No trained TTS model is bundled.

## Development

```powershell
cd prototype
python -m unittest discover -s tests
cd ..
python tools/test_atelier.py
python tools/test_release.py
python tools/test_character_customization.py
python tools/test_components.py ComponentsTests
```

Tests use isolated worlds and fake/local services. They do not require a real API key. Detailed release checks are in [docs/RELEASE_REVIEW.md](docs/RELEASE_REVIEW.md).

`prototype/lifebox` owns events, permissions, life rules and adapters; `prototype/web` owns the Canvas interface; `prototype/data` contains catalogues and manifests. `tools` contains asset builders and validation helpers. Saves, credentials, generated media caches and machine-specific settings live under ignored `work/`.

## Credits and licensing

Original project code is MIT licensed. **Art has separate licences**: LPC scene/character compositions are shared under CC BY-SA 4.0 with upstream options and attribution preserved in [LPC-CREDITS.txt](prototype/web/assets/LPC-CREDITS.txt) and [ASSET_LICENSES.md](ASSET_LICENSES.md). Kenney assets retain their CC0 notice. Do not assume the code licence covers model weights or external content.

Dialogue guidance references [Lieflat Less AI Tone](https://github.com/larashero3-dotcom/lieflat-less-ai-tone) (MIT). Memory design references [Spatial Memory Engine](https://github.com/jack66g/spatial-memory-engineagent) (Apache-2.0). Their notices are retained in `docs/third-party/`. No claim is made that either entire upstream system is integrated.
