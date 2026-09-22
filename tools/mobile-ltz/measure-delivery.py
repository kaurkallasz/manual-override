"""Read-only SSE timing across relay stages. Never starts a game or sends controls."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import http.cookiejar
import json
from pathlib import Path
import ssl
import statistics
import time
from urllib.request import Request, build_opener, HTTPCookieProcessor, HTTPSHandler

ROOT = Path(__file__).resolve().parents[2]


def percentile(values, fraction=.95):
    return round(sorted(values)[int((len(values)-1)*fraction)], 2) if values else None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=int,default=20)
    args=parser.parse_args()
    if not 5 <= args.seconds <= 60: parser.error('--seconds must be between 5 and 60')
    config=json.loads((ROOT/'hub-config.json').read_text())
    secret=(ROOT/'.mobile-ltz-runtime/bridge-secret').read_text().strip()
    tls=ssl.create_default_context(cafile='/etc/ssl/cert.pem')
    def opener(cookies=False):
        handlers=[HTTPSHandler(context=tls)]
        if cookies: handlers.append(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        return build_opener(*handlers)
    def login(client,url,headers):
        request=Request(url,data=json.dumps({'password':config['sandboxes']['green']['password']}).encode(),
                        headers={**headers,'Content-Type':'application/json'})
        with client.open(request,timeout=20) as response: return json.load(response)
    direct=opener()
    auth=login(direct,'http://127.0.0.1:8118/login',{'X-Mobile-Bridge':secret})['auth']
    hosted=opener(True)
    assert login(hosted,'https://mecharena.eu/TowerDefence/api.php?path=login',{'Origin':'https://mecharena.eu'}).get('ok')
    with direct.open('http://127.0.0.1:4040/api/tunnels',timeout=5) as response:
        tunnels=json.load(response)['tunnels']
    tunnel=next(item['public_url'] for item in tunnels if item['public_url'].startswith('https://'))
    bridge={'X-Mobile-Bridge':secret,'X-Mobile-Auth':auth,'ngrok-skip-browser-warning':'1'}
    sources=[('local',opener(),'http://127.0.0.1:8000/s/gamemaster/p/mobile-ltz-api/api/events',{'Cookie':'hhh_auth='+auth}),
             ('gateway',opener(),'http://127.0.0.1:8118/events',bridge),
             ('tunnel',opener(),tunnel+'/events',bridge),
             ('hosted',hosted,'https://mecharena.eu/TowerDefence/api.php?path=events',{})]
    def measure(source):
        name,client,url,headers=source
        arrivals=[]; offsets=[]; lengths=[]; generation=[]; builds=[]; phases=set(); enemy_max=0
        try:
            with client.open(Request(url,headers=headers),timeout=args.seconds+5) as response:
                deadline=time.monotonic()+args.seconds
                frame=[]
                while time.monotonic()<deadline:
                    line=response.readline()
                    if not line: break
                    if line.strip(): frame.append(line); continue
                    data=b'\n'.join(row[5:].strip() for row in frame if row.startswith(b'data:')); frame=[]
                    if not data: continue
                    value=json.loads(data); value=value.get('state',value)
                    at=time.monotonic(); arrivals.append(at); lengths.append(len(data))
                    delivery=value.get('delivery') or {}
                    prepared=delivery.get('prepared_at',value.get('server_time'))
                    if isinstance(prepared,(int,float)): offsets.append(at-prepared)
                    if isinstance(delivery.get('source_gap_ms'),(int,float)): generation.append(delivery['source_gap_ms'])
                    if isinstance(delivery.get('build_ms'),(int,float)): builds.append(delivery['build_ms'])
                    phases.add(value.get('phase','unknown'));enemy_max=max(enemy_max,len(value.get('enemies',[])))
            gaps=[(b-a)*1000 for a,b in zip(arrivals,arrivals[1:])]
            return {'source':name,'samples':len(arrivals),'updates_per_s':round((len(arrivals)-1)/(arrivals[-1]-arrivals[0]),2) if len(arrivals)>1 else 0,
                    'gap_p95_ms':percentile(gaps),'gap_max_ms':max(gaps,default=None),
                    'excess_delivery_p95_ms':percentile([(offset-min(offsets))*1000 for offset in offsets]),
                    'source_gap_p95_ms':percentile(generation),'build_p95_ms':percentile(builds),
                    'mean_packet_bytes':round(statistics.mean(lengths)) if lengths else 0,'phases':sorted(phases),'max_enemies':enemy_max}
        except Exception as error:
            # Never include authenticated URLs, cookies or exception bodies.
            return {'source':name,'error':type(error).__name__}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(measure,sources): print(json.dumps(result),flush=True)


if __name__=='__main__': main()
