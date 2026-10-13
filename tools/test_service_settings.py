import copy
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
from lifebox.service_settings import ServiceSettings, load_settings, stored_key
from lifebox.demo_backend import DemoBackend
from lifebox.xai import XAIBackend, read_key


class Studio:
    def __init__(self, root):
        self.lock=threading.RLock();self.jobs={};self.root=root
        self.folders=[{'id':'one','path':str(root/'sd'),'backend':'a1111','label':'Forge'}]
        self.resources={'base':{'id':'base','category':'checkpoint','name':'base.safetensors','selectable':True,'installations':['one']}}
        self.config={'installation':'one','backend':'a1111','url':'http://127.0.0.1:7861','checkpoint':'base','profiles':{'actor':'untouched'},'native_selected':{'portrait':'keep'}}
        self.service={'ready':False,'message':'not tested'};self.probes=0
    def state(self):
        return copy.deepcopy({'config':self.config,'folders':self.folders,'resources':list(self.resources.values()),'service':self.service})
    def configure(self,data):self.config.update(data)
    def discover(self,path=None):
        if path:
            root=Path(path).resolve()
            if not (root/'webui.py').is_file():raise ValueError('not SD')
            self.folders.append({'id':'new','path':str(root),'backend':'a1111','label':'New Forge'})
    def probe(self):self.probes+=1;self.service={'ready':True,'message':'SD connected'}


class ConnectionsTests(unittest.TestCase):
    def setUp(self):
        parent=Path(__file__).parent/'connection-test-data';parent.mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=parent);self.root=Path(self.tmp.name).resolve()
        self.session=SimpleNamespace(root=self.root/'world',lock=threading.RLock(),studio=Studio(self.root),backend=SimpleNamespace(base=DemoBackend()),components=SimpleNamespace(original_backend=None))
        self.settings=ServiceSettings(self.session,self.root)
    def tearDown(self):
        assert self.root.is_relative_to((Path(__file__).parent/'connection-test-data').resolve())
        self.tmp.cleanup()
    def body(self,**changes):return {'operation':'save_ai','enabled':True,'key':'fixture-only-key','remember':False,'model':'grok-build-0.1','dialogue_model':'grok-4.3',**changes}
    def mount(self,**changes):return {'operation':'mount_sd','path':'','installation':'one','url':'http://127.0.0.1:7860','checkpoint':'base',**changes}
    def test_save_activates_without_network_and_preserves_routes_world_budget(self):
        old=XAIBackend('old-fixture',self.root/'work/play-usage.json',limit_usd=.03,max_calls=19,dialogue_model='grok-4.3');old.ledger['calls']=7;old._persist();self.session.backend.base=old
        with patch.object(XAIBackend,'_request',side_effect=AssertionError('No network on save')):
            result=self.settings.operation(self.body())
        new=self.session.backend.base
        self.assertEqual((new.stats()['calls'],new.limit,new.max_calls),(7,.03,19));self.assertEqual(new._key,'fixture-only-key')
        self.assertNotIn('fixture-only-key',json.dumps(result));self.assertNotIn('fixture-only-key',self.settings.path.read_text());self.assertEqual(load_settings(self.root)['save_dir'],str(self.session.root.resolve()));self.assertIs(self.session.components.original_backend,new)
    @unittest.skipUnless(os.name=='nt','Windows DPAPI')
    def test_encrypted_saved_key_roundtrip_overrides_environment_without_returning_secret(self):
        result=self.settings.operation(self.body(remember=True));path=stored_key(self.root)
        self.assertNotIn('fixture-only-key',path.read_text());self.assertTrue(result['ai']['saved_key'])
        with patch.dict(os.environ,{'XAI_API_KEY':'different-fixture'}):self.assertEqual(read_key(path,prefer_environment=False),'fixture-only-key')
        restored=ServiceSettings(self.session,self.root);restored.operation(self.body(key=''));self.assertEqual(self.session.backend.base._key,'fixture-only-key')
    def test_offline_and_blank_key_keep_current_key_and_ledger(self):
        self.settings.operation(self.body());self.settings.operation(self.body(key='',enabled=False));self.assertTrue(self.session.backend.base.stats()['demo'])
        self.settings.operation(self.body(key=''));self.assertEqual(self.session.backend.base._key,'fixture-only-key')
    def test_invalid_settings_do_not_write_or_switch(self):
        for changes in ({'key':'short'},{'key':'bad key with spaces'},{'model':'unknown'},{'enabled':'yes'}):
            with self.assertRaises(ValueError):self.settings.operation(self.body(**changes))
            self.assertFalse(self.settings.path.exists());self.assertIsInstance(self.session.backend.base,DemoBackend)
    def test_model_test_only_explicit_and_missing_selected_model_fails(self):
        self.settings.operation(self.body())
        with patch.object(XAIBackend,'_request',return_value={'data':[{'id':'grok-build-0.1'},{'id':'grok-4.3'}]}) as request:
            result=self.settings.operation({'operation':'test_ai'});request.assert_called_once_with('/models');self.assertIn('成功',result['message'])
        self.assertEqual(self.session.backend.base.stats()['calls'],0)
    def test_mount_only_changes_connection_and_keeps_character_profiles(self):
        result=self.settings.operation(self.mount());self.assertEqual(result['sd']['config']['url'],'http://127.0.0.1:7860');self.assertEqual(self.session.studio.config['profiles'],{'actor':'untouched'});self.assertEqual(self.session.studio.config['native_selected'],{'portrait':'keep'});self.assertEqual(self.session.studio.probes,0)
    def test_new_path_mount_and_bad_paths(self):
        folder=self.root/'custom-sd';folder.mkdir();(folder/'webui.py').touch()
        self.settings.operation(self.mount(path=str(folder),checkpoint=''));self.assertEqual(self.session.studio.config['installation'],'new')
        with self.assertRaises(ValueError):self.settings.operation(self.mount(path=str(self.root/'missing')))
    def test_wrong_url_or_checkpoint_and_active_jobs_block_before_save(self):
        original=copy.deepcopy(self.session.studio.config)
        for changes in ({'url':'https://cloud.example'},{'checkpoint':'missing'}):
            with self.assertRaises(ValueError):self.settings.operation(self.mount(**changes))
            self.assertEqual(self.session.studio.config,original)
        self.session.studio.jobs={'job':{'status':'running'}}
        with self.assertRaises(ValueError):self.settings.operation(self.mount())
        self.assertEqual(self.session.studio.config,original)
    def test_probe_is_separate_and_extra_fields_rejected(self):
        self.settings.operation({'operation':'test_sd'});self.assertEqual(self.session.studio.probes,1)
        with self.assertRaises(ValueError):self.settings.operation({'operation':'test_sd','key':'fixture'})
    def test_explicit_demo_launch_stays_in_demo_save_directory(self):
        from lifebox.play import main
        config={'enabled':True,'model':'grok-build-0.1','dialogue_model':'grok-4.3','save_dir':str(self.root/'original-world')}
        server=SimpleNamespace(server_port=8766,serve_forever=lambda:None)
        with patch.object(sys,'argv',['game','--demo','--port','8766']), patch('lifebox.service_settings.load_settings',return_value=config), patch('lifebox.pixel.PixelSession') as session, patch('lifebox.play.make_server',return_value=server), patch('builtins.print'):
            main()
        self.assertEqual(session.call_args.args[0].name,'demo-play')
        self.assertIsInstance(session.call_args.args[1],DemoBackend)
    def test_connection_route_requires_token_and_origin(self):
        from urllib.request import Request,urlopen
        from urllib.error import HTTPError
        from lifebox.play import make_server
        self.session.screen=lambda:{}
        with patch('lifebox.service_settings.ServiceSettings',return_value=self.settings):server=make_server(self.session,0)
        t=threading.Thread(target=server.serve_forever,daemon=True);t.start();url=f'http://127.0.0.1:{server.server_port}'
        try:
            token=json.load(urlopen(url+'/api/state'))['token']
            with self.assertRaises(HTTPError) as missing:urlopen(url+'/api/connections')
            self.assertEqual(missing.exception.code,403)
            response=json.load(urlopen(Request(url+'/api/connections',headers={'X-Play-Token':token})));self.assertNotIn('key',response['ai'])
            data=json.dumps(self.body(enabled=False,key='')).encode()
            headers={'Content-Type':'application/json','X-Play-Token':token}
            with self.assertRaises(HTTPError) as origin:urlopen(Request(url+'/api/connections',data,headers))
            self.assertEqual(origin.exception.code,403)
            headers['Origin']=url;result=json.load(urlopen(Request(url+'/api/connections',data,headers)));self.assertFalse(result['ai']['enabled'])
        finally:server.shutdown();server.server_close();t.join()


if __name__=='__main__':unittest.main()
