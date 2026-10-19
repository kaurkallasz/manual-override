"""Compare capture off/on using the real facade over the isolated game fixture."""
import json
import statistics
import tempfile
import time
from mobile_ltz_fixture import create_app
from shared import delay_trace as trace


def main():
    with tempfile.TemporaryDirectory(prefix='delay-benchmark-') as folder:
        app, game = create_app(folder)
        snapshot = app.view_functions['mobile_ltz_api.mobile_state_api'].__globals__['mobile_snapshot']
        try:
            for _ in range(15):
                snapshot('green')
            samples = {'off': [], 'on': []}
            for mode in ('off', 'on', 'on', 'off'):
                if mode == 'on' and not trace.enabled():
                    trace._recorder.start(seconds=60)
                elif mode == 'off':
                    trace._recorder.stop(); trace._recorder.drain()
                for _ in range(100):
                    started = time.perf_counter_ns()
                    snapshot('green')
                    samples[mode].append((time.perf_counter_ns()-started)/1e6)
                    time.sleep(.05)  # 20 builds/s: two players at the normal 10 Hz cadence.
            def summary(values):
                return {'median_ms':statistics.median(values),'p95_ms':sorted(values)[int(len(values)*.95)],
                        'mean_ms':statistics.mean(values),'max_ms':max(values),'samples':len(values)}
            result = {mode:summary(values) for mode, values in samples.items()}
            result['added_median_ms'] = result['on']['median_ms']-result['off']['median_ms']
            result['added_p95_ms'] = result['on']['p95_ms']-result['off']['p95_ms']
            result['dropped'] = trace._recorder.dropped
            print(json.dumps(result,indent=2))
        finally:
            game.hub_stop(); app.config['fixture_cleanup']()


if __name__ == '__main__':
    main()
