# API and Stable Diffusion setup

[繁體中文](CONNECTION_SETTINGS.zh-TW.md) · [简体中文](CONNECTION_SETTINGS.zh-CN.md) · [日本語](CONNECTION_SETTINGS.ja.md) · **English**

Open **Game settings → AI and generation → API key and SD paths**.

## AI API

1. Enable live AI and paste your xAI key.
2. Dialogue defaults to Grok 4.3 and actions to grok-build-0.1. Selectors offer models with configured usage prices.
3. Remember key saves it with the current Windows user's DPAPI encryption. Unchecking uses a newly entered key only for this running session.
4. Save API settings applies immediately. Leave the key blank to keep the existing one.
5. Test saved API connection checks only the model catalogue, not generated dialogue. Unsaved input is not tested.

This form supports xAI at the fixed URL https://api.x.ai/v1. Other local models use Model and tool interfaces. Saving makes no model request and preserves the world, usage ledger and tool routes. Saved keys are not returned to the form or included in saves, cards or exports.

## Stable Diffusion

1. Select a detected installation, choose a folder, or paste an absolute installation path.
2. Select the WebUI/Forge folder containing `webui.py`, or ComfyUI containing `main.py` and `comfy`. Do not select only the models folder.
3. Enter the actual local URL: WebUI commonly uses `http://127.0.0.1:7860`, this project's reForge uses `http://127.0.0.1:7861`, and ComfyUI commonly uses `http://127.0.0.1:8188`. Local SD needs no API key.
4. Save and connect SD. After first connecting a new folder, choose a global checkpoint and save again.
5. Start SD and test the saved connection. WebUI needs `--api`. SD launcher, LoRAs and full generation settings opens the existing launcher and character art configuration.

Connecting reads models in their original location, without copying or downloading weights. It does not start SD or generate artwork. A different installation needs its own checkpoint; character LoRAs/templates must remain compatible. Switching is blocked while generation jobs are queued or running.

The connection update passed ten new settings/route checks and one explicit-demo save-isolation check. Existing gameplay suites were not rerun, and no paid model call or image generation was performed for this update.
