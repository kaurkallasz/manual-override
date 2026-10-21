"""Recovered interrupted match for real phone UI checks; temporary data, fake arms."""
import tempfile
from werkzeug.serving import make_server
from mobile_ltz_fixture import create_app


def create_recovered_app(folder):
    app, game = create_app(folder)
    app.test_client().post('/__test/camera', json={'enabled': True})
    event = game._progress.roster()['events']['active_id']
    game.apply_command({'action': 'start', 'event_id': event,
                        'starting_atoms': {'green': 100, 'purple': 102}})
    with game._engine.lock:
        for _ in range(13):
            game._engine.rewards.killed({'enemy_type': 'grunt', 'hp': 0, 'x': 400, 'y': 250, 'kill_owner': 'green'})
            game._engine.kills += 1
            game._engine.next_enemy_id += 1
    game._progress.last_checkpoint = 0
    game._progress.flush()
    # Simulate losing the process after its checkpoint, without a final result.
    old = game._progress
    old.stop()
    game._progress = game.ProgressLink(old.module_reader, old.engine_reader,
        old.wake, old.path, old.result_listener, old.tick)
    old_journey = game._journey
    game._journey = game.Journey(old_journey.path, old_journey.module_reader, old_journey.wake)
    game._engine.reset(); game._run_id = None
    game._progress.roster(); game._journey_tick()
    return app, game


if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as folder:
        app, game = create_recovered_app(folder)
        server = make_server('127.0.0.1', 8146, app, threaded=True)
        print('Recovery fixture ready', flush=True)
        try:
            server.serve_forever()
        finally:
            game.hub_stop(); app.config['fixture_cleanup']()
