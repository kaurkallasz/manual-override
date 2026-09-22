"""Export mobile presentation and only published level assets for DreamHost."""
import concurrent.futures
import hashlib
import http.cookiejar
import json
from pathlib import Path
import shutil
from urllib.parse import urlencode
from urllib.request import build_opener, HTTPCookieProcessor, Request, urlopen
import zipfile

ROOT=Path(__file__).resolve().parents[2]
RUNTIME=ROOT/'.mobile-ltz-runtime'
OUT=RUNTIME/'release'/'TowerDefence'
BASE='http://127.0.0.1:8000'
API=BASE+'/s/gamemaster/p/mobile-ltz-api/api/'

def export():
    OUT.mkdir(parents=True, exist_ok=True)
    config=json.loads((ROOT/'hub-config.json').read_text())
    jar=http.cookiejar.CookieJar()
    opener=build_opener(HTTPCookieProcessor(jar))
    opener.open(BASE+'/s/green/login',urlencode({'password':config['sandboxes']['green']['password']}).encode()).close()
    cookie='; '.join(c.name+'='+c.value for c in jar)
    def fetch(path):
        with urlopen(Request(API+path,headers={'Cookie':cookie}),timeout=30) as response:return response.read()
    snapshot=json.loads(fetch('state'))
    values=set(snapshot['presentation']['assets'].values())
    def asset(path):
        data=fetch('assets/'+path)
        filename=hashlib.sha256(path.encode()).hexdigest()[:24]+Path(path.split('?')[0]).suffix
        (OUT/'assets'/filename).write_bytes(data)
        return path,'assets/'+filename,len(data)
    (OUT/'assets').mkdir(exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool: results=list(pool.map(asset,values))
    (OUT/'assets.json').write_text(json.dumps({p:f for p,f,_ in results}))
    (OUT/'renderer.js').write_bytes(fetch('renderer.js'))
    for name in ['index.html','mobile.css','mobile.js','viewport.js','live-game.js','network.js']:
        shutil.copyfile(ROOT/'sandboxes/green/prototypes/mobile-ltz'/name,OUT/name)
    rig=(ROOT/'sandboxes/green/prototypes/mobile-ltz/joint-rig.js').read_text()
    turret=(ROOT/'sandboxes/green/prototypes/mobile-ltz/turret-overlay.js').read_text()
    (OUT/'mobile.js').write_text(rig+'\n'+turret+'\n'+(OUT/'mobile.js').read_text())
    shutil.copyfile(Path(__file__).with_name('api.php'),OUT/'api.php')
    shutil.copyfile(Path(__file__).with_name('index.php'),OUT/'index.php')
    url=json.loads((RUNTIME/'tunnel.json').read_text())['url']
    secret=(RUNTIME/'bridge-secret').read_text().strip()
    (OUT/'bridge-config.php').write_text("<?php return ['url'=>"+repr(url)+",'secret'=>"+repr(secret)+"];\n")
    (OUT/'bridge-config.php').chmod(0o600)
    shutil.copyfile(Path(__file__).with_name('hosting.htaccess'),OUT/'.htaccess')
    archive=RUNTIME/'mobile-ltz-release.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
        for path in OUT.rglob('*'):
            if path.is_file() and path.name != 'bridge-config.php':bundle.write(path,path.relative_to(OUT.parent))
    archive.chmod(0o600)
    print(f'Exported {len(results)} published assets, {sum(n for _,_,n in results)//1024} KB. Bundle: {archive}')

if __name__=='__main__':export()
