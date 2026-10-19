"""Exercise the production helper-unloading loader in a fresh interpreter.

Fake arms only. The default-driver probe uses an invalid local IP and must
fail before opening a robot socket. Run directly or via test_relay_worker.py.
"""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'hub'))


def main():
    from flask import Flask
    from hub import Sandbox
    sandbox = SimpleNamespace(name='gamemaster',
        machines_dir=str(ROOT / 'sandboxes/gamemaster/prototypes'),
        hub=SimpleNamespace(sandboxes_dir=str(ROOT / 'sandboxes')),
        app=Flask('production-relay-loader'), _modules={})
    Sandbox._load_one(sandbox, 'dobot-mg400-relay')
    relay = sandbox._modules['dobot-mg400-relay']
    assert 'arm_worker' not in sys.modules
    assert 'relay_arm' not in sys.modules
    worker_class = relay.ArmWorker

    # Reloading the helpers mirrors pickle's import lookup after the hub has
    # removed them. The old cached target/class cannot be pickled afterwards.
    from test_relay_worker import FakeArm
    workers = []
    with tempfile.TemporaryDirectory() as folder:
        events = str(Path(folder) / 'fake-arm-events.txt')
        def fake_worker(ip, **kwargs):
            worker = worker_class(ip, **kwargs, _driver_factory=FakeArm, command_timeout=1)
            workers.append(worker)
            return worker
        client = sandbox.app.test_client()
        base = '/p/dobot-mg400-relay/api'
        try:
            with patch.object(relay, 'ArmWorker', side_effect=fake_worker), \
                 patch.object(relay, '_log_command'), patch.object(relay, '_log_incoming'):
                for side in relay.SIDES:
                    response = client.post(base+'/connect', json={'side':side, 'ip':events})
                    assert response.is_json, response.status_code
                    assert response.json['ok'], response.json
                    acquired = client.post(base+'/acquire', json={'side':side}).json
                    assert acquired['ok'], acquired
                    enabled = client.post(base+'/enable', json={'side':side,'token':acquired['token']}).json
                    assert enabled['ok'], enabled
                    state = client.get(base+'/state').json['arms'][side]
                    assert state['connected'] and state['motion_ready'] and state['feedback_ok'], state
                    assert not state['servo_active'], state
                assert workers[0]._process.pid != workers[1]._process.pid
                assert not Path(events).exists(), 'Connect/Enable must not issue motion or pump commands'
        finally:
            relay.hub_stop()
        assert all(not worker._process.is_alive() for worker in workers)

        # Also cover production's default factory, which used to be an
        # unpicklable cached relay_arm.DobotMG400 class.
        robot = worker_class('test-no-robot', local_ip='not-a-local-ip', command_timeout=1)
        try:
            try:
                robot.connect()
                raise AssertionError('Invalid local interface was accepted')
            except relay.DobotError as error:
                assert 'no local interface' in str(error), str(error)
            assert not robot._process.is_alive()
        finally:
            robot.close()
    print(json.dumps({'status':'passed','loader':'Sandbox._load_one',
        'teams':['purple','green'],'default_driver':'validated before socket creation'}))


if __name__ == '__main__':
    main()
