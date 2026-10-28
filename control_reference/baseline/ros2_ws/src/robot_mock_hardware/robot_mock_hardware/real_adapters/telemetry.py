"""Read-only hardware polling in workers, never in the motion executor."""
import json
import math
import re
import subprocess
import threading
import time
from pathlib import Path

from robot_test_core.adapters import DeviceAdapter, MotorAdapter
from robot_test_core.models import DeviceState, DeviceStatus


class PollingDevice(DeviceAdapter):
    def __init__(self, config):
        self.config = config
        self._lock = threading.Lock()
        self._quit = threading.Event()
        self._thread = None
        self._status = DeviceStatus(DeviceState.UNKNOWN, 'Waiting for hardware sample')
        self._sample_time = 0.0
        self._samples = self._errors = self._recoveries = 0
        self._failed = False

    def connect(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def disconnect(self):
        self._quit.set()
        if self._thread:
            self._thread.join(timeout=0.1)

    def command(self, args):
        return subprocess.run(args, capture_output=True, text=True, check=True,
                              timeout=float(self.config.get('timeout_sec', 2))).stdout

    def _run(self):
        while not self._quit.is_set():
            try:
                status = self.poll()
                self._samples += 1
                if self._failed:
                    self._recoveries += 1
                self._failed = False
            except Exception as exc:
                self._errors += 1
                self._failed = True
                status = DeviceStatus(DeviceState.OFFLINE, str(exc))
            status.values.update(sample_count=self._samples, error_count=self._errors,
                                 recover_count=self._recoveries, read_only=True,
                                 backend=self.config['backend'])
            with self._lock:
                self._status = status
                self._sample_time = time.monotonic()
            self._quit.wait(float(self.config.get('poll_sec', 2)))

    def get_status(self):
        with self._lock:
            status = self._status
            age = time.monotonic() - self._sample_time
            if self._quit.is_set() or (self._sample_time and age > float(self.config.get('stale_sec', 15))):
                return DeviceStatus(DeviceState.OFFLINE, 'No recent hardware sample', dict(status.values))
            return DeviceStatus(status.state, status.detail, dict(status.values))


class EtherCATMonitor(PollingDevice):
    """IgH CLI reads only. No master activation, downloads or controlwords."""
    def poll(self):
        cli = self.config.get('executable', '/usr/local/bin/ethercat')
        listing = self.command([cli, 'slaves'])
        slaves = []
        for line in listing.splitlines():
            match = re.match(r'^\s*(\d+)\s+\d+:\d+\s+(\S+)\s+([+E])\s+(.+)$', line)
            if match:
                slaves.append((int(match[1]), match[2], match[3]))
        values = {'slave_count': len(slaves), 'expected_slaves': self.config.get('expected_slaves', 4)}
        interface = self.config.get('interface', 'enp2s0')
        for counter in ('rx_crc_errors', 'rx_frame_errors', 'rx_errors', 'tx_errors'):
            path = Path('/sys/class/net') / interface / 'statistics' / counter
            if path.exists():
                values[counter] = int(path.read_text().strip())
        state = DeviceState.WARN
        detail = 'Read-only EtherCAT telemetry; motion control unavailable'
        if len(slaves) != values['expected_slaves'] or any(s[2] == 'E' for s in slaves):
            state, detail = DeviceState.ERROR, 'EtherCAT slave count/state mismatch'
        for position, bus_state, flag in slaves:
            prefix = f'slave_{position}'
            values[prefix + '_state'] = bus_state
            for name, index, datatype in [('statusword', '0x6041', 'uint16'),
                                           ('position_raw', '0x6064', 'int32'),
                                           ('velocity_raw', '0x606c', 'int32'),
                                           ('torque_raw', '0x6077', 'int16'),
                                           ('operation_mode', '0x6061', 'int8'),
                                           ('error_code', '0x603f', 'uint16')]:
                if self._quit.is_set():
                    return DeviceStatus(DeviceState.OFFLINE, 'Disconnected', values)
                output = self.command([cli, 'upload', '-p', str(position), '-t', datatype, index, '0'])
                values[prefix + '_' + name] = int(output.split()[-1])
            if values[prefix + '_error_code'] or values[prefix + '_statusword'] & 8:
                state, detail = DeviceState.ERROR, 'Servo reports fault; inspect raw status'
        return DeviceStatus(state, detail, values)


class RM75Monitor(PollingDevice):
    def poll(self):
        output = self.command([self.config['executable'], self.config['host'],
                               str(self.config.get('port', 8080))])
        # Vendor SDK may print informational text before our JSON record.
        records = [line for line in output.splitlines() if line.startswith('{')]
        values = json.loads(records[-1])
        errors = values['arm_errors']
        return DeviceStatus(DeviceState.ERROR if any(errors) else DeviceState.OK,
                            'RM75 read-only joint/arm state; no motion control', values)


class EtherCATReadOnlyMotor(MotorAdapter):
    def __init__(self, bus, config):
        self.bus = bus
        self.position = int(config['slave_position'])
        self.config = config
        counts = float(config.get('encoder_counts_per_rev', 1)) * float(config.get('gear_ratio', 1))
        if counts <= 0 or not math.isfinite(counts):
            raise ValueError('Encoder counts and gear ratio must be finite and positive')
        self.scale = (float(config['lead_m']) / counts if 'lead_m' in config else
                      2 * math.pi / counts if config.get('position_unit') == 'rad' else 1.0)

    def connect(self):
        pass

    def disconnect(self):
        pass

    def enable(self):
        raise RuntimeError('Read-only EtherCAT: motion control unavailable')

    def jog(self, velocity):
        self.enable()

    def stop(self):
        raise RuntimeError('Read-only EtherCAT: hardware STOP is not implemented')

    disable = stop

    def get_status(self):
        status = self.bus.get_status()
        prefix = f'slave_{self.position}_'
        values = {k[len(prefix):]: v for k, v in status.values.items() if k.startswith(prefix)}
        values.update(slave_position=self.position, backend='ethercat_monitor',
                      read_only=True, position_unit=self.config.get('position_unit', 'encoder_counts'),
                      velocity_unit=self.config.get('velocity_unit', 'encoder_counts/s'),
                      control_mode=self.config.get('control_mode', 'velocity'), homed=False)
        if 'statusword' not in values:
            return DeviceStatus(DeviceState.OFFLINE, 'No servo sample', values)
        values['position'] = values['position_raw'] * self.scale
        values['velocity'] = values['velocity_raw'] * self.scale
        values['enabled'] = (values['statusword'] & 0x6f) == 0x27
        return DeviceStatus(status.state, status.detail, values)

    def get_position(self):
        return self.get_status().values.get('position', float('nan'))

    def get_velocity(self):
        return self.get_status().values.get('velocity', float('nan'))

    def get_error(self):
        return str(self.get_status().values.get('error_code', 'No servo sample'))


class UnavailableDevice(DeviceAdapter):
    def __init__(self, config):
        self.config = config

    def connect(self):
        pass

    def disconnect(self):
        pass

    def get_status(self):
        return DeviceStatus(DeviceState.OFFLINE, self.config['reason'],
                            {'backend': 'unavailable', 'read_only': True})
