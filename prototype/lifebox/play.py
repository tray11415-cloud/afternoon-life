"""Local playable slice: one human, ten private agent views, no adult media routes."""
from __future__ import annotations

import argparse
import os
import socket
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .engine import Engine
from .fixtures import neutral_world
from .model import Action
from .storage import load, save
from .xai import AIError, DIALOGUE_TRIGGERS, ERRORS, XAIBackend, read_key

NAMES = ['曉晴', '雨澄', '以寧', '若涵', '季夏', '庭羽', '知秋', '映彤', '芷禾', '書瑤']
VOICES = ['爽快直接，喜歡動手做東西。', '慢熱，重視準時與承諾。', '話少，常從音樂想到事情。',
          '溫柔但不會無條件答應別人。', '好奇，喜歡小冒險。', '愛開輕鬆玩笑，遇到正事很認真。',
          '觀察細膩，習慣先聽再說。', '有主見，不喜歡被替自己做決定。', '隨和，珍惜安靜的時間。', '務實，會記得別人答應過的事。']
GOALS = ['完成手作草稿', '整理這週的帳目', '寫完一段旋律', '整理工作筆記', '安排週末行程',
         '準備明天的資料', '整理拍攝照片', '完成練習計畫', '照顧窗邊植物', '讀完手邊的書']
PEOPLE = {f'member-{i+1:02d}': {'id': f'member-{i+1:02d}', 'name': name, 'age': 25,
                              'profile': VOICES[i]} for i, name in enumerate(NAMES)}
LOCATION_NAMES = {'shared': '公共庭院', **{f'room-{i+1:02d}': f'{name}的家' for i, name in enumerate(NAMES)}}
ACTIVITIES = {'idle': '休息中', 'working': '處理自己的事', 'moving': '走動中', 'talking': '交談中', 'meeting': '赴約中', 'gathering':'共同活動中'}
REASONS = {'actor_busy': '現在還在忙，等一會兒再試。', 'target_not_here': '她已經離開這裡了。',
           'commitment_conflict': '這個時段已經有其他安排。', 'invalid_path': '目前不能直接走到那裡。',
           'invitation_closed': '這個邀約已經結束。', 'goal_complete': '手邊的事情已經完成。'}


def play_world():
    world = neutral_world()
    for i, actor in enumerate(world['actors'][:-1]):
        actor['name'] = NAMES[i]
        actor['goal'] = {'title': GOALS[i], 'target': 8 + i}
        if i < 3:
            actor['location'] = 'shared'
    return world


class PlaySession:
    def __init__(self, root: Path, backend):
        self.root, self.backend = Path(root), backend
        self.root.mkdir(parents=True, exist_ok=True)
        self.auto_path, self.manual_path = self.root / 'autosave.json', self.root / 'save.json'
        self.engine = load(self.auto_path) if self.auto_path.exists() else Engine(play_world())
        self.lock = threading.RLock()
        self.error, self.notice = None, None
        self._native_serial = 0
        self._save()

    def _save(self):
        save(self.engine, self.auto_path)

    def _do(self, actor, action):
        return self.engine.dispatch(actor, action, 'play:' + secrets.token_hex(12), expected_tick=self.engine.tick)

    def _native_step(self, exempt=()):
        """Schedules own work/travel. Social decisions are exclusively agent/model decisions."""
        tick = self.engine.tick
        for index, actor_id in enumerate(self.engine.agent_ids()):
            if actor_id in exempt:
                continue
            view = self.engine.view(actor_id, memory_limit=12)
            own = view['self']
            if own['busy_until'] > tick:
                continue
            accepted = [inv for inv in view['invitations'] if inv['status'] == 'accepted']
            if accepted:
                plan = min(accepted, key=lambda inv: inv['start'])
                if own['location'] != plan['location']:
                    destination = plan['location'] if plan['location'] in view['paths'] else 'shared'
                    action = Action('move', {'location': destination})
                else:
                    continue  # Do not reserve a wait tick that prevents the appointment starting.
            else:
                goal = own['goal']
                home = f'room-{index+1:02d}'
                if goal['progress'] < goal['target'] and (tick + index) % 12 >= 4:
                    if own['location'] != home:
                        destination = home if home in view['paths'] else 'shared'
                        action = Action('move', {'location': destination})
                    else:
                        minutes = min(3, goal['target'] - goal['progress'])
                        action = Action('work', {'minutes': minutes})
                elif own['location'] != 'shared':
                    action = Action('move', {'location': 'shared'})
                else:
                    continue
            self._do(actor_id, action)
        self.engine.advance()

    def _ai(self, actor_id, trigger):
        view = self.engine.view(actor_id, memory_limit=14)
        if view['self']['busy_until'] > view['tick']:
            self.notice = f"{PEOPLE[actor_id]['name']}正在忙自己的事。可以等一會兒。"
            return None
        try:
            action = self.backend.decide(view, PEOPLE[actor_id]['profile'], trigger)
            if action.kind == 'say' and trigger not in DIALOGUE_TRIGGERS and getattr(self.backend, 'dialogue_model', None):
                action = self.backend.express(view, PEOPLE[actor_id]['profile'], action)
            outcome = self.engine.dispatch(actor_id, action, 'ai:' + secrets.token_hex(12),
                                           expected_revision=view['revision'], expected_tick=view['tick'])
            if not outcome.accepted:
                self.notice = '角色提出的行動暫時無法執行：' + REASONS.get(outcome.reason, '時間或地點不符。')
            elif action.kind != 'say':
                phrases = {'wait': '暫時沒有接話。', 'work': '選擇先處理自己的事。',
                           'move': '決定離開這裡。', 'invite': '提出了新的邀約。', 'respond': '回應了邀約。'}
                self.notice = PEOPLE[actor_id]['name'] + phrases.get(action.kind, '做出了自己的決定。')
            return action if outcome.accepted else None
        except AIError as exc:
            self.error = {'code': str(exc), 'message': ERRORS.get(str(exc), 'AI 暫時無法回應。')}
            return None

    def screen(self):
        with self.lock:
            view = self.engine.view('player', memory_limit=100)
            # Only public identity and player-observed presence; never remote locations/goals.
            nearby = {actor['id']: actor for actor in view['nearby']}
            from .characters import public_identity
            roster = [{**public_identity(self.engine,actor_id), 'here': actor_id in nearby,
                       'activity': ACTIVITIES.get(nearby.get(actor_id, {}).get('activity'), '目前不在這裡')}
                      for actor_id, spec in PEOPLE.items()]
            events = [event for event in view['memories'] if event['kind'] in
                      {'message_spoken', 'actor_moved', 'work_started', 'work_completed', 'invitation_created', 'invitation_status'}]
            return {'tick': view['tick'], 'revision': view['revision'], 'location': view['self']['location'],
                    'location_name': LOCATION_NAMES.get(view['self']['location'],view['self']['location']),
                    'location_names': LOCATION_NAMES.copy(),
                    'paths': [{'id': place, 'name': LOCATION_NAMES.get(place,place)} for place in view['paths']],
                    'roster': roster, 'nearby': view['nearby'], 'events': events,
                    'invitations': view['invitations'], 'usage': self.backend.stats(),
                    'error': self.error, 'notice': self.notice, 'adult_enabled': False,
                    'has_save': self.manual_path.exists()}

    def act(self, body):
        if not isinstance(body, dict) or set(body) != {'command', 'params'} or not isinstance(body['params'], dict):
            raise ValueError('invalid command')
        command, params = body['command'], body['params']
        with self.lock:
            self.error, self.notice = None, None
            if command in {'talk', 'invite'}:
                expected = {'target', 'text'} if command == 'talk' else {'target'}
                if set(params) != expected or params.get('target') not in PEOPLE:
                    raise ValueError('invalid target')
                target = params['target']
                if command == 'talk':
                    text = params['text']
                    if not isinstance(text, str) or not text.strip() or len(text) > 800:
                        raise ValueError('invalid text')
                    action = Action('say', {'target': target, 'text': text.strip()})
                else:
                    action = Action('invite', {'target': target, 'start': self.engine.tick + 4,
                                              'end': self.engine.tick + 7, 'location': 'shared', 'purpose': '在庭院一起坐坐'})
                outcome = self._do('player', action)
                if outcome.accepted:
                    self._native_step(exempt=(target,))
                    self._ai(target, '玩家說話' if command == 'talk' else '玩家邀約')
                    self.engine.advance()
                else:
                    self.notice = REASONS.get(outcome.reason, '這個行動目前無法執行。')
            elif command == 'move':
                if set(params) != {'location'} or params['location'] not in LOCATION_NAMES:
                    raise ValueError('invalid location')
                result = self._do('player', Action('move', params))
                if result.accepted:
                    self._native_step()
                else:
                    self.notice = REASONS.get(result.reason, '目前無法移動。')
            elif command == 'wait':
                if set(params) != {'minutes'} or type(params['minutes']) is not int or not 1 <= params['minutes'] <= 10:
                    raise ValueError('invalid minutes')
                # One autonomous decision; speech and recipient response may add chat calls.
                for _ in range(params['minutes']):
                    self._native_step()
                ids = list(self.engine.agent_ids())
                pivot = (self.engine.tick // 2) % len(ids)
                order = ids[pivot:] + ids[:pivot]
                candidates = [actor for actor in order if self.engine.view(actor)['self']['busy_until'] <= self.engine.tick]
                pending = [actor for actor in candidates if any(inv['status'] == 'pending' and inv['recipient'] == actor
                          for inv in self.engine.view(actor)['invitations'])]
                if candidates:
                    actor = (pending or candidates)[0]
                    action = self._ai(actor, '自由活動')
                    if action and action.kind in {'say', 'invite'} and action.params.get('target') in PEOPLE:
                        recipient = action.params['target']
                        self._ai(recipient, '另一位成員邀約' if action.kind == 'invite' else '另一位成員向你說話')
                self.engine.advance()
            elif command == 'respond':
                if set(params) != {'invitation_id', 'accept'} or type(params['accept']) is not bool:
                    raise ValueError('invalid response')
                result = self._do('player', Action('respond', params))
                if result.accepted:
                    self._native_step()
                else:
                    self.notice = REASONS.get(result.reason, '目前無法回應邀約。')
            elif command in {'save', 'load', 'reset'}:
                if params:
                    raise ValueError('invalid params')
                if command == 'save':
                    save(self.engine, self.manual_path)
                    self.notice = '已存檔。'
                elif command == 'load':
                    if self.manual_path.exists():
                        self.engine = load(self.manual_path)
                        self.notice = '已讀取存檔；API 用量不會回退。'
                    else:
                        self.notice = '還沒有手動存檔。'
                else:
                    self.engine = Engine(play_world())
                    self.notice = '重新開始；API 用量不會回退。'
            else:
                raise ValueError('unknown command')
            self.engine.assert_consistent()
            self._save()
            return self.screen()


def make_server(session, port=8765):
    token = secrets.token_urlsafe(32)
    static = Path(__file__).resolve().parent.parent / 'web'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def _send(self, status, data, content_type='application/json; charset=utf-8'):
            if isinstance(data, dict):
                data = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-src https://video.blender.org http://127.0.0.1:* http://localhost:*; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(data)

        def _host_ok(self):
            expected = f'127.0.0.1:{self.server.server_port}'
            return self.headers.get('Host') == expected

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, {'error': 'local_only'})
            path = urlsplit(self.path).path
            if path == '/api/state':
                return self._send(200, {**session.screen(), 'token': token})
            if path in {'/api/components','/api/components/schema'} and hasattr(session,'components'):
                if not secrets.compare_digest(self.headers.get('X-Play-Token',''),token):return self._send(403,{'error':'local_only'})
                return self._send(200,session.components.schema() if path.endswith('/schema') else session.components.state())
            if path.startswith('/component-art/') and hasattr(session,'components'):
                asset=session.components.asset(path.removeprefix('/component-art/'))
                if asset:return self._send(200,asset.read_bytes(),'image/png')
                return self._send(404,{'error':'not_found'})
            if path == '/api/groups' and hasattr(session,'social'):
                if not secrets.compare_digest(self.headers.get('X-Play-Token',''),token):return self._send(403,{'error':'local_only'})
                return self._send(200,session.social.planner())
            if path == '/api/characters' and hasattr(session,'character_setup'):
                if not secrets.compare_digest(self.headers.get('X-Play-Token',''),token):return self._send(403,{'error':'local_only'})
                return self._send(200,session.character_setup.state(session))
            if path == '/api/preferences' and hasattr(session,'preferences'):
                if not secrets.compare_digest(self.headers.get('X-Play-Token',''),token):return self._send(403,{'error':'local_only'})
                return self._send(200,session.preferences.state())
            if path == '/api/art' and hasattr(session,'studio'):
                if not secrets.compare_digest(self.headers.get('X-Play-Token',''),token):return self._send(403,{'error':'local_only'})
                return self._send(200,session.studio.state())
            if path == '/api/speech' and hasattr(session,'speech'):
                if not secrets.compare_digest(self.headers.get('X-Play-Token',''),token):return self._send(403,{'error':'local_only'})
                return self._send(200,session.speech.state())
            if path.startswith('/speech-audio/') and hasattr(session,'speech'):
                if not secrets.compare_digest(self.headers.get('X-Play-Token',''),token):return self._send(403,{'error':'local_only'})
                asset=session.speech.asset(path.removeprefix('/speech-audio/'))
                if asset:return self._send(200,asset.read_bytes(),'audio/wav')
                return self._send(404,{'error':'not_found'})
            if path.startswith('/look-art/') and hasattr(session,'look_studio'):
                asset=session.look_studio.asset(path.removeprefix('/look-art/'))
                if asset:return self._send(200,asset.read_bytes(),'image/png')
                return self._send(404,{'error':'not_found'})
            if path.startswith('/character-art/') and hasattr(session,'studio'):
                asset=session.studio.asset(path.removeprefix('/character-art/'))
                if asset:return self._send(200,asset.read_bytes(),'image/png')
                return self._send(404,{'error':'not_found'})
            if path.startswith('/custom-art/') and hasattr(session,'art_assets'):
                asset=session.art_assets.asset(path.removeprefix('/custom-art/'))
                if asset:return self._send(200,asset.read_bytes(),'image/png')
                return self._send(404,{'error':'not_found'})
            files = {'/': ('index.html', 'text/html; charset=utf-8'),
                     '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                     '/engine.js': ('engine.js', 'text/javascript; charset=utf-8'),
                     '/style.css': ('style.css', 'text/css; charset=utf-8'),
                     '/art-settings.js': ('art-settings.js','text/javascript; charset=utf-8'),
                     '/social-settings.js': ('social-settings.js','text/javascript; charset=utf-8'),
                     '/speech-settings.js': ('speech-settings.js','text/javascript; charset=utf-8'),'/life-settings.js':('life-settings.js','text/javascript; charset=utf-8'),'/component-settings.js':('component-settings.js','text/javascript; charset=utf-8'),'/i18n.js':('i18n.js','text/javascript; charset=utf-8'),'/locales.json':('locales.json','application/json; charset=utf-8'),'/simplified.json':('simplified.json','application/json; charset=utf-8'),'/menu.js':('menu.js','text/javascript; charset=utf-8'),'/maker.js':('maker.js','text/javascript; charset=utf-8'),'/studio.css':('studio.css','text/css; charset=utf-8')}
            # Public packaged art only. No arbitrary paths, private saves or keys.
            for asset in (static / 'assets').glob('*'):
                if asset.name in {'maps.json','KENNEY-LICENSE.txt','LPC-CREDITS.txt','LPC-LICENSE.txt'} or asset.suffix == '.png':
                    files['/assets/' + asset.name] = ('assets/' + asset.name,
                        'image/png' if asset.suffix == '.png' else 'application/json; charset=utf-8' if asset.suffix == '.json' else 'text/plain; charset=utf-8')
            if path.startswith('/cg/') and hasattr(session, 'cg_root') and session.renderer:
                name = path[4:]
                allowed = {job.get('asset_id') + '.png' for job in session.renderer.visible_jobs('player') if job.get('status') == 'ready'}
                if name in allowed:
                    return self._send(200, (session.cg_root / name).read_bytes(), 'image/png')
            if path not in files:
                return self._send(404, {'error': 'not_found'})
            file, mime = files[path]
            return self._send(200, (static / file).read_bytes(), mime)

        def do_POST(self):
            origin = f'http://127.0.0.1:{self.server.server_port}'
            if not self._host_ok() or self.headers.get('Origin') != origin or not secrets.compare_digest(self.headers.get('X-Play-Token', ''), token):
                return self._send(403, {'error': 'local_only'})
            route=urlsplit(self.path).path
            if route not in {'/api/action','/api/art','/api/characters','/api/speech','/api/components','/api/preferences'}:
                return self._send(404, {'error': 'not_found'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= (6291456 if route in {'/api/art','/api/components'} else 131072 if route=='/api/characters' else 65536 if route=='/api/speech' else 8192) or self.headers.get('Content-Type') != 'application/json':
                    raise ValueError('invalid body')
                body = json.loads(self.rfile.read(size))
                if route=='/api/preferences':
                    with session.lock:return self._send(200,session.preferences.configure(body))
                if route=='/api/components':return self._send(200,session.components.operation(body))
                if route=='/api/characters':
                    if isinstance(body,dict) and body.get('operation') in {'preview_look','draft'}:
                        from .characters import validate_profile,default_profile
                        expected={'operation','actor','profile'}|({'brief'} if body['operation']=='draft' else set())
                        if set(body)!=expected or body['actor'] not in session.character_setup.profiles:raise ValueError('無效人物草稿')
                        profile={**default_profile(body['actor']),**validate_profile(body['profile'])}
                        from .looks import validate_look
                        profile['look']=validate_look(profile.get('look'),body['actor'])
                        if body['operation']=='preview_look':
                            with session.lock:return self._send(200,session.look_studio.preview(body['actor'],profile))
                        if not isinstance(body['brief'],str) or not 1<=len(body['brief'].strip())<=800:raise ValueError('請用800字內描述人物方向')
                        if hasattr(session.backend,'draft_character'):
                            draft=session.backend.draft_character(profile,body['brief'],session.preferences.config['language']);source='model'
                        else:
                            draft={**profile,'goal':body['brief'].strip()[:100]};source='offline-example'
                        return self._send(200,{'profile':draft,'source':source,'applied':False,'usage':session.backend.stats()})
                    if isinstance(body,dict) and set(body)=={'operation','actor','profile','before'} and body['operation']=='prepare_current':
                        return self._send(200,session.character_setup.prepare_current(session,body['actor'],body['profile'],body['before']))
                    if not isinstance(body,dict) or set(body)!={'profiles'}:raise ValueError('無效創角模板')
                    with session.lock:
                        session.character_setup.configure(body['profiles'])
                        return self._send(200,session.character_setup.state(session))
                if route=='/api/art':return self._send(200,session.art_action(body))
                if route=='/api/speech':return self._send(200,session.speech_action(body))
                return self._send(200, {**session.act(body), 'token': token})
            except AIError as exc:
                return self._send(400,{'error':str(exc),'message':ERRORS.get(str(exc),'AI 草稿暫時無法生成。')})
            except (ValueError, TypeError, KeyError, UnicodeError) as exc:
                return self._send(400, {'error':'invalid_request','message':str(exc)[:250] if route in {'/api/art','/api/characters','/api/speech','/api/components'} else '請檢查這次行動的內容。'})
            except Exception:
                return self._send(500, {'error': 'internal', 'message': '行動暫時無法完成，請重新整理。'})
    class LocalServer(ThreadingHTTPServer):
        allow_reuse_address=False
        def server_bind(self):
            if os.name=='nt' and hasattr(socket,'SO_EXCLUSIVEADDRUSE'):
                self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            super().server_bind()
    return LocalServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--demo',action='store_true',help='Offline rules; no key or paid calls')
    parser.add_argument('--data-dir',type=Path,help='Separate save directory')
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[2]
    demo=args.demo or not (os.environ.get('XAI_API_KEY') or (project/'work/private/xai.dpapi').is_file())
    if demo:
        from .demo_backend import DemoBackend
        backend=DemoBackend()
    else:
        backend = XAIBackend(read_key(project / 'work/private/xai.dpapi'), project / 'work/play-usage.json',dialogue_model='grok-4.3')
        backend.select_model()
    from .pixel import PixelSession
    session = PixelSession(args.data_dir or project / 'work'/('demo-play' if demo else 'play'), backend)
    server = make_server(session, args.port)
    print(json.dumps({'url': f'http://127.0.0.1:{server.server_port}', 'model': backend.model,
                      'dialogue_model': backend.dialogue_model, 'adult_enabled': False}), flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
