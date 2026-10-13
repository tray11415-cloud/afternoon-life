"""Explicit player connection settings; credentials stay outside saves and exports."""
import ctypes
import json
import os
import subprocess
from pathlib import Path

from .character_art import atomic, local_url
from .demo_backend import DemoBackend
from .xai import AIError, PRICES, XAIBackend, read_key

ENDPOINT = 'https://api.x.ai/v1'


def load_settings(project):
    try:
        data = json.loads((Path(project) / 'work/private/connections.json').read_text(encoding='utf-8'))
        if set(data) == {'enabled', 'model', 'dialogue_model', 'save_dir'} and type(data['enabled']) is bool and isinstance(data['save_dir'], str) and Path(data['save_dir']).is_absolute() and all(data[k] in PRICES for k in ('model', 'dialogue_model')):
            return data
    except (OSError, ValueError, TypeError):
        pass
    return None


def stored_key(project):
    private = Path(project) / 'work/private'
    return private / ('ui-xai.dpapi' if (private / 'ui-xai.dpapi').is_file() else 'xai.dpapi')


def save_key(path, value):
    if os.name != 'nt':
        raise ValueError('此平台只支援本次執行使用金鑰；請取消記住金鑰。')
    class Blob(ctypes.Structure):
        _fields_ = [('size', ctypes.c_ulong), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    raw = value.encode('utf-16-le')
    buffer = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    source, result = Blob(len(raw), buffer), Blob()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source), None, None, None, None, 4, ctypes.byref(result)):
        raise ValueError('Windows 無法加密保存金鑰。')
    try:
        encrypted = ctypes.string_at(result.data, result.size).hex()
    finally:
        ctypes.windll.kernel32.LocalFree(result.data)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(encrypted, encoding='ascii')
    os.replace(temporary, path)


class ServiceSettings:
    def __init__(self, session, project):
        self.s, self.project = session, Path(project)
        self.path = self.project / 'work/private/connections.json'
        self.memory_key = None

    def base(self):
        return self.s.backend.base if hasattr(self.s.backend, 'base') else self.s.backend

    def state(self):
        with self.s.lock:
            base = self.base()
            sd = self.s.studio.state()
            enabled = isinstance(base, XAIBackend)
            return {'ai': {'enabled': enabled, 'has_key': bool(self.memory_key or os.environ.get('XAI_API_KEY') or stored_key(self.project).is_file() or enabled),
                'saved_key': (self.project / 'work/private/ui-xai.dpapi').is_file(), 'can_remember': os.name == 'nt',
                'endpoint': ENDPOINT, 'model': base.model if enabled else (load_settings(self.project) or {}).get('model', 'grok-build-0.1'),
                'dialogue_model': base.dialogue_model if enabled else (load_settings(self.project) or {}).get('dialogue_model', 'grok-4.3'),
                'models': list(PRICES)}, 'sd': {'config': {k: sd['config'][k] for k in ('installation', 'backend', 'url', 'checkpoint')},
                'folders': sd['folders'], 'resources': [r for r in sd['resources'] if r['category'] == 'checkpoint' and r['selectable']],
                'service': sd['service']}}

    def operation(self, body):
        if not isinstance(body, dict):
            raise ValueError('無效連線設定')
        op = body.get('operation')
        if op == 'save_ai' and set(body) == {'operation', 'enabled', 'key', 'remember', 'model', 'dialogue_model'}:
            if type(body['enabled']) is not bool or type(body['remember']) is not bool or not isinstance(body['key'], str):
                raise ValueError('無效 API 設定')
            if body['model'] not in PRICES or body['dialogue_model'] not in PRICES:
                raise ValueError('請選擇已有價格與用量限制的模型。')
            key = body['key'].strip()
            if key and (not 8 <= len(key) <= 4096 or not key.isascii() or any(c.isspace() or ord(c) < 33 for c in key)):
                raise ValueError('請填入有效格式的 API 金鑰。')
            with self.s.lock:
                old = self.base()
                if body['enabled'] and not key:
                    key = self.memory_key or (old._key if isinstance(old, XAIBackend) else read_key(stored_key(self.project), prefer_environment=not (self.project / 'work/private/ui-xai.dpapi').is_file()))
                backend = XAIBackend(key, self.project / 'work/play-usage.json', model=body['model'], dialogue_model=body['dialogue_model'],
                    limit_usd=getattr(old, 'limit', .05), max_calls=getattr(old, 'max_calls', 50)) if body['enabled'] else DemoBackend()
                if body['key'].strip() and body['remember']:
                    save_key(self.project / 'work/private/ui-xai.dpapi', key)
                self.path.parent.mkdir(parents=True, exist_ok=True)
                atomic(self.path, {**{k: body[k] for k in ('enabled', 'model', 'dialogue_model')}, 'save_dir': str(self.s.root.resolve())})
                if key:
                    self.memory_key = key
                if hasattr(self.s.backend, 'base'):
                    self.s.backend.base = backend
                    self.s.components.original_backend = backend
                else:
                    self.s.backend = backend
            return {**self.state(), 'message': 'AI 設定已保存並立即生效；尚未驗證金鑰，不會自動呼叫模型。'}
        if op == 'test_ai' and set(body) == {'operation'}:
            with self.s.lock:
                base = self.base()
            if not isinstance(base, XAIBackend):
                raise ValueError('請先保存並啟用真實 AI。')
            available = {m.get('id') for m in base._request('/models').get('data', [])}
            if not {base.model, base.dialogue_model} <= available:
                raise AIError('model_unavailable')
            return {**self.state(), 'message': 'API 連線成功，兩個選定模型均可用；沒有生成台詞。'}
        if op == 'browse_sd' and set(body) == {'operation'}:
            if os.name != 'nt':
                raise ValueError('此平台請直接貼上 SD 安裝路徑。')
            script = "Add-Type -AssemblyName System.Windows.Forms;$d=New-Object System.Windows.Forms.FolderBrowserDialog;$d.Description='Choose your SD WebUI / Forge / ComfyUI folder';$d.ShowNewFolderButton=$false;if($d.ShowDialog() -eq 'OK'){[Console]::OutputEncoding=[Text.UTF8Encoding]::new();[Console]::Write($d.SelectedPath)}"
            result = subprocess.run(['powershell.exe', '-NoProfile', '-STA', '-Command', script], capture_output=True, timeout=120,
                creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode:
                raise ValueError('無法開啟資料夾選擇器，請貼上路徑。')
            return {'path': result.stdout.decode('utf-8', errors='replace').strip()}
        if op == 'scan_sd' and set(body) == {'operation'}:
            self.s.studio.discover()
            return self.state()
        if op == 'mount_sd' and set(body) == {'operation', 'path', 'installation', 'url', 'checkpoint'}:
            url = local_url(body['url'])
            if not isinstance(body['path'], str) or len(body['path']) > 2048 or not isinstance(body['checkpoint'], str):
                raise ValueError('請填入 SD 安裝資料夾路徑。')
            with self.s.lock, self.s.studio.lock:
                if any(j['status'] in ('queued', 'running') for j in self.s.studio.jobs.values()):
                    raise ValueError('生圖工作進行中，請完成後再切換掛載。')
                if body['path'].strip():
                    self.s.studio.discover(body['path'].strip())
                    root = Path(body['path'].strip()).expanduser().resolve()
                    folder = next(f for f in self.s.studio.folders if Path(f['path']) == root)
                else:
                    folder = next((f for f in self.s.studio.folders if f['id'] == body['installation']), None)
                    if not folder:
                        raise ValueError('請選擇安裝或加入 SD 資料夾。')
                checkpoint = body['checkpoint']
                if checkpoint and not any(r['id'] == checkpoint and folder['id'] in r['installations'] and r['category'] == 'checkpoint' and r['selectable'] for r in self.s.studio.resources.values()):
                    raise ValueError('底模不屬於所選 SD 安裝，請先掛載再選擇。')
                change = {'installation': folder['id'], 'backend': folder['backend'], 'url': url, 'checkpoint': checkpoint}
                if folder['id'] != self.s.studio.config['installation']:
                    change.update(vae='', control_model='', sampler='euler' if folder['backend'] == 'comfyui' else 'Euler')
                self.s.studio.configure(change)
            return {**self.state(), 'message': 'SD 路徑與網址已掛載，模型留在原資料夾；請測試連線。'}
        if op == 'test_sd' and set(body) == {'operation'}:
            self.s.studio.probe()
            result = self.state()
            result['message'] = result['sd']['service']['message']
            return result
        raise ValueError('未知連線設定操作')
