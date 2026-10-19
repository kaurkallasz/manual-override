"""Green LTZ Score presentation; progress is owned by Photon Progress."""
import os
from pathlib import Path
from flask import Blueprint, send_from_directory
from shared.ltz_ui import ROOT as UI_ROOT, ASSETS, asset_response
HERE = os.path.dirname(os.path.abspath(__file__))
GAME_ART_DIR = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..', 'assets', 'game-art', 'z-pixel-v2', 'normalized'))
MANIFEST = {'name': 'LTZ Score', 'description': 'Saved players, weapon upgrades, three-win control progression and performance history.', 'default_page': '', 'pages': [{'path': '', 'label': 'LTZ Score'}]}
bp = Blueprint('green_player_ltz_score', __name__)
@bp.route('/operation-id.js')
def operation_script():
    response = send_from_directory(Path(__file__).resolve().parents[4] / 'shared/mobile_ltz', 'operation-id.js')
    response.headers['Cache-Control'] = 'no-store'
    return response
@bp.route('/')
def index():
    response = send_from_directory(UI_ROOT.parent/'ltz_score', 'index.html')
    response.headers['Cache-Control'] = 'no-store'
    return response
@bp.route('/score.js')
def script():
    response = send_from_directory(UI_ROOT.parent/'ltz_score', 'score.js')
    response.headers['Cache-Control'] = 'no-store'
    return response
@bp.route('/assets/<path:filename>')
def asset(filename):
    if filename in ASSETS:return asset_response(filename)
    return send_from_directory(os.path.join(HERE, 'assets'), filename)
@bp.route('/art/<path:filename>')
def art(filename):
    return send_from_directory(GAME_ART_DIR, filename)

@bp.route('/shop.js')
@bp.route('/shop.css')
def shared_shop():
    from flask import request
    return send_from_directory(UI_ROOT,request.path.rsplit('/',1)[-1],max_age=0)
