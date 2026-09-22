"""Narrow DreamHost-to-local relay. Exposes no hub pages or robot endpoints."""
import hmac
import json
import logging
import os
import re
import time
import threading
import secrets
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from flask import Flask, Response, request, jsonify, stream_with_context

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def timed_frame(frame, gap_ms):
    """Annotate owned delivery diagnostics; preserve unknown SSE verbatim."""
    try:
        lines=frame.decode('utf-8').splitlines()
        raw='\n'.join(line[5:].lstrip(' ') for line in lines if line.startswith('data:'))
        value=json.loads(raw)
        state=value.get('state',value)
        delivery=state.get('delivery')
        if not isinstance(delivery,dict) or delivery.get('contract')!='photon.delivery' or delivery.get('version')!=1:
            return frame
        delivery.update(gateway_at=time.time(),gateway_gap_ms=gap_ms)
        other=[line for line in lines if line and not line.startswith('data:')]
        return ('\n'.join(other+['data: '+json.dumps(value,separators=(',',':'))])+'\n\n').encode()
    except (ValueError,AttributeError,TypeError):
        return frame


def coalesce_frames(previous, incoming):
    """Merge only the owned full-state/delta contract, retaining scene changes."""
    if previous is None:
        return incoming
    def decode(frame):
        raw=b'\n'.join(line[5:].strip() for line in frame.splitlines() if line.startswith(b'data:'))
        value=json.loads(raw)
        if (value.get('contract')!='hub.live' or value.get('version')!=1
                or value.get('kind') not in ('snapshot','update') or not isinstance(value.get('state'),dict)):
            raise ValueError('Not an owned live frame')
        return value
    if not any(line.startswith(b'data:') for line in incoming.splitlines()):
        return previous  # A keepalive must not evict an undelivered scene.
    try:
        old,new=decode(previous),decode(incoming)
        if new['kind']=='update':
            if any(old['state'].get(key)!=new['state'].get(key) for key in ('run_id','level_revision')):
                return None  # Caller flushes both; an unidentified scene is not mergeable.
            new['state']={**old['state'],**new['state']}
            new['kind']=old['kind']
        prefix='event: update\n' if new['kind']=='update' else ''
        return (prefix+'data: '+json.dumps(new,separators=(',',':'))+'\n\n').encode()
    except (ValueError,AttributeError,TypeError):
        return None


def latest_events(response):
    """One pending owned snapshot per subscriber; bounded fallback for unknown frames."""
    condition=threading.Condition()
    pending=[]
    finished=False
    stopped=False
    def read():
        nonlocal finished
        frame=[];previous_at=None
        try:
            while not stopped:
                line=response.readline()
                if not line: break
                frame.append(line)
                if line not in (b'\n',b'\r\n'): continue
                at=time.monotonic()
                value=timed_frame(b''.join(frame),round((at-previous_at)*1000,2) if previous_at is not None else None)
                frame=[];previous_at=at
                with condition:
                    merged=coalesce_frames(pending[-1],value) if pending else value
                    if pending and merged is not None:
                        pending[-1]=merged
                    else:
                        condition.wait_for(lambda: len(pending)<2 or stopped)
                        if stopped: break
                        pending.append(value)
                    condition.notify_all()
        except (OSError,ValueError):
            pass  # EOF/timeout ends the stream; the player's retry owner recovers.
        finally:
            with condition:
                finished=True;condition.notify_all()
    reader=threading.Thread(target=read,name='mobile-latest-events',daemon=True)
    reader.start()
    try:
        while True:
            with condition:
                condition.wait_for(lambda: pending or finished)
                if not pending: break
                value=pending.pop(0);condition.notify_all()
            yield value
    finally:
        with condition:
            stopped=True;condition.notify_all()
        response.close()
        reader.join(timeout=.25)

def create_app(secret, upstream='http://127.0.0.1:8000', client_token_file=None, public_url_file=None, public_url=None):
    app = Flask('mobile-ltz-gateway')
    app.config['MAX_CONTENT_LENGTH'] = 4096
    opener = build_opener(NoRedirect())
    stream_tokens={}
    stream_lock=threading.Lock()

    def stream_offer(cookie):
        try:
            url=public_url or json.loads(Path(public_url_file).read_text())['url']
            parsed=urlsplit(url)
            if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment:
                return None
        except (ValueError,TypeError,KeyError,OSError):
            return None
        now=time.time()
        with stream_lock:
            for token,entry in list(stream_tokens.items()):
                if entry['expires_at']<=now: del stream_tokens[token]
            found=next(((token,entry) for token,entry in stream_tokens.items() if entry['cookie']==cookie and entry['expires_at']>now+90),None)
            if found is None:
                if len(stream_tokens)>=128: return None
                token=secrets.token_urlsafe(32)
                entry={'cookie':cookie,'expires_at':now+600}
                stream_tokens[token]=entry
            else: token,entry=found
        return {'contract':'mobile.stream','version':1,'url':url.rstrip('/')+'/live/events?token='+token,'expires_at':entry['expires_at'],'ttl_s':max(0,entry['expires_at']-now)}

    @app.before_request
    def authorize():
        if request.path=='/live/events':
            if request.method not in ('GET','OPTIONS') or request.headers.get('Origin')!='https://mecharena.eu':
                return jsonify(error='Read-only player stream required'),403
            with stream_lock:
                entry=stream_tokens.get(request.args.get('token',''))
            if not entry or entry['expires_at']<=time.time():
                return jsonify(error='Player stream expired'),401
            if request.method=='OPTIONS':
                return Response(status=204,headers={'Access-Control-Allow-Methods':'GET',
                    'Access-Control-Allow-Headers':'ngrok-skip-browser-warning, Accept',
                    'Access-Control-Max-Age':'60'})
            request.environ['mobile.stream']=entry
            return None
        if not hmac.compare_digest(request.headers.get('X-Mobile-Bridge', ''), secret):
            return jsonify(error='Unauthorized'), 401
        if (request.content_length or 0) > 4096:
            return jsonify(error='Request too large'), 413

    @app.after_request
    def stream_cors(response):
        if request.path=='/live/events' and request.headers.get('Origin')=='https://mecharena.eu':
            response.headers['Access-Control-Allow-Origin']='https://mecharena.eu'
            response.headers['Vary']='Origin'
            response.headers['Referrer-Policy']='no-referrer'
        return response

    @app.route('/<path:path>', methods=['GET', 'POST'])
    def relay(path):
        direct=request.environ.get('mobile.stream')
        if direct: path='events'
        client = re.fullmatch(r'client/(?:manifest|(?:[a-f0-9]{32}|latest)/(?:index\.html|mobile\.css|mobile\.js|viewport\.js|live-game\.js|network\.js|joint-rig\.js))', path)
        if not client and path not in ('login', 'state', 'events', 'command', 'renderer.js') and not path.startswith('assets/'):
            return jsonify(error='Not found'), 404
        if request.method != ('POST' if path in ('login', 'command') else 'GET'):
            return jsonify(error='Method not allowed'), 405
        if '..' in path or '\\' in path or '?' in path or '#' in path:
            return jsonify(error='Invalid path'), 400
        headers = {'Accept-Encoding': 'identity'}
        if client:
            try:
                token = Path(client_token_file).read_text().strip() if client_token_file else ''
                if not re.fullmatch(r'[a-f0-9]{32}', token):
                    return jsonify(error='Mobile interface unavailable'), 503
                headers['X-HHH-Auth'] = token
                manifest_url = upstream + '/s/green/p/mobile-ltz/api/client/manifest'
                with opener.open(Request(manifest_url, headers=headers), timeout=10) as response:
                    manifest = json.load(response)
                if not isinstance(manifest, dict) or manifest.get('contract') != 'mobile.client' or type(manifest.get('version')) is not int or manifest['version'] != 1 or manifest.get('status') != 'ready' or not re.fullmatch(r'[a-f0-9]{32}', str(manifest.get('build', ''))):
                    return jsonify(error='Mobile interface contract unavailable'), 503
                if path == 'client/manifest':
                    return jsonify(manifest)
            except (ValueError, URLError, TimeoutError, OSError):
                return jsonify(error='Mobile interface unavailable. Check the local game server.'), 503
            data = None
            url = upstream + '/s/green/p/mobile-ltz/api/' + path
        elif path == 'login':
            value = request.get_json(silent=True) or {}
            password = value.get('password')
            if not isinstance(password, str) or len(password) > 256:
                return jsonify(error='Player password required'), 400
            data = urlencode({'password': password}).encode()
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
            url = upstream + '/s/green/login'
        else:
            cookie = direct['cookie'] if direct else request.headers.get('X-Mobile-Auth', '')
            if not cookie or len(cookie) > 2048 or any(c in cookie for c in '\r\n;'):
                return jsonify(error='Sign in to Green'), 401
            headers['Cookie'] = 'hhh_auth=' + cookie
            data = request.get_data() if path == 'command' else None
            if data is not None:
                headers['Content-Type'] = 'application/json'
            url = upstream + '/s/gamemaster/p/mobile-ltz-api/api/' + quote(path, safe='/')
        try:
            try:
                response = opener.open(Request(url, data=data, headers=headers), timeout=10)
            except HTTPError as error:
                response = error
            if path == 'login':
                cookie = SimpleCookie()
                for value in response.headers.get_all('Set-Cookie', []):
                    cookie.load(value)
                response.close()
                if 'hhh_auth' not in cookie:
                    return jsonify(error='Wrong Green password'), 401
                return jsonify(ok=True, auth=cookie['hhh_auth'].value)
            if response.code in (301, 302, 303, 307, 308):
                response.close()
                return jsonify(error='Sign in to Green'), 401
            status = response.code
            content_type = response.headers.get('Content-Type', 'application/octet-stream')
            if path=='state' and status==200:
                try: value=json.load(response)
                finally: response.close()
                offer=stream_offer(cookie)
                if offer: value['live_stream']=offer
                result=jsonify(value);result.headers['Cache-Control']='no-store'
                return result
            def stream():
                try:
                    if path == 'events':
                        for frame in latest_events(response):
                            if direct and direct['expires_at']<=time.time(): break
                            yield frame
                    else:
                        while chunk := response.read(65536):
                            yield chunk
                finally:
                    response.close()
            response_headers = {'Cache-Control':'no-store, no-transform', 'X-Accel-Buffering':'no'}
            if response.headers.get('X-Mobile-Build'):
                response_headers['X-Mobile-Build'] = response.headers['X-Mobile-Build']
            return Response(stream_with_context(stream()), status=status, content_type=content_type,
                            headers=response_headers)
        except (URLError, TimeoutError, OSError):
            return jsonify(error='Local Gamemaster is offline'), 503
    return app

if __name__ == '__main__':
    secret = Path(os.environ['MOBILE_LTZ_SECRET_FILE']).read_text().strip()
    if len(secret) < 32:
        raise SystemExit('Bridge secret is missing')
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    from werkzeug.serving import make_server
    token_file = Path(os.environ['MOBILE_LTZ_SECRET_FILE']).with_name('client-auth-8000')
    public_file=Path(os.environ['MOBILE_LTZ_SECRET_FILE']).with_name('tunnel.json')
    make_server('127.0.0.1', 8118, create_app(secret, client_token_file=token_file, public_url_file=public_file), threaded=True).serve_forever()
