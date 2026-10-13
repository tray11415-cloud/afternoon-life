# v0.19.0 release review

[繁體中文](RELEASE_REVIEW.zh-TW.md) · [简体中文](RELEASE_REVIEW.zh-CN.md) · [日本語](RELEASE_REVIEW.ja.md) · **English**

The review found no blocker requiring a core rewrite. This release fixes first-run dependency/key handling, adds persistent Traditional Chinese/Japanese/English settings and dialogue guidance, corrects male-character model guidance, localises the primary interface and static settings help, adds English/Japanese workshop commands, and wraps the toolbar for longer labels. Public asset credits are now served by the local game.

## Evidence

- 161 original prototype tests passed.
- 8 release tests passed: preferences persistence without changing world/profile/TTS, invalid locale rejection, offline dialogue language, xAI gender/language guidance using a mock response, catalogue coverage, protected HTTP routes, English/Japanese replacement plus undo, and duplicate-listener rejection.
- The 700+ entry catalogue covers all 398 original static interface strings in both English and Japanese. Author text, prompts, history, source content and native SD remain unchanged.
- Browser checks passed for English/Japanese/Traditional Chinese round trips and character-form preservation. Existing character, component, SD and native-template checks are retained in the repository.
- Demo mode uses local rules and fixed dialogue, never a hidden live model. Recording annotations identify the mode actually shown.

## Known limits

Long-term story quality, large-scale performance and trained semantic memory are not validated. Daily routines and crafting use authored rules/recipes. External catalogues are snapshots. Model identity, outfit and animation quality needs human preview; extension compatibility and neural TTS depend on external installations. Explicit media stays disabled.

## Publication scope

Publish the source, packaged LPC/Kenney art, licences, bilingual README, tests and showcase. Exclude keys, work folders, private saves, local SD/TTS inventories, model weights and generated caches. The local SD sample gallery is omitted from the public checkout; optional generation features remain present. No provider or asset author is claimed to endorse the project.

## v0.20 checks (2026-10-13)

Title, grouped settings, pixel looks, single-profile manual drafting and four UI languages. Regression: 161 prototype tests, 8 release tests, 11 character-customisation tests, 11 atelier tests, 30 component tests, 26 SD-studio tests and 18 native-SD tests passed. API requests mocked in tests; no paid calls. Frontend JS syntax checked. Browser: preference save/reload, Simplified Chinese, per-character look preview/apply, local draft, card export, title/new game/archive restoration, shared invitation, inventory purchase, SD actor shortcut and Simplified replacement/apply/undo passed. Automated card-file upload was blocked by browser extension permissions; no extension access was expanded. Long-term story quality and arbitrary SD model compatibility are still unvalidated.

Production files for auto/manual saves, SD settings/native templates, TTS settings and xAI ledger matched their pre-deployment SHA256 values. No private data or local model weights are packaged. Existing local SD proof samples stay on the machine, excluded from public distribution. Adapted pixel layers retain attribution.
