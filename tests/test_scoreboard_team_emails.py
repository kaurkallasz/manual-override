"""Comma-separated team contacts, privacy, and concurrent outbox durability."""
import json
from pathlib import Path
import unittest
import test_event_progression as fixture

class TeamEmailTests(unittest.TestCase):
    setUp=fixture.EventProgressionTests.setUp
    pair=fixture.EventProgressionTests.pair
    new_event=fixture.EventProgressionTests.new_event
    play=fixture.EventProgressionTests.play
    def test_normalization_and_limits(self):
        from score_upload import normalize_emails,normalize_email
        self.assertEqual(normalize_emails(' B@Example.com, a@example.com, b@example.com '),['a@example.com','b@example.com'])
        self.assertEqual(normalize_emails('  '),[])
        for bad in ('a@example.com,','a@example.com,,b@example.com','a@example.com,bad','a@example.com; b@example.com',','.join(f'p{i}@example.com' for i in range(11)),['a@example.com']):
            with self.assertRaises(ValueError):normalize_emails(bad)
        self.assertEqual(len(normalize_emails(','.join(f'p{i}@example.com' for i in range(10)))),10)
        with self.assertRaises(ValueError):normalize_email('a@example.com,b@example.com')
    def test_create_dedupes_and_retry_order_is_irrelevant(self):
        p=self.s.create_player('Team','team-create',event_id=self.event,email='b@example.com, A@example.com,a@example.com')
        self.assertEqual(p,self.s.create_player('Team','team-create',event_id=self.event,email='a@example.com,b@example.com'))
        with self.s.transaction() as db:
            row=db.execute('SELECT payload FROM score_outbox WHERE id=?',('profile:'+p['player_id'],)).fetchone()
            self.assertEqual(json.loads(row[0])['email'],'a@example.com,b@example.com')
            self.assertEqual(db.execute('SELECT count(*) FROM score_outbox').fetchone()[0],1)
    def test_invalid_address_rolls_back_whole_profile(self):
        with self.s.transaction() as db:before=db.execute('SELECT count(*) FROM players').fetchone()[0]
        with self.assertRaises(ValueError):self.s.create_player('Bad team','invalid-team',event_id=self.event,email='a@example.com,bad')
        with self.s.transaction() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM players').fetchone()[0],before)
            self.assertEqual(db.execute('SELECT count(*) FROM score_outbox').fetchone()[0],0)
    def test_add_teammate_keeps_original_and_queues_only_new_profile(self):
        self.s.score_set_contact('green','a@example.com',self.event);self.play(4,'overrun')
        with self.s.transaction(write=True) as db:db.execute('DELETE FROM score_outbox')
        self.s.score_set_contact('green','a@example.com, b@example.com',self.event)
        with self.s.transaction() as db:
            rows=db.execute('SELECT payload FROM score_outbox').fetchall()
            self.assertEqual(len(rows),1);self.assertEqual(json.loads(rows[0][0])['email'],'a@example.com,b@example.com')
        for bad in ('b@example.com,c@example.com','a@example.com,c@example.com'):
            with self.assertRaisesRegex(ValueError,'Include all existing'):self.s.score_set_contact('green',bad,self.event)
        self.assertEqual(self.s.snapshot('green')['scoreboard']['email_count'],2)
    def test_team_addresses_stay_private(self):
        self.s.score_set_contact('green','private1@example.com,private2@example.com',self.event)
        for value in (self.s.snapshot('green'),self.s.snapshot(),self.s.export()):
            self.assertNotIn('private1@example.com',json.dumps(value));self.assertNotIn('private2@example.com',json.dumps(value))
    def test_old_ack_cannot_drop_new_recipient_list(self):
        from score_upload import UploadClient
        self.s.score_set_contact('green','a@example.com',self.event)
        def transport(action,payload,key):
            self.s.score_set_contact('green','a@example.com,b@example.com',self.event)
            return {'ok':True,'accepted_id':'profile:'+payload['player_id']}
        c=UploadClient(self.s,Path(self.folder.name)/'uploader',transport=transport);c.save_config({'upload_key':'a'*64,'installation_id':'b'*32})
        self.assertTrue(c.flush_one());self.assertEqual(c.status()['pending'],1)
        c.transport=lambda a,p,k:{'ok':True,'accepted_id':'profile:'+p['player_id']}
        self.assertTrue(c.flush_one());self.assertEqual(c.status()['pending'],0)
        self.assertEqual(self.s.snapshot('green')['scoreboard']['upload_state'],'submitted')
    def test_old_failed_upload_does_not_backoff_new_payload(self):
        from score_upload import UploadClient
        self.s.score_set_contact('green','a@example.com',self.event)
        def transport(action,payload,key):
            self.s.score_set_contact('green','a@example.com,b@example.com',self.event)
            raise OSError('temporary')
        c=UploadClient(self.s,Path(self.folder.name)/'uploader',transport=transport);c.save_config({'upload_key':'a'*64,'installation_id':'b'*32})
        self.assertFalse(c.flush_one())
        with self.s.transaction() as db:
            row=db.execute('SELECT tries,next_at,error FROM score_outbox').fetchone();self.assertEqual(tuple(row),(0,0,None))
    def test_identical_contact_list_does_not_resend(self):
        self.s.score_set_contact('green','a@example.com,b@example.com',self.event)
        with self.s.transaction(write=True) as db:db.execute('DELETE FROM score_outbox')
        self.s.score_set_contact('green',' B@example.com, a@example.com ',self.event)
        with self.s.transaction() as db:self.assertEqual(db.execute('SELECT count(*) FROM score_outbox').fetchone()[0],0)

if __name__=='__main__':unittest.main()
