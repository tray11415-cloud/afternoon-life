from __future__ import annotations
import hashlib, json, tempfile, unittest
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from lifebox.pixel import PixelSession
from lifebox.model import Action
from lifebox.memory import VectorMemory, OllamaEmbedding
from lifebox.engine import Engine
from lifebox.play import play_world
from tests.test_play import FakeBackend

class PixelTests(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).resolve().parents[2]/'work'; root.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='pixel-test-',dir=root); self.now=100.0; self.backend=FakeBackend()
        self.session=PixelSession(Path(self.temp.name),self.backend,clock=lambda:self.now)
    def tearDown(self): self.session.close(); self.temp.cleanup()
    def act(self,command,**params): return self.session.act({'command':command,'params':params})
    def test_collision_and_no_client_teleport(self):
        """伺服器阻擋牆壁、穿人與假座標；走路不呼叫模型。"""
        space=self.session.space; p=space.entities['player']; p.update(x=3,y=7)
        self.act('step',direction='up'); self.assertEqual((p['x'],p['y']),(3,7))
        with self.assertRaises(ValueError): self.act('walk',x=1.5,y=2)
        with self.assertRaises(ValueError): self.act('move',location='room-01')
        self.assertEqual(self.backend.contexts,[])
    def test_far_dialogue_and_visibility_are_enforced(self):
        """隔空聊天不花費 API；同張地圖也只能感知近距離對話。"""
        self.act('talk',target='member-01',text='隔空呼叫')
        self.assertEqual(self.backend.contexts,[])
        space=self.session.space
        space.entities['member-02'].update(x=19,y=14)
        self.session._do('member-01',Action('say',{'target':None,'text':'只有附近的人聽見'}))
        self.assertIn('只有附近的人聽見',json.dumps(self.session.engine.view('member-02'),ensure_ascii=False))
        self.assertNotIn('只有附近的人聽見',json.dumps(self.session.screen(),ensure_ascii=False))
        self.assertNotIn('只有附近的人聽見',json.dumps(self.session.engine.view('member-03'),ensure_ascii=False))
    def test_portal_updates_authoritative_world(self):
        """走到實際門口才切換場景，所有房屋都有可達入口。"""
        space=self.session.space;p=space.entities['player'];p.update(x=4,y=7)
        self.act('step',direction='up')
        self.assertEqual(p['scene'],'room-01');self.assertEqual(self.session.engine.view('player')['self']['location'],'room-01')
        self.session.engine.advance();p.update(x=10,y=12);self.now+=1
        self.act('step',direction='down');self.assertEqual(p['scene'],'shared')
        for portal in space.maps['shared']['portals']:
            self.assertTrue(space.path('shared',(p['x'],p['y']),(portal['x'],portal['y']),'player'))
    def test_heartbeat_runs_offscreen_life_without_api(self):
        """本機時間推進、人物尋路和離場工作不需要逐幀付费呼叫。"""
        before=self.session.space.snapshot()
        for _ in range(560):
            self.now+=.3;self.act('pulse',focus=None)
        self.assertNotEqual(self.session.space.snapshot(),before)
        self.assertGreater(self.session.engine.tick,10)
        self.assertTrue(any(self.session.engine.view(a)['self']['goal']['progress']>0 for a in self.session.engine.agent_ids()))
        self.assertEqual(self.backend.contexts,[])
        self.session.engine.assert_consistent()
    def test_pixel_save_restores_path_position_and_branch(self):
        """讀檔與重啟一起恢復座標、未走完的路徑與世界；記憶不穿越分支。"""
        self.act('walk',x=18,y=16);self.act('save');before=self.session.space.snapshot()
        self.session.space.entities['player'].update(x=18,y=15)
        self.session._do('member-01',Action('say',{'target':'player','text':'存檔之後才說的未來秘密'}))
        self.session.memory.sync(self.session.engine)
        self.act('load');self.assertEqual(self.session.space.snapshot(),before)
        self.assertNotIn('未來秘密',json.dumps(self.session.memory.context(self.session.engine,'player','未來秘密'),ensure_ascii=False))
        restarted=PixelSession(Path(self.temp.name),self.backend,clock=lambda:self.now)
        try:self.assertEqual(restarted.space.snapshot(),before)
        finally:restarted.close()
    def test_close_dialogue_uses_only_one_agent_memory(self):
        """靠近後聊天只送收話角色的記憶，沒有全知世界或其他角色秘密。"""
        self.session.space.entities['player'].update(x=18,y=15)
        self.act('talk',target='member-01',text='今天有什麼打算？')
        context=self.backend.contexts[0]
        self.assertEqual(context['self']['id'],'member-01')
        self.assertNotIn('actors',context)
        self.assertTrue(any(e['data'].get('text')=='今天有什麼打算？' for e in context['memories']))
        self.assertLess(len(json.dumps(context,ensure_ascii=False).encode()),11000)
    def test_original_sprites_are_distinct(self):
        """十個人各有不同的四方向行走圖，並非一張圖換名字。"""
        root=Path(__file__).resolve().parents[1]/'web/assets'
        hashes=[hashlib.sha256((root/f'member-{i:02d}.png').read_bytes()).hexdigest() for i in range(1,11)]
        self.assertEqual(len(set(hashes)),10)
    def test_npc_conversation_uses_two_private_views(self):
        """像素場景的兩個角色用各自上下文交談，玩家旁觀不能讀取私話。"""
        space=self.session.space
        space.entities['member-01'].update(x=16,y=13)
        space.entities['member-02'].update(x=18,y=13)
        self.session._native_step();self.session._native_step()
        def paired(context,profile,trigger):
            self.backend.contexts.append(context)
            target=next(p['id'] for p in context['nearby'] if p['id']!='player')
            return Action('say',{'target':target,'text':'兩人的私人旅行計畫'})
        self.backend.decide=paired
        self.session._ai('member-01','自由活動')
        self.session._ai('member-02','另一位成員向你說話')
        self.assertEqual([v['self']['id'] for v in self.backend.contexts],['member-01','member-02'])
        self.assertNotIn('私人旅行計畫',json.dumps(self.session.screen(),ensure_ascii=False))
    def test_appointment_requires_physical_presence(self):
        """同在庭院但相隔很遠不算赴約，兩人實際靠近後才能開始。"""
        space=self.session.space;space.entities['player'].update(x=18,y=15)
        self.session._do('player',Action('invite',{'target':'member-01','start':2,'end':10,'location':'shared','purpose':'一起坐坐'}))
        inv=self.session.engine.view('player')['invitations'][0]
        self.session._do('member-01',Action('respond',{'invitation_id':inv['id'],'accept':True}))
        space.entities['player'].update(x=25,y=16);self.session.engine.advance(2)
        self.assertEqual(self.session.engine.view('player')['invitations'][0]['status'],'accepted')
        space.entities['player'].update(x=18,y=15);self.session.engine.advance()
        self.assertEqual(self.session.engine.view('player')['invitations'][0]['status'],'active')
    def test_environment_interaction_persists_and_adult_remains_off(self):
        """澆花改變可保存的場景狀態，成人指令仍停用，CG 無服務時明確提示。"""
        self.session.space.entities['player'].update(x=14,y=16)
        screen=self.act('interact',object='garden');self.assertTrue(screen['space']['watered_today'])
        self.act('save');self.act('reset');self.assertFalse(self.session.screen()['space']['watered_today'])
        self.act('load');self.assertTrue(self.session.screen()['space']['watered_today'])
        self.assertFalse(self.session.screen()['adult_enabled'])
        with self.assertRaises(ValueError):self.act('hentai')
        if self.session.renderer:self.session.renderer.close(wait=False);self.session.renderer=None
        self.session.studio.services[self.session.studio.config['url']]={'ready':False}
        self.assertIn('尚未連接',self.act('cg',target='member-01')['notice'])

class MemoryTests(unittest.TestCase):
    def test_vector_retrieval_is_owner_scoped_and_recalls_old_events(self):
        """舊對話可按主題檢索；SQLite 的私人記憶不跨角色共用。"""
        temp_root=Path(__file__).resolve().parents[2]/'work'; temp_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='memory-test-',dir=temp_root) as root:
            engine=Engine(play_world());memory=VectorMemory(Path(root)/'memory.sqlite3')
            engine.dispatch('member-01',Action('say',{'target':'member-02','text':'約好星期六去看櫻花與古董相機'}),'secret')
            engine.advance()
            for i in range(15):
                engine.dispatch('member-01',Action('say',{'target':'member-02','text':'今天第'+str(i)+'次提到午餐'}),str(i));engine.advance()
            context=memory.context(engine,'member-02','櫻花古董相機')
            self.assertIn('櫻花與古董相機',json.dumps(context,ensure_ascii=False))
            self.assertNotIn('櫻花與古董相機',json.dumps(memory.context(engine,'member-03','櫻花古董相機'),ensure_ascii=False))
            restarted=VectorMemory(Path(root)/'memory.sqlite3')
            self.assertTrue(restarted.retrieve(engine,'member-02','櫻花古董相機'))
    def test_local_embedding_adapter_rejects_remote_provider(self):
        """本機語意嵌入接口拒絕外部主機，避免把私人記憶意外送到雲端。"""
        with self.assertRaises(ValueError):OllamaEmbedding('https://remote.test','embedding-model')
    def test_local_embedding_http_contract(self):
        """本機嵌入服務的請求格式和向量正規化經 HTTP 驗證，不假裝真實模型已安裝。"""
        received=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_POST(self):
                received.append((self.path,json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                raw=json.dumps({'embeddings':[[3,4,0,0,0,0,0,0]]}).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            embedding=OllamaEmbedding(f'http://127.0.0.1:{server.server_port}','fixture-embed')
            vector=embedding.embed('只有本機服務接收的記憶')
            self.assertEqual(received,[('/api/embed',{'model':'fixture-embed','input':'只有本機服務接收的記憶'})])
            self.assertAlmostEqual(vector[0],.6);self.assertAlmostEqual(vector[1],.8)
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
