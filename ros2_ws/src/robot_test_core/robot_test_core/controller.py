"""Transport-independent motion safety. Called by one serialized executor only."""
import math
import time
from typing import Callable, Dict
from .auto_cycle import AutoCycle
from .adapters import MotorAdapter, DeviceAdapter
from .models import RobotState, ControlMode, DeviceState, DeviceStatus

class RobotController:
    def __init__(self, motors: Dict[str, MotorAdapter], devices: Dict[str, DeviceAdapter], config: dict,
                 event: Callable[[str, str], None] = lambda *_: None):
        self.motors = motors
        self.devices = devices
        self.config = config
        self.event = event
        self.state = RobotState.INITIALIZING
        self.mode = ControlMode.MONITOR
        self.armed = False
        self.auto = None
        self.last_commands: Dict[str, float] = {}
        self.exceptions: Dict[str, str] = {}
        self.stop_errors: Dict[str, str] = {}
        self.stop_message = ''
        self.timeout = float(config['test']['watchdog_timeout_ms']) / 1000
        if not 0 < self.timeout <= 0.5:
            raise ValueError('Demo watchdog must be in (0, 500] ms')
        self.last_tick = time.monotonic()
        for name, adapter in self.all_devices.items():
            try:
                adapter.connect()
            except Exception as exc:
                self.exceptions[name] = str(exc)
                event('CONNECT_ERROR', f'{name}: {exc}')
        self.state = RobotState.READY

    @property
    def monitor_only(self) -> bool:
        return bool(self.config.get('robot', {}).get('monitor_only', False))

    @property
    def all_devices(self) -> Dict[str, DeviceAdapter]:
        return {**self.motors, **self.devices}

    def status(self, name: str) -> DeviceStatus:
        if name in self.exceptions:
            return DeviceStatus(DeviceState.ERROR, self.exceptions[name])
        try:
            return self.all_devices[name].get_status()
        except Exception as exc:
            self.exceptions[name] = str(exc)
            self.event('READ_ERROR', f'{name}: {exc}')
            return DeviceStatus(DeviceState.ERROR, str(exc))

    def motion_healthy(self) -> bool:
        names = list(self.motors) + [n for n in ('ethercat', 'canopen') if n in self.devices]
        return all(self.status(n).state == DeviceState.OK for n in names)

    def arm(self) -> None:
        if self.config.get('robot', {}).get('monitor_only', False) or not self.motors:
            raise RuntimeError('Monitor-only deployment: motion is unavailable')
        if not self.motion_healthy():
            raise RuntimeError('Motion device fault; clear fault before arming')
        self.stop('ARM_RESET')
        if self.stop_errors:
            raise RuntimeError('Cannot arm: stopping/disabling a motor failed')
        try:
            for motor in self.motors.values():
                motor.enable()
        except Exception:
            self.stop('ENABLE_FAILED')
            raise
        self.armed = True
        self.mode = ControlMode.MANUAL
        self.state = RobotState.READY
        self.event('ARM', 'Manual motion enabled')

    def jog(self, axis: str, velocity: float, now: float) -> None:
        if not self.armed or self.mode != ControlMode.MANUAL:
            raise RuntimeError('Motion disarmed')
        if axis not in self.motors:
            raise ValueError('Unknown axis')
        if self.config['axes'][axis].get('control_mode') == 'torque':
            raise ValueError('Torque axis rejects velocity commands')
        if not math.isfinite(velocity) or abs(velocity) > self.config['axes'][axis]['max_velocity']:
            raise ValueError('Velocity outside configured limit')
        if not self.motion_healthy():
            self.stop('MOTION_FAULT')
            raise RuntimeError('Motion device fault')
        self.motors[axis].jog(velocity)
        self.last_commands[axis] = now
        self.state = RobotState.RUNNING if velocity else RobotState.READY

    def torque(self, axis: str, torque: float, now: float) -> None:
        if not self.armed or self.mode != ControlMode.MANUAL:
            raise RuntimeError('Motion disarmed')
        cfg = self.config['axes'].get(axis, {})
        if axis not in self.motors or cfg.get('control_mode') != 'torque':
            raise ValueError('Not a torque axis')
        torque_min = cfg.get('torque_raw_min', 0)
        torque_max = cfg['torque_raw_max']
        if not math.isfinite(torque) or not torque_min <= torque <= torque_max:
            raise ValueError(f'Torque outside configured limit [{torque_min}, {torque_max}]')
        if not self.motion_healthy():
            self.stop('MOTION_FAULT')
            raise RuntimeError('Motion device fault')
        self.motors[axis].set_torque(torque)
        self.last_commands[axis] = now
        self.state = RobotState.RUNNING if torque else RobotState.READY

    def start_auto(self) -> None:
        cfg = self.config['test']['auto_cycle']
        axis = cfg['axis']
        numeric = [cfg[k] for k in ('velocity', 'positive_target', 'negative_target', 'dwell_sec')]
        if not cfg['enabled'] or axis not in self.motors or not all(math.isfinite(v) for v in numeric):
            raise ValueError('Invalid auto-cycle configuration')
        if not 0 < cfg['velocity'] <= self.config['axes'][axis]['max_velocity'] or cfg['positive_target'] <= cfg['negative_target'] or cfg['dwell_sec'] < 0:
            raise ValueError('Unsafe auto-cycle limits')
        self.arm()
        self.mode = ControlMode.AUTO_TEST
        self.last_commands['__auto__'] = time.monotonic()
        self.auto = AutoCycle(self.motors[axis], cfg)
        self.state = RobotState.RUNNING
        self.event('AUTO_START', axis)

    def stop(self, reason: str = 'STOP') -> bool:
        if self.monitor_only:
            self.stop_message = 'Monitor-only deployment: hardware STOP/disable unavailable; no hardware command sent'
            self.event('STOP_UNSUPPORTED', f'{reason}: {self.stop_message}')
            return False
        # Disarm first: queued/repeated JOG messages cannot restart after STOP.
        self.armed = False
        self.mode = ControlMode.MONITOR
        self.auto = None
        self.last_commands.clear()
        self.stop_errors.clear()
        for name, motor in self.motors.items():
            # Attempt disable even if stop raises, and always continue to other axes.
            for operation in (motor.stop, motor.disable):
                try:
                    operation()
                except Exception as exc:
                    detail = f'{operation.__name__}: {exc}'
                    self.exceptions[name] = detail
                    self.stop_errors[name] = detail
                    self.event('STOP_ERROR', f'{name}: {detail}')
        self.state = RobotState.FAULT if self.stop_errors else RobotState.STOPPED
        self.stop_message = 'Stop attempted; inspect motor errors' if self.stop_errors else 'All motors stopped and disarmed'
        self.event(reason, self.stop_message)
        return not bool(self.stop_errors)

    def tick(self, now: float) -> None:
        dt = max(0.0, now - self.last_tick)
        self.last_tick = now
        if self.armed and (dt > self.timeout or any(now - t >= self.timeout for t in self.last_commands.values())):
            self.stop('WATCHDOG')
        if self.armed and not self.motion_healthy():
            self.stop('MOTION_FAULT')
        if self.armed and self.auto:
            try:
                self.auto.tick(now, dt)
            except Exception as exc:
                self.stop('AUTO_ERROR')
                self.event('AUTO_ERROR', str(exc))
        for name, adapter in self.all_devices.items():
            try:
                adapter.update(min(dt, self.timeout))
            except Exception as exc:
                if name not in self.exceptions:
                    self.event('DEVICE_ERROR', f'{name}: {exc}')
                self.exceptions[name] = str(exc)
                if name in self.motors or name in ('ethercat', 'canopen'):
                    self.stop('MOTION_FAULT')

    def close(self) -> None:
        if self.monitor_only:
            self.event('SHUTDOWN', 'Closing monitor resources; no hardware STOP/disable commanded')
        else:
            self.stop('SHUTDOWN')
        for name, adapter in self.all_devices.items():
            try:
                adapter.disconnect()
            except Exception as exc:
                self.event('DISCONNECT_ERROR', f'{name}: {exc}')
