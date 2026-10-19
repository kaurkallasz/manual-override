"""Bounded USB image-control client. Importing this module never opens hardware."""
import json
import threading
import time

CONTROL_RANGES = {
    'brightness': (-3, 3), 'contrast': (-3, 3), 'saturation': (-4, 4),
    'sharpness': (-3, 3), 'denoise': (0, 8), 'quality': (8, 63),
    'ae_level': (-5, 5), 'aec_value': (1, 65535), 'agc_gain': (1, 64),
    'aec': (0, 1), 'agc': (0, 1), 'awb': (0, 1), 'wb_mode': (0, 4),
    'aec2': (0, 1), 'bpc': (0, 1), 'wpc': (0, 1), 'raw_gma': (0, 1),
    'lenc': (0, 1), 'hmirror': (0, 1), 'vflip': (0, 1),
    'special_effect': (0, 6), 'colorbar': (0, 1),
}
AI_RANGES = {'enabled':(0,1),'confidence':(10,95),'nms':(10,90),
             'max_fps':(1,10),'max_boxes':(1,10),'stale_ms':(200,3000)}


def validate_detection(data):
    def integer(value, lo, hi):
        return type(value) is int and lo <= value <= hi
    def label(value):
        return isinstance(value, str) and 0 < len(value) <= 64 and all(ord(c) >= 32 for c in value)
    settings, boxes = data.get('settings'), data.get('boxes')
    if (data.get('kind') != 'ai' or not label(data.get('model'))
            or not label(data.get('class_name')) or not isinstance(settings,dict)
            or not all(integer(settings.get(k),*limits) for k,limits in AI_RANGES.items())
            or not isinstance(boxes,list) or len(boxes)>10
            or data.get('state') not in ('ready','disabled','loading','error','waiting_for_video','waiting_for_detection')
            or not integer(data.get('epoch'),1,4294967295) or not integer(data.get('frame_seq'),0,4294967295)
            or not integer(data.get('age_ms'),-1,2147483647)
            or not integer(data.get('width'),0,640) or not integer(data.get('height'),0,480)):
        raise RuntimeError('Incompatible camera detection protocol')
    if data['state']=='ready' and (data['width']==0 or data['height']==0 or data['frame_seq']==0 or data['age_ms']<0):
        raise RuntimeError('Malformed detection frame')
    for box in boxes:
        if (not isinstance(box,dict) or not all(integer(box.get(k),0,10000) for k in ('x','y','w','h'))
                or ('class_name' in box and not label(box['class_name']))
                or not integer(box.get('score'),0,100) or box['w']==0 or box['h']==0
                or box['x']+box['w']>10000 or box['y']+box['h']>10000):
            raise RuntimeError('Malformed detection box')


def validate_action(action, name=None, value=None, ranges=None):
    ranges = CONTROL_RANGES if ranges is None else ranges
    if action in ('get', 'reset') and name is None and value is None:
        return action
    if action != 'set' or name not in ranges or type(value) is not int:
        raise ValueError('Expected get, reset, or a supported control and integer value')
    lo, hi = ranges[name]
    if not lo <= value <= hi:
        raise ValueError(f'{name} must be between {lo} and {hi}')
    return f'set {name} {value}'


class XiaoControls:
    def __init__(self, serial_number='1CDBD443344C'):
        self.serial_number = serial_number
        self._lock = threading.RLock()
        self._serial = None
        self._sequence = 0

    def close(self):
        with self._lock:
            if self._serial is not None:
                try:
                    self._serial.close()
                finally:
                    self._serial = None

    def available_port(self):
        try:
            import serial
            from serial.tools.list_ports import comports
        except ImportError as exc:
            raise RuntimeError('Install mcam1/requirements.txt to enable USB controls') from exc
        ports = [p for p in comports() if p.vid == 0x303a and p.pid == 0x8000
                 and (not self.serial_number or p.serial_number == self.serial_number)]
        if len(ports) != 1:
            raise RuntimeError('Expected one matching XIAO USB webcam; reconnect it or configure its serial number')
        return ports[0].device

    def _open(self):
        if self._serial is not None:
            return
        import serial
        port = self.available_port()
        device = serial.Serial(None, 115200, timeout=0.1, write_timeout=1, exclusive=True)
        device.dtr, device.rts = True, False
        device.port = port
        device.open()
        self._serial = device

    def request(self, action='get', name=None, value=None):
        return self._exchange('ctrl', validate_action(action, name, value))

    def request_ai(self, action='get', name=None, value=None):
        return self._exchange('ai', validate_action(action, name, value, AI_RANGES))

    def _exchange(self, namespace, command):
        with self._lock:
            try:
                self._open()
                self._sequence = self._sequence % 2000000000 + 1
                seq = self._sequence
                self._serial.write(f'{namespace} {seq} {command}\n'.encode('ascii'))
                deadline, buffer = time.monotonic() + 4, bytearray()
                while time.monotonic() < deadline:
                    buffer.extend(self._serial.read(max(1, min(self._serial.in_waiting, 2048))))
                    while b'\n' in buffer:
                        line, _, buffer = buffer.partition(b'\n')
                        if line.strip().startswith(b'Unknown command.'):
                            if namespace == 'ai':
                                raise RuntimeError('AI firmware is not installed. Install ai-v1 to enable on-device people detection.')
                            raise RuntimeError('The camera is connected, but its firmware does not support image controls. Install controls-v1 firmware.')
                        try:
                            data = json.loads(line)
                        except (ValueError, UnicodeDecodeError):
                            continue
                        if not isinstance(data, dict) or type(data.get('id')) is not int or data.get('id') != seq:
                            continue
                        if data.get('ok') is not True:
                            raise RuntimeError(str(data.get('error', 'Camera rejected the command')))
                        if type(data.get('protocol')) is not int or data.get('protocol') != 1:
                            raise RuntimeError('Incompatible camera control protocol')
                        if namespace == 'ai':
                            validate_detection(data)
                        elif (data.get('sensor') != 'OV3660' or not isinstance(data.get('values'), dict)
                              or any(type(data['values'].get(k)) is not int or not lo <= data['values'][k] <= hi
                                     for k, (lo, hi) in CONTROL_RANGES.items())):
                            raise RuntimeError('Incompatible camera control protocol')
                        return data
                    if len(buffer) > 8192:
                        raise RuntimeError('Oversized camera reply')
                raise RuntimeError(f'Camera did not respond; {"ai-v1" if namespace == "ai" else "controls-v1"} firmware is required')
            except Exception:
                self.close()
                raise
