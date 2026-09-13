"""Green LTZ Score presentation; progress is owned by Photon Progress."""
import os
from flask import Blueprint, send_from_directory
HERE = os.path.dirname(os.path.abspath(__file__))
GAME_ART_DIR = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..', 'assets', 'game-art', 'z-pixel-v2', 'normalized'))
MANIFEST = {'name': 'LTZ Score', 'description': 'Saved players, weapon upgrades, three-win control progression and performance history.', 'default_page': '', 'pages': [{'path': '', 'label': 'LTZ Score'}]}
bp = Blueprint('green_player_ltz_score', __name__)
@bp.route('/')
def index():
    response = send_from_directory(HERE, 'index.html')
    response.headers['Cache-Control'] = 'no-store'
    return response
@bp.route('/score.js')
def script():
    response = send_from_directory(HERE, 'score.js')
    response.headers['Cache-Control'] = 'no-store'
    return response
@bp.route('/assets/<path:filename>')
def asset(filename):
    return send_from_directory(os.path.join(HERE, 'assets'), filename)
@bp.route('/art/<path:filename>')
def art(filename):
    return send_from_directory(GAME_ART_DIR, filename)
