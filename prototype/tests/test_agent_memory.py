from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
from lifebox.engine import Engine
from lifebox.memory import VectorMemory
from lifebox.model import Action
from lifebox.play import play_world
from lifebox.xai import XAIBackend, AIError
from tests.test_pixel import PixelTests

TEMP_ROOT=Path(__file__).resolve().parents[2]/'work'
TEMP_ROOT.mkdir(exist_ok=True)

class EpisodeMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=TEMP_ROOT);self.path=Path(self.temp.name)/'memory.sqlite3'
        self.engine=Engine(play_world());self.memory=VectorMemory(self.path)
    def tearDown(self):self.temp.cleanup()
    def say(self,text,speaker='member-01',target='member-02'):
        result=self.engine.dispatch(speaker,Action('say',{'target':target,'text':text}),str(self.engine.revision))
        self.assertTrue(result.accepted);self.engine.advance()
    def hit(self,query,owner='member-02'):
        return self.memory.ranked(self.engine,owner,query,limit=1)[0]

    def test_concrete_old_memory_survives_noise_and_is_not_shared(self):
        """具體舊事在大量無關對話後仍可想起，別人查同主題不能取得私話。"""
        self.say('星期六早上九點在櫻花橋拍古董相機。')
        for i in range(25):self.say('午餐吃豆腐與青菜。')
        hit=self.hit('櫻花橋古董相機')
        self.assertIn('九點',hit['event']['data']['text'])
        self.assertEqual(hit['signals']['evidence'],'statement_not_verified_fact')
        self.assertEqual(self.memory.retrieve(self.engine,'member-03','櫻花橋古董相機'),[])
        self.assertEqual(self.memory.retrieve(self.engine,'member-02','宇宙量子紅移'),[])

    def test_preview_does_not_reinforce_and_presentations_persist(self):
        """檢索預覽不強化；已送入成功決策的記憶按事件去重並跨重啟保存。"""
        self.say('櫻花橋九點見。')
        context=self.memory.context(self.engine,'member-02','櫻花橋')
        self.assertEqual(self.hit('櫻花橋')['signals']['presentations'],0)
        self.memory.presented(self.engine,'member-02',context)
        self.memory.presented(self.engine,'member-02',context)
        restarted=VectorMemory(self.path)
        hit=restarted.ranked(self.engine,'member-02','櫻花橋')[0]
        self.assertEqual(hit['signals']['presentations'],1)
        self.assertEqual(hit['event']['data']['text'],'櫻花橋九點見。')

    def test_future_branch_does_not_change_old_memory_strength(self):
        """讀回舊存檔後，未來分支的記憶和強化次数都不可穿越回來。"""
        self.say('櫻花橋九點見。');saved=self.engine.journal()
        context=self.memory.context(self.engine,'member-02','櫻花橋')
        self.say('未來分支的私人約定。')
        self.memory.presented(self.engine,'member-02',context)
        self.assertEqual(self.hit('櫻花橋')['signals']['presentations'],1)
        self.engine=Engine.replay(saved)
        self.assertEqual(self.hit('櫻花橋')['signals']['presentations'],0)
        self.assertEqual(self.memory.retrieve(self.engine,'member-02','未來分支私人約定'),[])

    def test_decay_changes_recall_but_never_erases_event(self):
        """遊戲時間讓久未想起的記憶淡化，但原始事件仍可重新檢索。"""
        self.say('櫻花橋九點見。');before=self.hit('櫻花橋')
        for _ in range(8):self.engine.advance(1440)
        after=self.hit('櫻花橋')
        self.assertLess(after['signals']['retention'],before['signals']['retention'])
        self.assertEqual(before['event'],after['event'])

    def test_place_is_the_observers_experienced_scene(self):
        """記憶場所來自本人當時所在場景，同地點能喚起相關舊事。"""
        self.say('泡茶聊相機。')
        for actor in ('member-01','member-02'):
            self.assertTrue(self.engine.dispatch(actor,Action('move',{'location':'room-01'}),actor).accepted)
        self.engine.advance();self.say('泡茶聊相機。')
        hits=self.memory.ranked(self.engine,'member-02','泡茶相機',limit=2)
        self.assertEqual(hits[0]['signals']['scene'],'room-01')
        self.assertEqual(hits[1]['signals']['scene'],'shared')

    def test_relay_is_retrievable_but_stays_reported(self):
        """轉述可以按內容找回，仍明確標為傳聞而不是本人見聞。"""
        self.say('櫻花橋的古董相機是藍色。')
        source=self.engine.view('member-02')['memories'][0]['id']
        result=self.engine.dispatch('member-02',Action('tell',{'target':'member-03','source_event':source}),'relay')
        self.assertTrue(result.accepted)
        hit=self.hit('櫻花橋古董相機',owner='member-03')
        self.assertEqual(hit['signals']['evidence'],'reported')
        self.assertEqual(hit['event']['data']['source']['data']['text'],'櫻花橋的古董相機是藍色。')

    def test_old_index_is_migrated_without_rewriting_journal(self):
        """新版内容向量分開索引，保留舊資料和世界雜湊，不混用舊向量。"""
        self.say('櫻花橋九點見。');before=self.engine.journal()
        event=next(e for e in before['events'] if e['kind']=='message_spoken')
        with self.memory.connect() as db:
            db.execute('INSERT INTO memories VALUES (?,?,?,?,?,?)',('member-02',event['hash'],self.memory.embedding.name,event['id'],'[0]','{}'))
        self.assertIn('櫻花橋',self.hit('櫻花橋')['event']['data']['text'])
        self.assertEqual(self.engine.journal(),before)
        with self.memory.connect() as db:
            providers={r[0] for r in db.execute('SELECT provider FROM memories')}
        self.assertEqual(providers,{self.memory.embedding.name,self.memory.provider})

    def test_importance_prefers_actual_commitment_over_same_topic_chat(self):
        """同主題的正式邀約比閒聊容易想起，承諾由目前邀約狀態裁定。"""
        self.say('櫻花橋拍相機。')
        self.assertTrue(self.engine.dispatch('member-01',Action('invite',{'target':'member-02','start':10,'end':13,'location':'shared','purpose':'櫻花橋拍相機。'}),'invite').accepted)
        hit=self.hit('櫻花橋拍相機')
        self.assertEqual(hit['event']['kind'],'invitation_created')

class DialogueToneTests(unittest.TestCase):
    def test_single_generation_preserves_voice_facts_and_original_dialogue(self):
        """Grok 4.3 單次生成帶降套話指引，不增加改寫呼叫或刪改數字和自然反駁。"""
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as temp:
            backend=XAIBackend('fixture-only',Path(temp)/'usage.json',dialogue_model='grok-4.3')
            captured=[]
            text='不是今天，是星期六九點。你又記錯了？'
            def request(route,body):
                captured.append(body)
                return {'model':body['model'],'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'kind':'say','params':{'target':'player','text':text}})}}], 'usage':{'prompt_tokens':100,'completion_tokens':20}}
            backend._request=request
            context={'self':{'id':'member-02'},'nearby':[{'id':'player'}],'memories':[]}
            action=backend.decide(context,'慢熱，重視準時與承諾。','玩家說話')
            self.assertEqual(action.params['text'],text);self.assertEqual(len(captured),1)
            self.assertIn('Lieflat',captured[0]['messages'][0]['content'])
            self.assertIn('profile 的本人語氣優先',captured[0]['messages'][0]['content'])
            self.assertEqual(json.loads(captured[0]['messages'][1]['content'])['context'],context)
            self.assertEqual(captured[0]['model'],'grok-4.3')

class DecisionPresentationTests(PixelTests):
    # Only this class's new case runs here; inherited PixelTests aren't duplicated.
    def test_success_and_rejection_have_different_presentation_effects(self):
        """模型行動遭距離拒絕不強化；成功回話才保存此次帶入的個人記憶。"""
        self.session.space.entities['player'].update(x=18,y=15)
        self.session._do('player',Action('say',{'target':'member-01','text':'櫻花橋相機。'}));self.session.engine.advance()
        self.backend.action=Action('say',{'target':'member-03','text':'隔空對話'})
        self.assertIsNone(self.session._ai('member-01','玩家說話'))
        hits=self.session.memory.ranked(self.session.engine,'member-01','櫻花橋相機')
        self.assertEqual(hits[0]['signals']['presentations'],0)
        self.backend.action=Action('say',{'target':'player','text':'嗯，櫻花橋。'})
        self.assertIsNotNone(self.session._ai('member-01','玩家說話'))
        hits=self.session.memory.ranked(self.session.engine,'member-01','櫻花橋相機')
        original=next(h for h in hits if h['event']['actor']=='player')
        self.assertEqual(original['signals']['presentations'],1)

def load_tests(loader,tests,pattern):
    suite=unittest.TestSuite()
    for cls in (EpisodeMemoryTests,DialogueToneTests):suite.addTests(loader.loadTestsFromTestCase(cls))
    suite.addTest(DecisionPresentationTests('test_success_and_rejection_have_different_presentation_effects'))
    return suite
