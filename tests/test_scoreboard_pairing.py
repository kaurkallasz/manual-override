"""Installation request durability, approval boundary, and automatic upload coverage."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import test_event_progression as fixture

class PairingRequestTests(unittest.TestCase):
    setUp=fixture.EventProgressionTests.setUp
    pair=fixture.EventProgressionTests.pair
    new_event=fixture.EventProgressionTests.new_event
    def client(self,transport):
        from score_upload import UploadClient
        c=UploadClient(self.s,Path(self.folder.name)/'pairing-private',transport=transport)
        c.start=lambda:None
        return c
    def reply(self,p,**fields):
        return {'ok':True,'request_id':p['request_id'],'status':'pending','notification':'submitted',**fields}
    def test_pending_has_no_upload_and_status_has_no_secret(self):
        calls=[]
        def network(a,p,key=None):calls.append(a);return self.reply(p)
        c=self.client(network);c.request_pairing('Test arena',' OPERATOR@example.com ')
        self.assertFalse(c.flush_one());self.assertEqual(calls,[])
        c.check_pairing();self.assertEqual(calls,['request-pairing'])
        self.assertEqual(c.status()['pairing_request']['status'],'pending')
        self.assertEqual(c.path.stat().st_mode&0o777,0o600)
        self.assertNotIn(c.read_config()['upload_key'],json.dumps(c.status()))
        with self.assertRaisesRegex(ValueError,'in progress'):c.request_pairing('Another','o@example.com')
        with self.assertRaisesRegex(ValueError,'Cancel'):c.pair('A'*32,'Another')
    def test_response_loss_restart_then_approval_and_upload(self):
        calls=[]
        def lost(a,p,key=None):calls.append(dict(p));raise OSError('lost')
        c=self.client(lost);c.request_pairing('Test arena','o@example.com');c.check_pairing()
        self.s.score_set_contact('green','player@example.com',self.event)
        def network(a,p,key=None):
            if a=='ingest':return {'ok':True,'accepted_id':'profile:'+p['player_id']}
            calls.append(dict(p));return self.reply(p,status='approved',installation_id='a'*32)
        restarted=self.client(network);self.assertTrue(restarted.check_pairing())
        self.assertEqual(calls[0],calls[1]);self.assertTrue(restarted.paired)
        self.assertTrue(restarted.flush_one());self.assertEqual(restarted.status()['pending'],0)
    def test_bad_ack_does_not_pair_or_lose_request(self):
        c=self.client(lambda a,p:self.reply(p,status='approved',installation_id='invalid'))
        c.request_pairing('Arena','o@example.com');before=c.path.read_bytes()
        self.assertFalse(c.check_pairing());self.assertFalse(c.paired);self.assertEqual(before,c.path.read_bytes())
        c.pair_next=0;c.transport=lambda a,p:self.reply(p,request_id='f'*32)
        c.check_pairing();self.assertEqual(before,c.path.read_bytes())
    def test_cancel_survives_offline_and_blocks_upload(self):
        def offline(*args):raise OSError('offline')
        c=self.client(offline);c.request_pairing('Arena','o@example.com');c.cancel_request();c.check_pairing()
        self.assertEqual(c.read_config()['pairing_request']['status'],'cancelling')
        restarted=self.client(lambda a,p:self.reply(p,status='cancelled'))
        self.assertFalse(restarted.flush_one());restarted.check_pairing();self.assertFalse(restarted.path.exists())
    def test_terminal_request_can_be_replaced_with_fresh_proof(self):
        for state in ('expired','rejected','revoked'):
            c=self.client(lambda a,p:self.reply(p,status=state));c.request_pairing('Arena','o@example.com');old=c.read_config();c.check_pairing()
            c.request_pairing('New arena','n@example.com');new=c.read_config()
            self.assertNotEqual(old['upload_key'],new['upload_key']);self.assertNotEqual(old['pairing_request']['id'],new['pairing_request']['id'])
            c.path.unlink()
    def test_paired_installation_unchanged(self):
        c=self.client(lambda *a:None);c.save_config({'name':'Main arena','upload_key':'b'*64,'installation_id':'a'*32});before=c.path.read_bytes()
        self.assertFalse(c.check_pairing())
        with self.assertRaisesRegex(ValueError,'already paired'):c.request_pairing('New','o@example.com')
        self.assertEqual(before,c.path.read_bytes())
    def test_poll_backoff_and_validation(self):
        calls=[]
        def network(a,p):calls.append(a);return self.reply(p)
        c=self.client(network)
        for name,email in [('', 'o@example.com'),('x'*81,'o@example.com'),('Arena\n','o@example.com'),('Arena','bad')]:
            with self.assertRaises(ValueError):c.request_pairing(name,email)
        c.request_pairing('Arena','o@example.com');c.check_pairing();c.check_pairing();self.assertEqual(len(calls),1)
        c.pair_next=0;c.check_pairing();self.assertEqual(calls,['request-pairing','pairing-status'])

if __name__=='__main__':unittest.main()
