"""One frozen client assembly for local players and the existing hosted exporter."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent
UI=ROOT.parent/'ltz_ui'
CLIENT_FILES=('index.html','mobile.css','mobile.js','viewport.js','live-game.js','network.js')
HELPERS=('delay-trace.js','connection-log.js','operation-id.js','journey.js','mission-countdown.js','joint-rig.js','turret-overlay.js','physical-arm.js','mcam1.js')

def assemble(root=ROOT):
    files={name:(root/name).read_text() for name in CLIENT_FILES}
    files['mobile.js']='\n'.join([(UI/'shop.js').read_text(),(UI/'score-feedback.js').read_text(),(UI/'marker-presence.js').read_text(),*((root/name).read_text() for name in HELPERS),files['mobile.js']])
    files['mobile.css']+='\n'+(UI/'shop.css').read_text()
    return files
