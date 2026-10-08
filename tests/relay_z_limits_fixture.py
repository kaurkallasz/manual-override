"""Real relay/operator and player UIs with temporary limits and fake arm data."""
import argparse
import tempfile
from pathlib import Path
from werkzeug.serving import make_server
from flask import request,jsonify,send_from_directory
from mobile_ltz_fixture import create_app
from test_photon_framework import load, ROOT


def fixture(folder):
    app,game=create_app(folder)
    relay=load('dobot-mg400-relay')
    relay.Z_FLOOR_PATH=str(Path(folder)/'z-floor.json')
    relay.COMMAND_LOG_FILE=str(Path(folder)/'relay.log')
    relay._z_floor=-102.;relay._z_floor_enabled=True
    relay._z_ceiling=80.;relay._z_ceiling_enabled=True
    app.register_blueprint(relay.bp,url_prefix='/s/gamemaster/p/dobot-mg400-relay')
    @app.get('/theme.css')
    def theme():return send_from_directory(ROOT/'hub','theme.css')
    @app.after_request
    def project_limits(response):
        if '/p/cartesian-xyz-test/api/' in request.path and response.is_json:
            value=response.get_json();limits=relay.z_limits_snapshot()
            value.update(z_limits=limits,motion_ready=True,motion_epoch=1,control_session='fixture-session',robot_mode=5)
            if request.path.endswith('/config'):
                value['workspace']={'x':[-450,450],'y':[-450,450],'z':[limits['minimum'],limits['maximum']],'r':[-160,160]}
            return jsonify(value)
        return response
    return app,game


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8117)
    with tempfile.TemporaryDirectory(prefix='relay-z-fixture-') as folder:
        app,game=fixture(folder);server=make_server('127.0.0.1',parser.parse_args().port,app,threaded=True)
        try:server.serve_forever()
        finally:game.hub_stop();app.config['fixture_cleanup']()
