"""Start/stop the phone relay for the existing game hub. No login launch agent is installed."""
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
PRIVATE=ROOT/'.mobile-ltz-runtime'
GAMEMASTER='http://localhost:8000/s/gamemaster/#laser-tag-y'

def open_gamemaster():
    if sys.platform == 'darwin' and os.environ.get('MOBILE_LTZ_NO_BROWSER') != '1':
        subprocess.run(['open', GAMEMASTER], check=True)

def listening(port):
    with socket.socket() as sock:
        sock.settimeout(.2)
        return sock.connect_ex(('127.0.0.1',port))==0

def ensure_game():
    if listening(8000):
        return
    # There is exactly one game. The relay may start it, but stopping/restarting
    # the relay never terminates the shared Gamemaster or team tabs.
    log=PRIVATE/'main-game.log'
    log.touch(mode=0o600,exist_ok=True);log.chmod(0o600)
    with log.open('a') as output:
        proc=subprocess.Popen([sys.executable,str(ROOT/'hub.py'),'--port','8000'],cwd=ROOT,
                              stdout=output,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
    deadline=time.monotonic()+20
    while not listening(8000) and time.monotonic()<deadline:
        if proc.poll() is not None:raise SystemExit('Main Gamemaster failed; see its private log.')
        time.sleep(.1)
    if not listening(8000):raise SystemExit('Main Gamemaster did not start.')

def start():
    PRIVATE.mkdir(mode=0o700,exist_ok=True)
    if any(listening(port) for port in (8118,4040)):
        if all(listening(port) for port in (8000,8118,4040)):
            print('Phone relay is attached to the existing Gamemaster on port 8000.')
            print('Gamemaster:', GAMEMASTER)
            open_gamemaster()
            return
        raise SystemExit('A stack service is already running. Use status, or stop this stack before restarting.')
    secret=PRIVATE/'bridge-secret'
    if not secret.exists():
        import secrets
        secret.write_text(secrets.token_urlsafe(48));secret.chmod(0o600)
    ngrok=shutil.which('ngrok')
    if not ngrok:raise SystemExit('Install/configure ngrok before starting the relay.')
    ensure_game()
    jobs={
        'gateway':[sys.executable,str(HERE/'gateway.py')],
        'tunnel':[ngrok,'http','http://127.0.0.1:8118','--inspect=false','--log=stdout','--log-format=json'],
    }
    env={**os.environ,'MOBILE_LTZ_SECRET_FILE':str(secret)}
    records={}
    for name,cmd in jobs.items():
        log=PRIVATE/(name+'.log')
        log.touch(mode=0o600,exist_ok=True);log.chmod(0o600)
        with log.open('a') as output:
            proc=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=output,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
        records[name]={'pid':proc.pid,'command':cmd}
        (PRIVATE/'processes.json').write_text(json.dumps(records))
        deadline=time.monotonic()+10
        port={'gateway':8118,'tunnel':4040}[name]
        while not listening(port) and time.monotonic()<deadline:
            if proc.poll() is not None:raise SystemExit(f'{name} failed; see its private log.')
            time.sleep(.1)
        if not listening(port):raise SystemExit(f'{name} did not start.')
    with urlopen(Request('http://127.0.0.1:8118/client/manifest',
                         headers={'X-Mobile-Bridge':secret.read_text().strip()}),timeout=10) as response:
        client=json.load(response)
    if client.get('contract')!='mobile.client' or type(client.get('version')) is not int or client['version']!=1 or client.get('status')!='ready':
        raise SystemExit('The mobile interface did not publish successfully.')
    for attempt in range(30):
        with urlopen('http://127.0.0.1:4040/api/tunnels',timeout=3) as response:data=json.load(response)
        tunnels=data.get('tunnels',[])
        if tunnels:
            url=tunnels[0]['public_url']
            (PRIVATE/'tunnel.json').write_text(json.dumps({'url':url}))
            print('Gamemaster:', GAMEMASTER)
            print('Green: http://localhost:8000/s/green/')
            print('Phone: https://mecharena.eu/TowerDefence/')
            print('Relay:',url)
            print('Mobile build:',client['build'])
            open_gamemaster()
            return
        time.sleep(.2)
    raise SystemExit('Tunnel not ready. See the private tunnel log.')

def stop():
    path=PRIVATE/'processes.json'
    records=json.loads(path.read_text()) if path.exists() else {}
    for name,record in reversed(list(records.items())):
        pid=record['pid']
        command=subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True).stdout
        marker='ngrok http http://127.0.0.1:8118' if name=='tunnel' else str(HERE/(name+'_server.py' if name=='game' else 'gateway.py'))
        if marker in command:
            os.kill(pid,signal.SIGTERM)
            print('Stopped',name)
    if path.exists():path.unlink()
    deadline=time.monotonic()+10
    while any(listening(port) for port in (8012,8118,4040)) and time.monotonic()<deadline:
        time.sleep(.1)

if __name__=='__main__':
    action=sys.argv[1] if len(sys.argv)>1 else 'status'
    if action=='start':start()
    elif action=='stop':stop()
    elif action=='restart':stop();start()
    elif action=='status':
        for name,port in [('Shared game',8000),('Mobile relay',8118),('Tunnel agent',4040)]:print(name,'running' if listening(port) else 'stopped')
    else:raise SystemExit('Usage: service.py start|restart|stop|status')
