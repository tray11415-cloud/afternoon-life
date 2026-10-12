from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from lifebox.model import Action
from lifebox.play import PlaySession, make_server
from lifebox.xai import AIError, XAIBackend


class FakeBackend:
    def __init__(self, action=None):
        self.contexts = []
        self.action = action

    def decide(self, context, profile, trigger):
        self.contexts.append(context)
        if self.action:
            return self.action
        if trigger == '玩家邀約':
            pending = next(inv for inv in context['invitations'] if inv['recipient'] == context['self']['id'] and inv['status'] == 'pending')
            return Action('respond', {'invitation_id': pending['id'], 'accept': True})
        return Action('say', {'target': 'player' if any(p['id'] == 'player' for p in context['nearby']) else None,
                              'text': '我先把今天的事情做好，再一起聊聊。'})

    def stats(self):
        return {'model': 'fixture-only', 'calls': len(self.contexts), 'successes': len(self.contexts),
                'estimated_usd': 0, 'uncertain_usd': 0}


class PlayTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[2] / 'work'
        root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='play-test-', dir=root)
        self.backend = FakeBackend()
        self.session = PlaySession(Path(self.temp.name), self.backend)

    def tearDown(self):
        self.temp.cleanup()

    def act(self, command, **params):
        return self.session.act({'command': command, 'params': params})

    def test_player_talk_uses_recipient_view(self):
        """玩家聊天只把收話角色自己的視角送入模型，回覆經世界裁定。"""
        screen = self.act('talk', target='member-01', text='今天想做什麼？')
        context = self.backend.contexts[0]
        self.assertEqual(context['self']['id'], 'member-01')
        self.assertNotIn('actors', context)
        self.assertTrue(any(e['kind'] == 'message_spoken' and e['actor'] == 'player' for e in context['memories']))
        self.assertTrue(any(e['kind'] == 'message_spoken' and e['actor'] == 'member-01' for e in screen['events']))

    def test_screen_hides_offscreen_private_state(self):
        """畫面不洩漏遠處角色的位置、工作目標與私人記憶；成人入口停用。"""
        screen = self.session.screen()
        self.assertFalse(screen['adult_enabled'])
        for person in screen['roster']:
            self.assertNotIn('goal', person)
            self.assertNotIn('memories', person)
            self.assertNotIn('location', person)
        self.assertNotIn('api_key', json.dumps(screen))

    def test_agent_can_choose_work_instead_of_reply(self):
        """角色可以先工作，產生真實工作狀態而非虛構台詞。"""
        self.backend.action = Action('work', {'minutes': 3})
        screen = self.act('talk', target='member-01', text='來聊聊？')
        self.assertEqual(self.session.engine.view('member-01')['self']['activity'], 'working')
        self.assertFalse(any(e['kind'] == 'message_spoken' and e['actor'] == 'member-01' for e in screen['events']))

    def test_invitation_has_real_acceptance(self):
        """邀約的接受與赴約由引擎處理，不是口頭答應。"""
        screen = self.act('invite', target='member-01')
        self.assertEqual(screen['invitations'][0]['status'], 'accepted')
        self.session._native_step()
        self.session._native_step()
        self.assertEqual(self.session.screen()['invitations'][0]['status'], 'active')

    def test_save_load_and_restart_keep_world(self):
        """手動讀檔與程序重啟可重建相同世界；用量留在獨立後端。"""
        self.act('talk', target='member-01', text='記得這一句。')
        self.act('save')
        before = self.session.engine.export_state()
        self.act('move', location='room-01')
        self.act('load')
        self.assertEqual(self.session.engine.export_state(), before)
        self.assertEqual(PlaySession(Path(self.temp.name), self.backend).engine.export_state(), before)

    def test_no_cloud_calls_for_movement_save_or_state(self):
        """查看畫面、移動及存檔不產生模型費用。"""
        self.session.screen()
        self.act('move', location='room-01')
        self.act('save')
        self.assertEqual(self.backend.contexts, [])

    def test_no_secret_remote_speech_in_player_feed(self):
        """玩家不在場的兩名角色對話不會出現在玩家畫面。"""
        engine = self.session.engine
        engine.dispatch('member-04', Action('move', {'location': 'shared'}), 'a')
        engine.advance()
        engine.dispatch('member-04', Action('say', {'target': 'member-02', 'text': '這是一段私人對話'}), 'b')
        self.assertNotIn('這是一段私人對話', json.dumps(self.session.screen(), ensure_ascii=False))

    def test_npc_pair_has_two_separate_contexts(self):
        """自主角色向同場成員說話時，對方獨立回應，私人台詞不洩漏給玩家。"""
        def paired(context, profile, trigger):
            self.backend.contexts.append(context)
            target = next(person['id'] for person in context['nearby'] if person['id'] != 'player')
            return Action('say', {'target': target, 'text': '只告訴妳的私下話題。'})
        self.backend.decide = paired
        screen = self.act('wait', minutes=2)
        self.assertEqual(len(self.backend.contexts), 2)
        first, second = self.backend.contexts
        self.assertNotEqual(first['self']['id'], second['self']['id'])
        self.assertTrue(any(e['kind'] == 'message_spoken' and e['actor'] == first['self']['id'] for e in second['memories']))
        self.assertNotIn('只告訴妳的私下話題', json.dumps(screen, ensure_ascii=False))

    def test_invalid_and_adult_commands_rejected(self):
        """不存在的成人與生圖指令、冒用角色及非法行動不會被執行。"""
        for command in ('hentai', 'cg', 'import_asset', 'become_agent'):
            with self.assertRaises(ValueError):
                self.act(command)
        with self.assertRaises(ValueError):
            self.act('wait', minutes=9999)

    def test_backend_failure_does_not_fabricate_reply(self):
        """API 失敗會明確顯示錯誤，不用假台詞補上。"""
        def fail(*args):
            raise AIError('credits')
        self.backend.decide = fail
        screen = self.act('talk', target='member-01', text='你好')
        self.assertEqual(screen['error']['code'], 'credits')
        self.assertFalse(any(e['kind'] == 'message_spoken' and e['actor'] == 'member-01' for e in screen['events']))

    def test_local_server_blocks_cross_origin_and_file_access(self):
        """本機介面阻擋跨來源操作，沒有私人檔案及成人路由。"""
        server = make_server(self.session, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(base + '/api/state') as response:
                token = json.load(response)['token']
            with self.assertRaises(HTTPError) as failure:
                urlopen(Request(base + '/api/action', data=b'{"command":"save","params":{}}',
                                headers={'Content-Type': 'application/json', 'X-Play-Token': token, 'Origin': 'https://other.test'}))
            self.assertEqual(failure.exception.code, 403)
            for route in ('/work/private/xai.dpapi', '/api/hentai', '/../../AGENTS.md'):
                with self.assertRaises(HTTPError) as failure:
                    urlopen(base + route)
                self.assertEqual(failure.exception.code, 404)
            with urlopen(Request(base + '/api/action', data=b'{"command":"save","params":{}}',
                                 headers={'Content-Type': 'application/json', 'X-Play-Token': token, 'Origin': base})) as response:
                self.assertTrue(json.load(response)['has_save'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


class XAITests(unittest.TestCase):
    def test_dialogue_and_activity_share_budget_and_use_own_prices(self):
        """聊天用 4.3、行動用便宜模型；兩者共用跨重啟額度並按各自價格計費。"""
        captured = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                captured.append(body)
                response = {'model':body['model'],'choices':[{'finish_reason':'stop','message':{'content':'{"kind":"wait","params":{}}'}}],
                            'usage':{'prompt_tokens':100,'completion_tokens':20,'prompt_tokens_details':{'cached_tokens':10}}}
                data = json.dumps(response).encode()
                self.send_response(200); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        root = Path(__file__).resolve().parents[2] / 'work'; root.mkdir(exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(prefix='routing-test-', dir=root) as temporary:
                path = Path(temporary) / 'usage.json'
                backend = XAIBackend('fixture-key', path, endpoint=f'http://127.0.0.1:{server.server_port}',
                                     max_calls=2, dialogue_model='grok-4.3')
                context = {'self':{'id':'member-06'}, 'tick':0, 'nearby':[], 'memories':[]}
                backend.decide(context, trigger='自由活動')
                backend.decide(context, trigger='玩家說話')
                self.assertEqual([body['model'] for body in captured], ['grok-build-0.1', 'grok-4.3'])
                self.assertEqual(captured[1]['reasoning_effort'], 'none')
                self.assertEqual(json.loads(captured[1]['messages'][1]['content'])['context'], context)
                self.assertAlmostEqual(backend.stats()['estimated_usd'], .0002965)
                restarted = XAIBackend('fixture-key', path, endpoint=backend.endpoint, max_calls=2, dialogue_model='grok-4.3')
                with self.assertRaises(AIError) as failure:
                    restarted.decide(context, trigger='另一位成員向你說話')
                self.assertEqual(str(failure.exception), 'budget')
                self.assertEqual(len(captured), 2)
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_autonomous_npc_pair_both_speak_with_dialogue_model(self):
        """自主開口與收話角色都用 4.3；各請求只有各自視角，私人對話不出現在玩家畫面。"""
        captured = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                captured.append(body)
                context = json.loads(body['messages'][1]['content'])['context']
                target = next(person['id'] for person in context['nearby'] if person['id'] != 'player')
                text = '便宜模型草稿' if body['model'] == 'grok-build-0.1' else '4.3 私人台詞'
                action = {'kind':'say', 'params':{'target':target, 'text':text}}
                response = {'model':body['model'],'choices':[{'finish_reason':'stop','message':{'content':json.dumps(action)}}],
                            'usage':{'prompt_tokens':100,'completion_tokens':20}}
                data = json.dumps(response).encode()
                self.send_response(200); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        root = Path(__file__).resolve().parents[2] / 'work'; root.mkdir(exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(prefix='routing-test-', dir=root) as temporary:
                backend = XAIBackend('fixture-key', Path(temporary)/'usage.json', endpoint=f'http://127.0.0.1:{server.server_port}', dialogue_model='grok-4.3')
                session = PlaySession(Path(temporary)/'world', backend)
                screen = session.act({'command':'wait', 'params':{'minutes':2}})
                self.assertEqual([body['model'] for body in captured], ['grok-build-0.1','grok-4.3','grok-4.3'])
                contexts = [json.loads(body['messages'][1]['content'])['context'] for body in captured]
                self.assertEqual(contexts[0]['self']['id'], contexts[1]['self']['id'])
                self.assertNotEqual(contexts[1]['self']['id'], contexts[2]['self']['id'])
                self.assertNotIn('4.3 私人台詞', json.dumps(screen, ensure_ascii=False))
                self.assertNotIn('便宜模型草稿', json.dumps(session.engine.journal(), ensure_ascii=False))
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_missing_requested_chat_model_has_no_fallback(self):
        """帳號不能使用指定的 4.3 時明確失敗，不默默換成便宜模型。"""
        root = Path(__file__).resolve().parents[2] / 'work'; root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='routing-test-', dir=root) as temporary:
            backend = XAIBackend('fixture-key', Path(temporary)/'usage.json', dialogue_model='grok-4.3')
            backend._request = lambda route: {'data':[{'id':'grok-build-0.1'}]}
            with self.assertRaises(AIError) as failure:
                backend.select_model()
            self.assertEqual(str(failure.exception), 'model_unavailable')
            self.assertEqual(backend.stats()['calls'], 0)

    def test_real_http_contract_budget_and_ledger_restart(self):
        """xAI 格式、token 費用、次數上限與跨重啟用量，以本機伺服器验证。"""
        captured = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_POST(self):
                captured.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                response = {'model':'grok-build-0.1','choices':[{'finish_reason':'stop','message':{'content':'{"kind":"wait","params":{}}'}}],
                            'usage':{'prompt_tokens':100,'completion_tokens':20,'prompt_tokens_details':{'cached_tokens':10}}}
                data = json.dumps(response).encode()
                self.send_response(200); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        root = Path(__file__).resolve().parents[2] / 'work'; root.mkdir(exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(prefix='xai-test-', dir=root) as temporary:
                path = Path(temporary) / 'usage.json'
                backend = XAIBackend('test-secret', path, endpoint=f'http://127.0.0.1:{server.server_port}', max_calls=1)
                context = {'self': {'id':'member-07'}, 'tick':0, 'nearby':[], 'memories':[]}
                self.assertEqual(backend.decide(context).kind, 'wait')
                self.assertEqual(json.loads(captured[0]['messages'][1]['content'])['context'], context)
                self.assertNotIn('test-secret', json.dumps(captured))
                self.assertAlmostEqual(backend.stats()['estimated_usd'], .000132)
                reloaded = XAIBackend('test-secret', path, endpoint=backend.endpoint, max_calls=1)
                with self.assertRaises(AIError) as failure:
                    reloaded.decide(context)
                self.assertEqual(str(failure.exception), 'budget')
                self.assertEqual(len(captured), 1)
                self.assertNotIn('test-secret', path.read_text())
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_errors_do_not_echo_provider_secrets(self):
        """供應商錯誤不回傳原始內容或敏感資訊。"""
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(401); self.end_headers(); self.wfile.write(b'secret-token-and-private-provider-details')
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        root = Path(__file__).resolve().parents[2] / 'work'; root.mkdir(exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(prefix='xai-test-', dir=root) as temporary:
                backend = XAIBackend('secret-token', Path(temporary)/'usage.json', endpoint=f'http://127.0.0.1:{server.server_port}')
                with self.assertRaises(AIError) as failure:
                    backend.decide({'self':{'id':'member-01'}})
                self.assertEqual(str(failure.exception), 'unauthorized')
                self.assertNotIn('secret-token', str(failure.exception))
        finally:
            server.shutdown(); server.server_close(); thread.join()
