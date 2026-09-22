import importlib.util
from pathlib import Path
import unittest
import io
import json
import tempfile
from unittest.mock import patch

path=Path(__file__).resolve().parents[1]/'tools/mobile-ltz/gateway.py'
spec=importlib.util.spec_from_file_location('mobile_gateway_test',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class GatewayTests(unittest.TestCase):
    def test_direct_stream_tokens_are_read_only_origin_scoped_and_expire(self):
        class Reply(io.BytesIO):
            code=200
            headers={'Content-Type':'application/json'}
        def upstream(request,**kwargs):
            self.assertEqual(request.get_header('Cookie'),'hhh_auth=fixture-player-cookie')
            return Reply(b'{"status":"ready"}' if request.full_url.endswith('/state') else b'data: {}\n\n')
        with patch.object(module,'build_opener') as make:
            make.return_value.open.side_effect=upstream
            client=module.create_app('fixture-bridge',public_url='https://example.test').test_client()
            self.assertEqual(client.get('/state').status_code,401)
            state=client.get('/state',headers={'X-Mobile-Bridge':'fixture-bridge','X-Mobile-Auth':'fixture-player-cookie'}).json
            offer=state['live_stream'];self.assertEqual(offer['version'],1)
            self.assertNotIn('fixture-player-cookie',json.dumps(state))
            path=offer['url'].replace('https://example.test','')
            self.assertEqual(client.get(path).status_code,403)
            self.assertEqual(client.get(path,headers={'Origin':'https://attacker.test'}).status_code,403)
            origin={'Origin':'https://mecharena.eu'}
            preflight=client.options(path,headers={**origin,'Access-Control-Request-Method':'GET','Access-Control-Request-Headers':'ngrok-skip-browser-warning'})
            self.assertEqual(preflight.status_code,204)
            self.assertEqual(preflight.headers['Access-Control-Allow-Methods'],'GET')
            self.assertEqual(client.post(path,headers=origin).status_code,403)
            self.assertEqual(client.get('/live/events?token=wrong',headers=origin).status_code,401)
            response=client.get(path,headers=origin)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.headers['Access-Control-Allow-Origin'],'https://mecharena.eu')
            self.assertEqual(response.data,b'data: {}\n\n')
            token=path.split('token=')[1]
            self.assertEqual(client.post('/command?token='+token,headers=origin,json={'action':'start'}).status_code,401)
            with patch.object(module.time,'time',return_value=offer['expires_at']+1):
                self.assertEqual(client.get(path,headers=origin).status_code,401)
    def test_coalescing_keeps_scene_and_latest_deaths_without_backlog(self):
        def frame(kind,state):
            return ('data: '+json.dumps({'contract':'hub.live','version':1,'kind':kind,'state':state})+'\n\n').encode()
        identity={'run_id':'one','level_revision':1}
        pending=frame('snapshot',{**identity,'level':{'name':'first'},'enemies':[{'id':1}],'kills':0})
        for i in range(100):
            pending=module.coalesce_frames(pending,frame('update',{**identity,'enemies':[],'kills':1,'sequence':i}))
        state=json.loads(pending.decode()[6:])
        self.assertEqual(state['kind'],'snapshot')
        self.assertEqual(state['state']['level'],{'name':'first'})
        self.assertEqual(state['state']['enemies'],[])
        self.assertEqual(state['state']['sequence'],99)
        self.assertEqual(state['state']['kills'],1)
        self.assertEqual(module.coalesce_frames(pending,b': ping\n\n'),pending)
        replaced=module.coalesce_frames(pending,frame('snapshot',{'run_id':'two','level_revision':2,'level':{'name':'second'},'enemies':[]}))
        self.assertEqual(json.loads(replaced.decode()[6:])['state']['level']['name'],'second')
        self.assertIsNone(module.coalesce_frames(pending,frame('update',{'run_id':'two','level_revision':2})))
    def test_timing_keeps_event_identity_and_uses_owned_contract(self):
        state={'enemies':[{'id':1}], 'delivery':{'contract':'photon.delivery','version':1,'sequence':42}}
        wire=('event: update\ndata: '+json.dumps({'state':state})+'\n\n').encode()
        result=module.timed_frame(wire,151)
        self.assertTrue(result.startswith(b'event: update\n'))
        decoded=json.loads(result.decode().split('data: ')[1])['state']
        self.assertEqual(decoded['enemies'],state['enemies'])
        self.assertEqual(decoded['delivery']['sequence'],42)
        self.assertEqual(decoded['delivery']['gateway_gap_ms'],151)
        self.assertIn('gateway_at',decoded['delivery'])
        self.assertEqual(module.timed_frame(b': keepalive\n\n',1),b': keepalive\n\n')
    def setUp(self):
        self.client=module.create_app('test-secret-only-not-a-deployment-key').test_client()
        self.headers={'X-Mobile-Bridge':'test-secret-only-not-a-deployment-key'}
    def test_bridge_and_player_auth_are_both_required(self):
        self.assertEqual(self.client.get('/state').status_code,401)
        self.assertEqual(self.client.get('/state',headers=self.headers).status_code,401)
    def test_no_admin_robot_arbitrary_url_or_traversal_proxy(self):
        for path in ['/s/gamemaster/','/robot/connect','/https://example.com','/assets/../secret','/assets/a%3Fb']:
            self.assertIn(self.client.get(path,headers=self.headers).status_code,(400,404))
    def test_methods_and_login_payloads(self):
        self.assertEqual(self.client.get('/command',headers=self.headers).status_code,405)
        self.assertEqual(self.client.post('/state',headers=self.headers,json={}).status_code,405)
        self.assertEqual(self.client.post('/login',headers=self.headers,json={'password':17}).status_code,400)
        self.assertEqual(self.client.post('/login',headers=self.headers,data='x'*5000).status_code,413)

    def test_events_preserve_complete_frames_and_discard_truncated_tail(self):
        class Reply(io.BytesIO):
            code=200
            headers={'Content-Type':'text/event-stream'}
        wire=b'event: update\ndata: {"kind":"update"}\n\ndata: {"cut":'
        with patch.object(module,'build_opener') as make:
            make.return_value.open.return_value=Reply(wire)
            client=module.create_app('test-secret-only-not-a-deployment-key').test_client()
            response=client.get('/events',headers={**self.headers,'X-Mobile-Auth':'fixture-only'},buffered=False)
            chunks=list(response.response)
            self.assertEqual(chunks,[b'event: update\ndata: {"kind":"update"}\n\n'])
            self.assertIn('no-transform',response.headers['Cache-Control'])

    def test_public_ui_is_allowlisted_and_contract_checked(self):
        build='b'*32
        class Reply(io.BytesIO):
            code=200
            headers={'Content-Type':'text/html','X-Mobile-Build':build}
        manifest={'contract':'mobile.client','version':1,'status':'ready','build':build}
        calls=[]
        def open_request(request, **kwargs):
            calls.append(request)
            return Reply(json.dumps(manifest).encode() if request.full_url.endswith('/manifest') else b'<html>published UI</html>')
        with tempfile.TemporaryDirectory() as directory:
            token=Path(directory)/'client-auth';token.write_text('a'*32)
            with patch.object(module,'build_opener') as make:
                make.return_value.open.side_effect=open_request
                client=module.create_app('test-secret-only-not-a-deployment-key',client_token_file=token).test_client()
                self.assertEqual(client.get('/client/latest/index.html').status_code,401)
                result=client.get('/client/latest/index.html',headers=self.headers)
                self.assertEqual(result.status_code,200)
                self.assertEqual(result.headers['X-Mobile-Build'],build)
                self.assertEqual(client.get('/client/'+build+'/joint-rig.js',headers=self.headers).status_code,200)
                self.assertTrue(all(request.get_header('X-hhh-auth')=='a'*32 for request in calls))
                self.assertEqual(client.get('/state',headers=self.headers).status_code,401)
                for path in ['/client/latest/prototype.py','/client/latest/api/command','/client/latest/../hub-config.json']:
                    self.assertEqual(client.get(path,headers=self.headers).status_code,404)
                manifest['version']=True
                self.assertEqual(client.get('/client/latest/index.html',headers=self.headers).status_code,503)

if __name__=='__main__':unittest.main()
