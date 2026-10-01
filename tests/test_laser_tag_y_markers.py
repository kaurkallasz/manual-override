"""One browser SSE connection for Game and Board display diagnostics; no hardware."""
import json
import unittest
from types import SimpleNamespace
from unittest import mock

from flask import Response
from test_photon_framework import FakeContext, Flask, load


class MarkerStreamTests(unittest.TestCase):
    def setUp(self):
        self.y = load('laser-tag-y')
        self.closed = []
        self.game_frames = [
            b'data: {"contract":"photon.game","version":2,"status":"ready"}\n\n',
            b'event: update\ndata: {"wave":2}\n\n',
            b': ping\n\n',
        ]
        def events(**options):
            self.assertEqual(options, {'incremental': True})
            response = Response(iter(self.game_frames), mimetype='text/event-stream')
            response.call_on_close(lambda: self.closed.append(True))
            return response
        self.game = SimpleNamespace(game_snapshot=lambda: {'contract':'photon.game', 'version':2},
                                    game_events=events)
        self.marker = {'contract':'photon.board.tracking','version':1,'status':'ready',
                       'source':'camera','sampled_at':100,'frame_at':100,
                       'tags':[{'id':40,'camera':[.4,.3],'visible':True,'last_seen':100}]}
        self.board = SimpleNamespace(tracking_snapshot=mock.Mock(return_value=self.marker))
        self.y.hub_init(FakeContext({'photon-game':self.game,'photon-board':self.board}))
        self.addCleanup(self.y.hub_stop)
        app = Flask('y-markers');app.register_blueprint(self.y.bp)
        self.client = app.test_client()

    def test_game_and_markers_share_one_stream_without_changing_game_events(self):
        with mock.patch.object(self.y.time,'monotonic',side_effect=[100,100.1,100.3]):
            response = self.client.get('/api/events?markers=1')
            body = response.data
            response.close()
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['X-Accel-Buffering'],'no')
        for frame in self.game_frames:
            self.assertIn(frame,body)
        self.assertEqual(body.count(b'event: markers\n'),1)
        diagnostic = body.split(b'event: markers\ndata: ',1)[1].split(b'\n\n',1)[0]
        self.assertEqual(json.loads(diagnostic),self.marker)
        self.assertEqual(self.board.tracking_snapshot.call_count,2)
        self.assertTrue(self.closed)

    def test_external_screen_and_game_only_clients_do_not_read_board(self):
        response = self.client.get('/api/events')
        self.assertEqual(response.data,b''.join(self.game_frames))
        self.board.tracking_snapshot.assert_not_called()
        response.close()

    def test_missing_disabled_failing_or_malformed_board_cannot_publish_live_markers(self):
        for board in (None, SimpleNamespace(),
                      SimpleNamespace(tracking_snapshot=lambda:{'contract':'wrong','version':1}),
                      SimpleNamespace(tracking_snapshot=lambda:{**self.marker,'version':True}),
                      SimpleNamespace(tracking_snapshot=lambda:{**self.marker,'sampled_at':float('nan')}),
                      SimpleNamespace(tracking_snapshot=mock.Mock(side_effect=RuntimeError('detector unavailable')))):
            modules = {'photon-game':self.game}
            if board is not None:
                modules['photon-board']=board
            self.y.hub_init(FakeContext(modules))
            result = self.y._marker_diagnostics()
            self.assertEqual(result['status'],'unavailable')
            self.assertEqual(result['tags'],[])
            self.assertTrue(result['errors'])

    def test_client_uses_the_shared_stream_instead_of_opening_a_second_eventsource(self):
        from pathlib import Path
        page = (Path(self.y.HERE)/'index.html').read_text()
        self.assertIn('new EventSource(`${SELF}/api/events?markers=1`)',page)
        self.assertIn("addEventListener('markers'",page)
        self.assertNotIn('/p/photon-board/api/events',page)
        monitor = page.split('function createArucoMonitor',1)[1].split('const arucoMonitor=',1)[0]
        self.assertNotIn('EventSource',monitor)


if __name__ == '__main__':
    unittest.main()
