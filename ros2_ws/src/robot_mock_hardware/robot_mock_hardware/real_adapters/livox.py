"""Own an isolated vendor SDK process; report actual point/IMU reception."""
import json
import selectors
import subprocess

from robot_test_core.models import DeviceState, DeviceStatus
from .telemetry import PollingDevice


class LivoxMonitor(PollingDevice):
    def __init__(self, config):
        super().__init__(config)
        self.process = None
        self.selector = None
        self._restarts = 0

    def disconnect(self):
        self._quit.set()
        if self._thread:
            self._thread.join(timeout=6)

    def _close_process(self):
        if self.selector:
            self.selector.close()
            self.selector = None
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=1)
            self.process.stdout.close()
            self.process = None

    def _run(self):
        try:
            super()._run()
        finally:
            self._close_process()

    def poll(self):
        if self.process is None:
            self.process = subprocess.Popen([self.config['executable'], self.config['sdk_config'], self.config['host']],
                                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
            self.selector = selectors.DefaultSelector()
            self.selector.register(self.process.stdout, selectors.EVENT_READ)
            self._restarts += 1
        try:
            if not self.selector.select(timeout=3):
                raise TimeoutError('Livox SDK telemetry timeout')
            line = self.process.stdout.readline(8192)
            if not line:
                raise RuntimeError(f'Livox SDK exited: {self.process.poll()}')
            values = json.loads(line)
            values.update(host=self.config['host'], model='MID360s', sdk_process_count=self._restarts)
            fresh = 0 <= values['last_packet_age_ms'] < 2000
            state = DeviceState.OK if fresh else DeviceState.OFFLINE
            if fresh and values['command_error_count']:
                state = DeviceState.WARN
            return DeviceStatus(state, 'Actual point/IMU packet reception; SDK counters reset on process restart', values)
        except Exception:
            self._close_process()
            raise
