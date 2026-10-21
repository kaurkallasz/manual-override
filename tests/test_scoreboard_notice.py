"""Operator notice contract, privacy boundary and existing SSE integration."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from flask import Flask,Response
from test_photon_framework import load,FakeContext

class ScoreboardNoticeTests(unittest.TestCase):
    def setUp(self):
        self.progress=load('photon-progress');self.view=load('laser-tag-y')
        self.addCleanup(self.progress.hub_stop);self.addCleanup(self.view.hub_stop)
    def status(self,**fields):
        return {'contract':'photon.scoreboard-link','version':1,'status':'ready','state':'linked','upload_delayed':False,**fields}
    def test_owner_projects_no_contact_or_credential(self):
        self.progress._uploader=SimpleNamespace(error=None,read_config=lambda:{'installation_id':'a'*32,'upload_key':'secret','name':'Private venue','pairing_request':{'id':'private-id','status':'approved','contact_email':'private@example.test'}})
        self.assertEqual(self.progress.scoreboard_link_snapshot(),self.status())
        self.progress._uploader.error='Temporary network error'
        self.assertTrue(self.progress.scoreboard_link_snapshot()['upload_delayed'])
        self.progress._uploader=None
    def test_owner_missing_and_corrupt_are_unavailable(self):
        self.assertEqual(self.progress.scoreboard_link_snapshot()['status'],'unavailable')
        self.progress._uploader=SimpleNamespace(read_config=lambda:1)
        self.assertEqual(self.progress.scoreboard_link_snapshot()['status'],'unavailable')
        self.progress._uploader=None
    def test_owner_unpaired_and_request_states(self):
        for state in ('unlinked','submitting','pending','cancelling','cancelled','rejected','expired','revoked'):
            cfg={} if state=='unlinked' else {'pairing_request':{'status':state,'contact_email':'private@example.test'}}
            self.progress._uploader=SimpleNamespace(error=None,read_config=lambda:cfg)
            self.assertEqual(self.progress.scoreboard_link_snapshot(),self.status(state=state))
        self.progress._uploader=None
    def test_notice_does_not_wait_for_network_worker(self):
        from score_upload import UploadClient
        import threading
        with tempfile.TemporaryDirectory() as tmp:
            client=UploadClient(None,Path(tmp));client.save_config({'upload_key':'a'*64,'installation_id':'b'*32})
            self.progress._uploader=client
            held=threading.Event();release=threading.Event()
            def network_lock():
                with client.lock:held.set();release.wait(3)
            thread=threading.Thread(target=network_lock);thread.start();held.wait(1)
            try:
                before=__import__('time').monotonic();self.assertEqual(self.progress.scoreboard_link_snapshot()['state'],'linked')
                self.assertLess(__import__('time').monotonic()-before,.5)
            finally:release.set();thread.join();self.progress._uploader=None
    def test_consumer_validates_contract_and_strips_extra_fields(self):
        for value in (None,{},self.status(version=True),self.status(contract='wrong'),self.status(state='unknown'),self.status(upload_delayed=1),self.status(status='unavailable')):
            self.view.hub_init(FakeContext({'photon-progress':SimpleNamespace(scoreboard_link_snapshot=lambda:value)}))
            self.assertEqual(self.view._scoreboard_link()['status'],'unavailable')
        self.view.hub_init(FakeContext({'photon-progress':SimpleNamespace(scoreboard_link_snapshot=lambda:self.status(secret='never send',email='private@example.test'))}))
        self.assertEqual(self.view._scoreboard_link(),self.status())
        self.view.hub_init(FakeContext({}));self.assertEqual(self.view._scoreboard_link()['status'],'unavailable')
    def test_operator_only_stream_and_completion_event(self):
        value=self.status(state='pending');closed=[]
        def chunks():
            yield b'data: {"contract":"photon.game","version":2}\n\n'
            value['state']='linked'
            yield b': keepalive\n\n'
        def events(**kw):
            r=Response(chunks(),mimetype='text/event-stream');r.call_on_close(lambda:closed.append(True));return r
        game=SimpleNamespace(game_snapshot=lambda:{'contract':'photon.game','version':2},game_events=events)
        owner=SimpleNamespace(scoreboard_link_snapshot=lambda:value)
        self.view.hub_init(FakeContext({'photon-progress':owner,'photon-game':game}))
        app=Flask(__name__);app.register_blueprint(self.view.bp,url_prefix='/p/laser-tag-y')
        c=app.test_client();url='/p/laser-tag-y/api/events?scoreboard=1&markers=1'
        self.assertEqual(c.get(url).status_code,403)
        self.assertEqual(c.get(url,environ_overrides={'hhh.roles':{'green'}}).status_code,403)
        with patch.object(self.view.time,'monotonic',side_effect=[1,4]):
            r=c.get(url,environ_overrides={'hhh.roles':{'gamemaster'}},buffered=True)
        payload=r.data.decode();self.assertEqual(r.status_code,200)
        self.assertIn('event: scoreboard',payload);self.assertIn('"state":"pending"',payload);self.assertIn('"state":"linked"',payload)
        self.assertEqual(len(closed),1)

if __name__=='__main__':unittest.main()
