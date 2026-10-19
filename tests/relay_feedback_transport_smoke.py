"""Real loopback SSE/HTTP with fake arms. Never connects to robot sockets.

Run: .venv/bin/python -B tests/relay_feedback_transport_smoke.py
"""
import threading
import time
from unittest.mock import patch

from werkzeug.serving import make_server, WSGIRequestHandler
from test_photon_framework import load, Flask
from test_relay_feedback import adapter


class QuietHandler(WSGIRequestHandler):
    def log(self, *args, **kwargs):
        pass


def main():
    relay = load('dobot-mg400-relay')
    stale = set()
    measured_at = {}
    heartbeats = []
    thread_errors = []
    def measured(side):
        if side not in stale:
            measured_at[side] = time.time()
        return dict(connected=True, enabled=True, feedback_ok=side not in stale,
                    feedback_at=measured_at[side],
                    robot_mode=5, motion_epoch=7, motion_ready=side not in stale,
                    joints=[0, 20, 30, 9], pose=[300, 100, 50, 9])
    app = Flask('relay-feedback-loopback')
    app.register_blueprint(relay.bp, url_prefix='/s/gamemaster/p/dobot-mg400-relay')
    name = relay.bp.name + '.heartbeat'
    heartbeat = app.view_functions[name]
    def delayed_heartbeat():
        result = heartbeat()
        heartbeats.append(time.monotonic())
        time.sleep(.9)  # Old heartbeat telemetry exceeds freshness between reads.
        return result
    app.view_functions[name] = delayed_heartbeat
    server = make_server('127.0.0.1', 0, app, threaded=True, request_handler=QuietHandler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    clients = []
    try:
        with patch.object(threading, 'excepthook', side_effect=thread_errors.append), \
             patch.object(relay, '_arm_dict', side_effect=measured), \
             patch.object(relay, '_arm', return_value=None), \
             patch.object(relay, '_log_command'), patch.object(relay, '_log_incoming'), \
             patch.object(relay, '_command_log_snapshot', side_effect=AssertionError('Monitor entered transport')):
            worker.start()
            for side in ('green', 'purple'):
                _, client = adapter(side)
                client.base = 'http://127.0.0.1:' + str(server.server_port) + '/s/gamemaster/p/dobot-mg400-relay'
                client._token, client._hb_ok, client._motion_epoch = 'test-' + side, True, 7
                relay._sides[side].update(token=client._token, present=True, last_seen=time.time())
                client._start_heartbeat()
                clients.append(client)
            deadline = time.monotonic() + 2
            while not all(client.get_state()['motion_ready'] for client in clients):
                assert time.monotonic() < deadline, 'Stream did not start'
                time.sleep(.02)
            stamps = [set(), set()]
            ages = []
            for _ in range(35):
                time.sleep(.1)
                for index, client in enumerate(clients):
                    state = client.get_state()
                    assert state['motion_ready'], state
                    stamps[index].add(state['last_feedback'])
                    ages.append(time.time() - state['last_feedback'])
            assert all(len(values) >= 20 for values in stamps), stamps
            assert len(heartbeats) >= 4
            stale.update(('green', 'purple'))
            time.sleep(.3)
            assert all(not client.get_state()['motion_ready'] for client in clients), 'Stale feedback stayed ready'
            threads = [(client._feedback_thread, client._hb_thread) for client in clients]
            for client in clients:
                client.close()
            assert all(not thread.is_alive() for pair in threads for thread in pair), 'Transport thread leaked'
            assert not thread_errors, thread_errors
            print('PASS: both players, 900 ms heartbeat delay, >=20 fresh SSE measurements, stale-stop and clean teardown; max age %.0f ms' % (max(ages) * 1000))
    finally:
        for client in clients:
            if client._token is not None:
                client.close()
        server.shutdown()
        server.server_close()
        worker.join(2)


if __name__ == '__main__':
    main()
