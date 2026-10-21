"""Temporary player invitations, owned by the hub's authentication layer."""
import base64
import ipaddress
import secrets
import threading
import time
from urllib.parse import urlsplit

TEAMS = ('green', 'purple')
LIFETIME_SECONDS = 8 * 60 * 60


def destination(team):
    if team not in TEAMS:
        raise ValueError('Unknown player team.')
    return f'/s/{team}/p/mobile-ltz/'


def network_origin(request_origin, lan_origin, configured=None):
    """Use the browser's reachable origin, with LAN fallback for loopback."""
    def parse(value):
        if not isinstance(value, str) or len(value) > 512:
            raise ValueError('Invalid player join server address.')
        parsed = urlsplit(value)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in ('', '/')):
            raise ValueError('Player join address must be an HTTP(S) server origin.')
        # Accessing port also validates malformed ports.
        _ = parsed.port
        return parsed

    def local(host):
        if host == 'localhost' or host.endswith('.localhost'):
            return True
        try:
            address = ipaddress.ip_address(host)
            return address.is_loopback or address.is_unspecified
        except ValueError:
            return False

    parsed = parse(configured if configured is not None else request_origin)
    if local(parsed.hostname) and configured is None:
        parsed = parse(lan_origin)
    if local(parsed.hostname):
        raise ValueError('No phone-reachable address found. Open the hub using its game Wi-Fi address.')
    return f'{parsed.scheme}://{parsed.netloc}'


def qr_data_url(url):
    # OpenCV is already a game dependency. Import lazily so the standalone hub
    # can still run without camera dependencies; the route reports unavailability.
    import cv2
    parameters = cv2.QRCodeEncoder_Params()
    parameters.correction_level = cv2.QRCodeEncoder_CORRECT_LEVEL_M
    matrix = cv2.QRCodeEncoder_create(parameters).encode(url)
    matrix = cv2.copyMakeBorder(matrix, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
    matrix = cv2.resize(matrix, None, fx=8, fy=8, interpolation=cv2.INTER_NEAREST)
    ok, encoded = cv2.imencode('.png', matrix)
    if not ok:
        raise RuntimeError('Could not render the player QR code.')
    return 'data:image/png;base64,' + base64.b64encode(encoded.tobytes()).decode('ascii')


class PlayerJoinLinks:
    """Reusable, unguessable, team-bound links; rotation/restart revokes links.

    Existing authenticated sessions keep their ordinary cookie lifetime.
    No password, session cookie, or service token is embedded in invitations.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._tokens = {}
        self._expires_at = 0

    def snapshot(self, origin, *, regenerate=False):
        with self._lock:
            if regenerate or time.time() >= self._expires_at:
                self._tokens = {team: secrets.token_urlsafe(24) for team in TEAMS}
                self._expires_at = int(time.time()) + LIFETIME_SECONDS
            tokens, expires_at = dict(self._tokens), self._expires_at
        links = []
        for team, token in tokens.items():
            url = f'{origin}/s/{team}/login#join={token}'
            links.append(dict(team=team, url=url, destination=destination(team),
                              qr=qr_data_url(url)))
        return dict(contract='hub.player-join', version=1, status='ready',
                    origin=origin, expires_at=expires_at, links=links)

    def accepts(self, team, token):
        if team not in TEAMS or not isinstance(token, str) or len(token) != 32:
            return False
        with self._lock:
            expected = self._tokens.get(team)
            return bool(expected and time.time() < self._expires_at
                        and secrets.compare_digest(expected, token))

    def invalidate(self):
        with self._lock:
            self._tokens = {}
            self._expires_at = 0
