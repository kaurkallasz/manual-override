"""Upload security, private contact storage, and durable retry coverage."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_event_progression as fixture


class ScoreboardTests(unittest.TestCase):
    setUp=fixture.EventProgressionTests.setUp
    pair=fixture.EventProgressionTests.pair
    new_event=fixture.EventProgressionTests.new_event
    play=fixture.EventProgressionTests.play

    def test_email_is_private_and_optional(self):
        import score_upload as upload
        for bad in ('bad','a@b','a\n@b.com','a..b@example.com','x'*255+'@e.com'):
            with self.assertRaises(ValueError):upload.normalize_email(bad)
        self.assertEqual(upload.normalize_email(' Player@Example.com '),'player@example.com')
        self.s.score_set_contact('green','player@example.com',self.event)
        self.assertTrue(self.s.snapshot('green')['scoreboard']['email_added'])
        self.assertNotIn('player@example.com',json.dumps(self.s.snapshot()))
        self.assertNotIn('player@example.com',json.dumps(self.s.export()))
        with self.assertRaisesRegex(ValueError,'already'):
            self.s.score_set_contact('green','thief@example.com',self.event)
        with self.s.transaction() as db:self.assertEqual(db.execute('SELECT count(*) FROM score_outbox').fetchone()[0],1)

    def test_player_status_distinguishes_setup_queue_retry_and_submission(self):
        from types import SimpleNamespace
        self.s.score_set_contact('green','player@example.com',self.event)
        self.module._store=self.s
        self.module._uploader=SimpleNamespace(paired=False)
        state=self.module.progress_snapshot({'side':'green'})['scoreboard']
        self.assertEqual(state['upload_state'],'setup_required')
        self.assertNotIn('Check your email',state['message'])
        self.module._uploader.paired=True
        self.assertEqual(self.module.progress_snapshot({'side':'green'})['scoreboard']['upload_state'],'queued')
        with self.s.transaction(write=True) as db:
            db.execute("UPDATE score_outbox SET tries=1,error='temporary failure'")
        self.assertEqual(self.module.progress_snapshot({'side':'green'})['scoreboard']['upload_state'],'retrying')
        with self.s.transaction(write=True) as db:db.execute('DELETE FROM score_outbox')
        state=self.module.progress_snapshot({'side':'green'})['scoreboard']
        self.assertEqual(state['upload_state'],'submitted')
        self.assertIn('submitted for delivery',state['message'])
        self.assertNotIn('player@example.com',json.dumps(state))

    def test_profile_create_is_idempotent_and_contact_not_in_profile(self):
        p=self.s.create_player('New','email-new',event_id=self.event,email='new@example.com')
        self.assertEqual(p,self.s.create_player('New','email-new',event_id=self.event,email='new@example.com'))
        with self.assertRaisesRegex(ValueError,'operation ID'):
            self.s.create_player('New','email-new',event_id=self.event,email='other@example.com')
        with self.s.transaction() as db:
            self.assertNotIn('new@example.com',db.execute('SELECT data FROM players WHERE id=?',(p['player_id'],)).fetchone()[0])
            self.assertEqual(db.execute('SELECT count(*) FROM score_outbox').fetchone()[0],1)

    def test_finished_results_queue_once_and_retain_recordings(self):
        self.s.score_set_contact('green','player@example.com',self.event)
        a,data=self.play(10,'overrun');self.s.record(data,final=True)
        with self.s.transaction() as db:
            rows=db.execute('SELECT * FROM score_outbox ORDER BY rowid').fetchall()
        self.assertEqual(len(rows),2)
        body=json.loads(rows[1]['payload']);self.assertEqual(body['run_id'],a['run_id'])
        self.assertEqual(set(body['player_ids']),set(self.ids.values()))
        self.assertEqual(body['receipts'][self.ids['green']]['statistics']['total_kills'],10)
        self.assertNotIn('player@example.com',rows[1]['payload'])
        other=self.module.ProgressStore(self.path);other.initialize()
        with other.transaction() as db:self.assertEqual(db.execute('SELECT count(*) FROM score_outbox').fetchone()[0],2)

    def test_existing_history_can_be_added_later(self):
        self.play(12,'overrun')
        with self.s.transaction() as db:self.assertEqual(db.execute('SELECT count(*) FROM score_outbox').fetchone()[0],0)
        self.s.score_set_contact('green','player@example.com',self.event)
        with self.s.transaction() as db:self.assertEqual(db.execute('SELECT count(*) FROM score_outbox').fetchone()[0],2)

    def test_pairing_response_loss_and_upload_retry(self):
        from score_upload import UploadClient
        calls=[]
        def network(action,payload,key=None):
            calls.append((action,payload,key))
            if len(calls)==1:raise OSError('response lost')
            if action=='pair':return {'ok':True,'installation_id':'a'*32}
            return {'ok':True,'accepted_id':'profile:'+payload['player_id']}
        client=UploadClient(self.s,Path(self.folder.name)/'private',transport=network)
        with self.assertRaises(OSError):client.pair('A'*32,'Test arena')
        client.pair('A'*32,'Test arena')
        self.assertEqual(calls[0][1]['upload_key'],calls[1][1]['upload_key'])
        self.assertNotIn('upload_key',client.status())
        self.assertEqual(client.path.stat().st_mode&0o777,0o600)
        self.s.score_set_contact('green','player@example.com',self.event)
        client.transport=lambda *a: (_ for _ in ()).throw(OSError('offline'))
        self.assertFalse(client.flush_one())
        self.assertEqual(client.status()['pending'],1)
        with self.s.transaction(write=True) as db:db.execute('UPDATE score_outbox SET next_at=0')
        client.transport=network
        self.assertTrue(client.flush_one());self.assertEqual(client.status()['pending'],0)
        client.disconnect();self.assertFalse(client.status()['paired'])

    def test_later_partner_email_does_not_reexport_old_result(self):
        self.s.score_set_contact('green','first@example.com',self.event)
        self.play(9,'overrun')
        with self.s.transaction(write=True) as db: db.execute('DELETE FROM score_outbox')
        self.play(10,'overrun')
        with self.s.transaction(write=True) as db: db.execute('DELETE FROM score_outbox')
        self.s.score_set_contact('purple','second@example.com',self.event)
        with self.s.transaction() as db:
            rows=db.execute('SELECT id FROM score_outbox').fetchall()
        self.assertEqual([row[0] for row in rows],['profile:'+self.ids['purple']])

    def test_wrong_ack_does_not_drop_result(self):
        from score_upload import UploadClient
        c=UploadClient(self.s,Path(self.folder.name)/'private',transport=lambda *a:{'ok':True,'accepted_id':'wrong'})
        c.save_config({'upload_key':'b'*64,'installation_id':'c'*32})
        self.s.score_set_contact('green','player@example.com',self.event)
        self.assertFalse(c.flush_one());self.assertEqual(c.status()['pending'],1)

    def test_network_failure_cannot_block_local_result_save(self):
        self.s.score_set_contact('green','player@example.com',self.event)
        with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('network during save')):
            a,_=self.play(42,'overrun')
        self.assertEqual(self.s.snapshot('green')['latest_result']['run_id'],a['run_id'])

if __name__=='__main__':unittest.main()
