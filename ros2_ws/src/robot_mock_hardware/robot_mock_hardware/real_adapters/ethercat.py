"""One native bus owner shared by every motor; Python never drives PDO cycles."""
import json
import math
import os
import selectors
import subprocess
import threading
import time

from robot_test_core.adapters import DeviceAdapter, MotorAdapter
from robot_test_core.models import DeviceState, DeviceStatus


class EtherCATBus(DeviceAdapter):
    def __init__(self, config):
        self.config = config
        self.condition = threading.Condition()
        self.process = None
        self.thread = None
        self.snapshot = None
        self.sample_time = 0.0
        self.error = ''
        self.epoch = self.sequence = 0
        self.arm_requested = False
        self.quit = threading.Event()

    def connect(self):
        with self.condition:
            if self.process is not None:
                return
            args = [self.config['executable'], '--monitor' if self.config.get('read_only') else '--run']
            if self.config.get('backend') == 'eyou':
                args.append(self.config.get('interface', 'enp2s0'))
            elif self.config.get('z_zero_counts') is not None:
                args.append(str(int(self.config['z_zero_counts'])))
            log_path = self.config.get('log_file')
            log = open(log_path, 'ab') if log_path else None
            try:
                self.process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                                stderr=log if log else subprocess.DEVNULL, bufsize=0)
            finally:
                if log:
                    log.close()
            os.set_blocking(self.process.stdin.fileno(), False)
            self.thread = threading.Thread(target=self._read, daemon=True, name='ethercat-telemetry')
            self.thread.start()

    def _read(self):
        selector = selectors.DefaultSelector()
        selector.register(self.process.stdout, selectors.EVENT_READ)
        pending = b''
        try:
            while not self.quit.is_set():
                if not selector.select(timeout=.2):
                    continue
                chunk = os.read(self.process.stdout.fileno(), 8192)
                if not chunk:
                    raise RuntimeError(f'EtherCAT process exited: {self.process.poll()}')
                pending += chunk
                while b'\n' in pending:
                    line, pending = pending.split(b'\n', 1)
                    data = json.loads(line)
                    with self.condition:
                        self.snapshot = data
                        self.sample_time = time.monotonic()
                        self.condition.notify_all()
                if len(pending) > 65536:
                    raise ValueError('Invalid EtherCAT telemetry framing')
        except Exception as exc:
            with self.condition:
                self.error = str(exc)
                self.condition.notify_all()
        finally:
            selector.close()

    def _send(self, command):
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError('EtherCAT backend not running')
        data = (command + '\n').encode('ascii')
        if os.write(self.process.stdin.fileno(), data) != len(data):
            raise RuntimeError('EtherCAT command pipe full')

    def _fresh(self):
        return self.snapshot is not None and time.monotonic() - self.sample_time < .25 and not self.error

    def arm(self):
        with self.condition:
            if self.config.get('read_only'):
                raise RuntimeError('Read-only Eyou SDK session')
            if self.arm_requested:
                return
            if not self._fresh() or not self.snapshot['healthy']:
                raise RuntimeError('EtherCAT is not ready')
            self.epoch = time.monotonic_ns()
            self.sequence = 0
            self._send(f'ARM {self.epoch} {time.monotonic_ns()}')
            self.arm_requested = True

    def command(self, axis, value):
        with self.condition:
            if not self.arm_requested or not self._fresh():
                raise RuntimeError('EtherCAT command rejected: disarmed or stale feedback')
            self.sequence += 1
            self._send(f'CMD {self.epoch} {self.sequence} {time.monotonic_ns()} {axis} {value:.12g}')

    def stop(self):
        with self.condition:
            if self.config.get('read_only'):
                raise RuntimeError('Read-only Eyou SDK session cannot command hardware STOP')
            already_stopped = (not self.arm_requested and self._fresh() and self.snapshot['healthy'] and
                               not self.snapshot['armed'] and self.snapshot['epoch'] == self.epoch and
                               all((m['statusword'] & 0x6f) != 0x27 for m in self.snapshot['slaves']))
            if already_stopped:
                return
            self.arm_requested = False
            self.epoch = time.monotonic_ns()
            self._send(f'STOP {self.epoch}')
            deadline = time.monotonic() + .3
            while time.monotonic() < deadline:
                if (self._fresh() and self.snapshot['healthy'] and self.snapshot['epoch'] == self.epoch and
                        not self.snapshot['armed'] and all((m['statusword'] & 0x6f) != 0x27 for m in self.snapshot['slaves'])):
                    return
                self.condition.wait(timeout=max(0, deadline - time.monotonic()))
            raise RuntimeError('EtherCAT disable acknowledgment timeout; hardware stop not confirmed')

    def get_status(self):
        with self.condition:
            if not self._fresh():
                return DeviceStatus(DeviceState.OFFLINE, self.error or 'No fresh PDO feedback', {'backend': self.config.get('backend', 'ethercat')})
            data = self.snapshot
            values = {k: v for k, v in data.items() if k != 'slaves'}
            values.update(backend=self.config.get('backend', 'ethercat'), slave_count=4, read_only=bool(self.config.get('read_only')))
            latched = self.arm_requested and data['epoch'] == self.epoch and not data['armed']
            return DeviceStatus(DeviceState.OK if data['healthy'] and not latched else DeviceState.ERROR,
                                'EtherCAT watchdog/stop latch' if latched else 'EtherCAT SDK feedback', values)

    def disconnect(self):
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=1)
            self.quit.set()
            if self.thread:
                self.thread.join(timeout=1)
            self.process.stdin.close()
            self.process.stdout.close()


class EtherCATMotor(MotorAdapter):
    def __init__(self, bus, config):
        self.bus = bus
        self.config = config
        self.axis = int(config['slave_position'])
        self.torque_mode = config.get('control_mode') == 'torque'
        counts = float(config.get('encoder_counts_per_rev', 65536)) * float(config.get('gear_ratio', 1))
        self.scale = config['lead_m'] / counts if 'lead_m' in config else 2 * math.pi / counts

    def connect(self):
        self.bus.connect()

    def disconnect(self):
        pass  # Shared bus is closed once by the device adapter.

    def enable(self):
        self.bus.arm()

    def disable(self):
        self.bus.stop()

    def stop(self):
        self.bus.stop()

    def jog(self, velocity):
        if self.torque_mode:
            raise ValueError('Torque axis requires set_torque')
        if not math.isfinite(velocity) or abs(velocity) > self.config['max_velocity']:
            raise ValueError('Velocity outside axis limit')
        if self.axis == 3 and self.bus.config.get('z_zero_counts') is None and not self.bus.config.get('allow_unreferenced_z'):
            raise RuntimeError('Z physical zero is not calibrated')
        self.bus.command(self.axis, velocity)

    def set_torque(self, torque):
        if not self.torque_mode or not math.isfinite(torque) or not 0 <= torque <= self.config['torque_raw_max']:
            raise ValueError('Torque outside axis limit')
        self.bus.command(self.axis, torque)

    def get_status(self):
        status = self.bus.get_status()
        with self.bus.condition:
            if not self.bus.snapshot:
                return status
            values = dict(self.bus.snapshot['slaves'][self.axis])
        zero = (self.bus.config.get('z_zero_counts') or 0) if self.axis == 3 else 0
        values.update(position=(values['position_raw'] - zero) * self.scale,
                      velocity=values['velocity_raw'] * self.scale,
                      enabled=(values['statusword'] & 0x6f) == 0x27,
                      position_unit=self.config.get('position_unit', 'encoder_rad'),
                      velocity_unit=self.config.get('velocity_unit', 'encoder_rad/s'),
                      slave_position=self.axis, backend=self.bus.config.get('backend', 'ethercat'), control_mode='torque' if self.torque_mode else 'velocity',
                      homed=self.axis == 3 and self.bus.config.get('z_zero_counts') is not None)
        return DeviceStatus(status.state, status.detail, values)

    def get_position(self):
        return self.get_status().values.get('position', float('nan'))

    def get_velocity(self):
        return self.get_status().values.get('velocity', float('nan'))

    def get_error(self):
        status = self.get_status()
        if 'fault' in status.values:
            return 'Drive statusword reports fault' if status.values['fault'] else ''
        return str(status.values.get('error_code', 'No feedback'))
