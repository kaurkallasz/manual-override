"""Relay-owned driver process; game/vision GIL stalls cannot delay robot feedback.

Only this process constructs the existing driver and owns that arm's sockets.
The hub still validates commands and leases. A separate two-second parent
watchdog stops the driver if the hub stalls or dies; workers never reconnect.
"""
from shared import delay_trace as trace
import atexit
import multiprocessing
import os
import runpy
import sys
import threading
import time

# The spawned child loads this owned file directly, outside the hub's helper
# cache. Resolve its driver beside it, even if the parent's search path changed.
if __name__ == '__relay_worker__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from relay_arm import DobotMG400, DobotError

PARENT_TIMEOUT = 2.0  # Same maximum lifetime as the relay's controller lease.
MOTION_REQUEST_MAX_AGE = .25
READ_METHODS = frozenset(('get_state', 'get_target', 'control_mode', 'is_connected'))
STOP_METHODS = frozenset(('hold', 'reset_motion', 'stop_servo'))
COMMAND_METHODS = frozenset((
    'connect', 'clear_error', 'enable', 'disable', 'reset_motion',
    'wait_for_motion_feedback', 'set_max_accel_cartesian', 'set_max_accel_joint',
    'set_max_velocity_cartesian', 'set_max_velocity_joint', 'hold',
    'positive_solution', 'set_pump', 'set_target_joints', 'set_target_pose',
    'start_servo', 'stop_servo',
))


def _reply(robot, connection, allowed):
    request = connection.recv()
    name, args, kwargs, deadline = request[:4]
    # A hub already running the preceding code may spawn this updated file
    # before its planned restart. Preserve that parent's four-field protocol.
    diagnostics = request[4] if len(request) == 5 else {
        'contract': trace.CONTRACT, 'version': trace.VERSION, 'recording': False}
    trace.remote_config(diagnostics, diagnostics.get('source', 'worker'))
    try:
        if name not in allowed:
            raise ValueError('Unknown relay driver operation')
        if time.monotonic() > deadline:
            raise DobotError(-1, 'Expired driver request; reconnect before moving.', name)
        value = trace.call('worker.execute.' + name, getattr(robot, name), *args, **kwargs)
        if name == 'connect':
            value = robot.iface
        response = (True, value)
    except DobotError as exc:
        response = (False, (exc.errid, exc.resp, exc.command))
    except Exception as exc:
        response = (False, (-1, str(exc), name))
    connection.send((*response, trace.remote_batch()) if len(request) == 5 else response)


def _run_worker(command, reads, pulse, config, driver_factory=None):
    robot = (driver_factory or DobotMG400)(**config)
    stopped = threading.Event()
    shutdown = threading.Event()

    def telemetry():
        try:
            while not stopped.is_set():
                if reads.poll(.05):
                    _reply(robot, reads, READ_METHODS | STOP_METHODS)
        except (EOFError, OSError):
            shutdown.set()

    def watchdog():
        while not shutdown.wait(.05):
            if not 0 <= time.monotonic() - pulse.value <= PARENT_TIMEOUT:
                break
        # Latch before blocking dashboard I/O. EOF and a missed heartbeat both
        # stop independently of a command whose robot reply is still pending.
        stopped.set()
        try:
            robot.reset_motion()
        except Exception:
            pass
        try:
            robot.stop_robot()
        except Exception:
            pass
        try:
            robot.set_pump('off', 2, 1)
        except Exception:
            pass

    reader = threading.Thread(target=telemetry, name='relay-worker-status', daemon=True)
    guard = threading.Thread(target=watchdog, name='relay-worker-watchdog', daemon=True)
    reader.start()
    guard.start()
    try:
        while not stopped.is_set():
            if command.poll(.05):
                _reply(robot, command, COMMAND_METHODS)
    except (EOFError, OSError):
        pass
    finally:
        shutdown.set()
        # A parent-timeout guard must finish its Stop/pump-off before close
        # takes away the dashboard socket it is using.
        guard.join(config['command_timeout'] * 3 + 2)
        # Closing owns StopRobot and socket teardown. No driver exists in the
        # parent, and no replacement is started after a worker failure.
        try:
            robot.close()
        finally:
            command.close()
            reads.close()
            reader.join(.2)


class ArmWorker:
    _blank_state = staticmethod(DobotMG400._blank_state)

    def __init__(self, ip, iface=None, local_ip=None, connect_timeout=5., command_timeout=5.,
                 *, _driver_factory=None):
        self.iface = iface
        self._config = dict(ip=ip, iface=iface, local_ip=local_ip,
                            connect_timeout=connect_timeout, command_timeout=command_timeout)
        self._driver_factory = _driver_factory
        self._process = None
        self._command = self._reads = None
        self._command_lock, self._read_lock = threading.Lock(), threading.Lock()
        self._stop = threading.Event()
        self._pulse_thread = None
        self._error = None

    def connect(self):
        if self._process is not None:
            raise DobotError(-1, 'Driver already started; create a new connection.', 'connect')
        command = reads = None
        try:
            context = multiprocessing.get_context('spawn')
            self._pulse = context.Value('d', time.monotonic(), lock=False)
            self._command, command = context.Pipe()
            self._reads, reads = context.Pipe()
            # Sandbox._load_one removes helpers from sys.modules. Pickling a
            # cached _run_worker or DobotMG400 then fails its identity check.
            # Spawn via the stable stdlib entry point and import the driver in
            # the child; only pipes, config and the optional test factory cross.
            self._process = context.Process(target=runpy.run_path,
                args=(os.path.abspath(__file__),), kwargs={
                    'run_name': '__relay_worker__',
                    'init_globals': {'_worker_args': (
                        command, reads, self._pulse, self._config, self._driver_factory)}},
                name='dobot-' + str(self._config['local_ip'] or self._config['ip']), daemon=True)
            self._process.start()
            # Run before multiprocessing's daemon termination at normal Python
            # exit, so the driver gets its StopRobot/socket teardown first.
            atexit.register(self.close)
            command.close()
            reads.close()
            self._pulse_thread = threading.Thread(target=self._heartbeat,
                name='relay-driver-heartbeat', daemon=True)
            self._pulse_thread.start()
            self.iface = self._call('connect')
        except Exception as exc:
            if command is not None:
                command.close()
            if reads is not None:
                reads.close()
            self.close()
            if isinstance(exc, DobotError):
                raise
            raise DobotError(-1, f'Relay worker startup failed: {exc}', 'connect') from exc

    def _heartbeat(self):
        while not self._stop.wait(.1):
            if not self._process.is_alive():
                break
            self._pulse.value = time.monotonic()

    @trace.traced('worker.call', side='self')
    def _call(self, name, *args, **kwargs):
        read = name in READ_METHODS | STOP_METHODS
        connection = self._reads if read else self._command
        lock = self._read_lock if read else self._command_lock
        # Connect opens three sockets; calibration FK may use dashboard I/O.
        timeout = 3 * self._config['connect_timeout'] + 2 if name == 'connect' else self._config['command_timeout'] + 3
        deadline = time.monotonic() + timeout
        motion = name in ('start_servo', 'set_target_pose', 'set_target_joints') or (
            name == 'set_pump' and args and args[0] != 'off')
        admission = time.monotonic() + (MOTION_REQUEST_MAX_AGE if motion else timeout)
        if not trace.call('worker.ipc_lock_wait', lock.acquire, timeout=max(0, admission - time.monotonic())):
            raise DobotError(-1, 'Driver request expired while waiting; target was not sent.', name)
        try:
            if self._stop.is_set() or self._process is None or not self._process.is_alive():
                raise DobotError(-1, self._error or 'Relay driver unavailable. Reconnect.', name)
            if time.monotonic() > admission:
                raise DobotError(-1, 'Driver request expired; target was not sent.', name)
            try:
                side = getattr(self, 'side', None)
                diagnostics = {**trace.config(side), 'source': 'worker.' + (side or 'unknown'), 'parent': trace.context()}
                trace.annotate(side=side)
                connection.send((name, args, kwargs, admission, diagnostics))
                if not trace.call('worker.ipc_response_wait', connection.poll, max(0, deadline - time.monotonic())):
                    raise TimeoutError('Relay driver response timed out. Reconnect.')
                ok, result, timings = connection.recv()
                trace.accept_remote(timings, diagnostics['source'])
            except (OSError, EOFError, TimeoutError) as exc:
                self._error = str(exc)
                self._stop.set()  # Stop renewing; child watchdog cancels targets.
                raise DobotError(-1, self._error, name) from exc
            if not ok:
                raise DobotError(*result)
            return result
        finally:
            lock.release()

    def get_state(self):
        try:
            return self._call('get_state')
        except DobotError as exc:
            if trace.enabled():
                process = self._process
                trace.evidence('worker.driver_unavailable', {
                    'driver_error': str(exc), 'error_kind': type(exc.__cause__ or exc).__name__,
                    'operation': 'get_state', 'pid': process.pid if process else None,
                    'alive': bool(process and process.is_alive()), 'exitcode': process.exitcode if process else None,
                    'heartbeat_age_ms': (time.monotonic()-self._pulse.value)*1000 if hasattr(self, '_pulse') else None,
                    'motion_invalidation': 'driver_unavailable'}, side=getattr(self, 'side', None), incident=True)
            return dict(self._blank_state(), servo_error=str(exc), motion_ready=False,
                        motion_epoch=None, motion_invalidation='driver_unavailable')

    def get_target(self):
        return self._read_or_none('get_target')

    def _read_or_none(self, name):
        try:
            return self._call(name)
        except DobotError:
            return None

    def control_mode(self):
        return self._read_or_none('control_mode')

    def is_connected(self):
        return self.get_state().get('connected') is True

    def __getattr__(self, name):
        if name not in COMMAND_METHODS:
            raise AttributeError(name)
        return lambda *args, **kwargs: self._call(name, *args, **kwargs)

    def close(self):
        atexit.unregister(self.close)
        self._stop.set()
        # EOF wakes the command loop, whose finally closes the real driver.
        if self._command is not None:
            self._command.close()
        if self._pulse_thread is not None:
            self._pulse_thread.join(.3)
        if self._process is not None and self._process.pid is not None:
            self._process.join(self._config['command_timeout'] + 2)
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(2)
        if self._reads is not None:
            self._reads.close()


if __name__ == '__relay_worker__':
    _run_worker(*_worker_args)
