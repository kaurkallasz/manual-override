"""Game Master access to the shared delay.analysis v1 recorder, no control commands."""
import csv
import io
import json
from pathlib import Path
from flask import Response, abort, jsonify, request, send_from_directory
from shared import delay_trace as trace
import live

_recorder = None
_live = live.LiveState()


def start(directory):
    global _recorder
    _recorder = trace.install(directory)


def stop():
    global _recorder
    trace.shutdown()
    _recorder = None


def client_batch(side, value):
    return _recorder.client_batch(side, value) if _recorder else trace.config(side)


def register(bp, operator_guard, mobile_guard):
    @bp.route('/delay-analysis')
    def delay_page():
        operator_guard()
        return send_from_directory(Path(__file__).parent, 'delay-analysis.html')

    @bp.route('/delay-analysis.js')
    @bp.route('/delay-analysis.css')
    def delay_assets():
        operator_guard()
        return send_from_directory(Path(__file__).parent, request.path.rsplit('/', 1)[-1])

    @bp.route('/api/delay', methods=['GET', 'POST'])
    def delay_control():
        operator_guard()
        if not _recorder:
            abort(503)
        if request.method == 'GET':
            response = jsonify(_recorder.snapshot(incident=request.args.get('incident')))
        else:
            mobile_guard(mutation=True)
            raw = request.stream.read(2049)
            if len(raw) > 2048:
                abort(413)
            try:
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise ValueError('Expected an object.')
                action = value.get('action')
                if action == 'start':
                    _recorder.start(side=value.get('side', 'both'), seconds=value.get('seconds', 0))
                elif action == 'stop':
                    _recorder.stop()
                elif action == 'clear':
                    _recorder.clear()
                elif action == 'mark':
                    _recorder.mark(value.get('label', 'Operator marked incident'))
                else:
                    raise ValueError('Choose start, stop, clear or mark.')
                _live.bump()
                response = jsonify(_recorder.snapshot())
            except (ValueError, UnicodeDecodeError) as exc:
                return jsonify(error=str(exc)), 400
            except OSError:
                return jsonify(error='Recorder storage is unavailable.'), 503
        response.headers['Cache-Control'] = 'no-store'
        return response

    @bp.route('/api/delay/events')
    def delay_events():
        operator_guard()
        if not _recorder:
            abort(503)
        return _live.stream(_recorder.snapshot, interval=1, shared=True)

    @bp.route('/api/delay/export')
    def delay_export():
        operator_guard()
        if not _recorder or not _recorder.path:
            abort(404)
        snapshot = _recorder.snapshot()
        if request.args.get('format') == 'csv':
            out = io.StringIO()
            keys = ('source', 'name', 'side', 'kind', 'count', 'p50_ms', 'p95_ms', 'p99_ms', 'max_ms', 'total_ms', 'cpu_ms', 'self_ms')
            writer = csv.DictWriter(out, keys, extrasaction='ignore')
            writer.writeheader(); writer.writerows(snapshot['operations'])
            return Response(out.getvalue(), mimetype='text/csv', headers={
                'Content-Disposition': 'attachment; filename=delay-summary.csv', 'Cache-Control': 'no-store'})
        # Open before yielding: a later Clear cannot redirect this export to a new capture.
        with _recorder.control_lock:
            if not _recorder.path:
                abort(404)
            snapshot = _recorder.snapshot()
            handle = _recorder.path.open('r')
        def records():
            try:
                yield json.dumps({k: v for k, v in snapshot.items() if k != 'events'}) + '\n'
                while chunk := handle.read(65536):
                    yield chunk
            finally:
                handle.close()
        return Response(records(), mimetype='application/x-ndjson', headers={
            'Content-Disposition': 'attachment; filename=delay-' + str(snapshot['capture_id']) + '.jsonl',
            'Cache-Control': 'no-store'})
