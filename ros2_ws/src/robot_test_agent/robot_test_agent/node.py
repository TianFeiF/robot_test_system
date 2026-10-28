import logging
import time
import statistics
import threading
from pathlib import Path
import yaml
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from std_srvs.srv import Trigger, SetBool
import os
from robot_test_msgs.msg import RobotHeartbeat, JogCommand, TorqueCommand
from robot_test_core.logger import CsvLogger
from robot_test_core.config import camera_configs
from .camera_stream import CameraStream
from robot_test_core.adapters import CameraAdapter
from .extensions import TestExtensions
from robot_test_core.models import RobotState
from robot_test_core.controller import RobotController
from robot_test_core.models import DeviceState
from robot_mock_hardware.factory import create_hardware

LOG = logging.getLogger(__name__)

class RobotTestAgent(Node):
    def __init__(self):
        super().__init__('robot_test_agent')
        path = self.declare_parameter('config_file', '').value
        self.config = yaml.safe_load(Path(path).read_text())
        self.config_path = Path(path)
        self.robot_id = self.config['robot']['id']
        if self.get_namespace() != '/' + self.robot_id:
            raise ValueError('Namespace must match configured robot id')
        self.csv = CsvLogger(self.robot_id)
        motors, devices = create_hardware(self.config)
        self.controller = RobotController(motors, devices, self.config, self.event)
        self.extensions = TestExtensions(self)
        self.camera_streams = [
            CameraStream(self, devices[name], settings.get('fps', 5), name, settings.get('transport', 'raw'))
            for name, settings in camera_configs(self.config).items()
            if isinstance(devices.get(name), CameraAdapter)
        ]
        self.started = time.monotonic()
        self.sequence = 0
        self.command_epoch_ns = self.get_clock().now().nanoseconds
        self.home_thread = None
        self.home_cancel = threading.Event()
        self.hb = self.create_publisher(RobotHeartbeat, 'heartbeat', 10)
        self.diag = self.create_publisher(DiagnosticArray, 'diagnostics', 10)
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT, durability=DurabilityPolicy.VOLATILE)
        self.create_subscription(JogCommand, 'jog_command', self.on_jog, qos)
        self.create_subscription(TorqueCommand, 'torque_command', self.on_torque, qos)
        self.create_service(Trigger, 'stop', self.on_stop)
        self.create_service(SetBool, 'arm', self.on_arm)
        self.create_service(Trigger, 'zero_z', self.on_zero_z)
        self.create_service(Trigger, 'home_z', self.on_home_z)
        self.create_timer(0.01, self.tick)
        self.create_timer(1.0 / self.config['test']['heartbeat_hz'], self.heartbeat)
        self.create_timer(1.0 / self.config['test']['diagnostics_hz'], self.diagnostics)

    def event(self, kind: str, detail: str) -> None:
        LOG.info('%s %s %s', self.robot_id, kind, detail)
        self.csv.write('events', event=kind, detail=detail)

    def tick(self) -> None:
        self.controller.tick(time.monotonic())

    def on_arm(self, request, response):
        try:
            if request.data:
                self.controller.arm()
                response.success = True
                response.message = 'Armed'
            else:
                response.success = self.controller.stop('DISARM')
                response.message = self.controller.stop_message
            self.command_epoch_ns = self.get_clock().now().nanoseconds
        except Exception as exc:
            response.success = False
            response.message = str(exc)
        return response

    def on_stop(self, request, response):
        cancel = getattr(self, 'home_cancel', None)
        if cancel is not None:
            cancel.set()
        response.success = self.controller.stop()
        self.command_epoch_ns = self.get_clock().now().nanoseconds
        response.message = self.controller.stop_message
        return response

    def on_zero_z(self, request, response):
        try:
            if self.controller.armed:
                raise RuntimeError('Stop the robot before zeroing Z')
            motor = self.controller.motors.get('z_axis')
            if motor is None or not hasattr(motor, 'zero_reference'):
                raise RuntimeError('Z zero is available only with the EtherCAT Z axis')
            self.controller.stop('ZERO_RESET')
            raw = motor.zero_reference()
            self.config['hardware']['ethercat']['z_zero_counts'] = int(raw)
            temporary = self.config_path.with_suffix(self.config_path.suffix + '.tmp')
            temporary.write_text(yaml.safe_dump(self.config, sort_keys=False, allow_unicode=True))
            os.replace(temporary, self.config_path)
            self.command_epoch_ns = self.get_clock().now().nanoseconds
            self.event('Z_ZERO', f'Z encoder position {raw} set as zero')
            response.success = True
            response.message = f'Z zeroed at encoder count {raw}; restart not required'
        except Exception as exc:
            response.success = False
            response.message = str(exc)
        return response

    def on_home_z(self, request, response):
        """Start homing asynchronously so STOP remains responsive."""
        if self.home_thread is not None and self.home_thread.is_alive():
            response.success = False
            response.message = 'Z homing is already running'
            return response
        if self.controller.armed:
            response.success = False
            response.message = 'Stop the robot before homing Z'
            return response
        self.home_cancel.clear()
        self.home_thread = threading.Thread(target=self._home_z_worker, daemon=True, name='z-homing')
        self.home_thread.start()
        response.success = True
        response.message = 'Z homing started; use STOP to cancel'
        return response

    def _home_z_worker(self):
        """Find the hard zero by a torque spike, three times, then average hits."""
        bus = None
        try:
            motor = self.controller.motors.get('z_axis')
            bus = getattr(motor, 'bus', None)
            if motor is None or bus is None or not hasattr(bus, 'set_z_reference'):
                raise RuntimeError('Z homing is available only with the EtherCAT Z axis')
            settings = self.config.get('hardware', {}).get('ethercat', {}).get('z_homing', {})
            direction = -1 if float(settings.get('direction', -1)) < 0 else 1
            velocity = float(settings.get('approach_velocity', 0.001))
            backoff_velocity = float(settings.get('backoff_velocity', velocity))
            max_velocity = float(self.config['axes']['z_axis']['max_velocity'])
            if not 0 < velocity <= max_velocity or not 0 < backoff_velocity <= max_velocity:
                raise ValueError(f'Z homing velocity must be in (0, {max_velocity}] m/s')
            repetitions = int(settings.get('repetitions', 3))
            if repetitions != 3:
                raise ValueError('Z homing requires exactly three reciprocal movements')
            samples = max(5, int(settings.get('baseline_samples', 20)))
            timeout = float(settings.get('approach_timeout_sec', 600.0))
            z_axis = self.config.get('axes', {}).get('z_axis', {})
            position_min = float(z_axis.get('position_min', 0.0))
            position_max = float(z_axis.get('position_max', 0.5))
            travel_span = max(0.0, position_max - position_min)
            # A fixed 30 s timeout only covers 30 mm at the configured
            # 0.001 m/s homing speed.  Scale the timeout to the full configured
            # stroke, while retaining the operator's larger explicit value.
            timeout = max(timeout, travel_span / velocity * 1.2 + 10.0)
            backoff_sec = float(settings.get('backoff_sec', 0.5))
            torque_delta = float(settings.get('torque_delta_raw', 500))
            torque_ratio = float(settings.get('torque_ratio', 2.0))
            if timeout <= 0 or backoff_sec <= 0 or torque_delta <= 0 or torque_ratio <= 1:
                raise ValueError('Invalid Z homing threshold or timeout configuration')
            self.event('Z_HOME_START', f'direction={direction} velocity={velocity} timeout={timeout:.1f}s repetitions=3')
            self.controller.stop('HOME_RESET')
            baseline_values = []
            deadline = time.monotonic() + 2.0
            while len(baseline_values) < samples and time.monotonic() < deadline:
                if self.home_cancel.is_set(): raise RuntimeError('Z homing cancelled')
                with bus.condition:
                    if not bus._fresh(): raise RuntimeError('No fresh EtherCAT feedback for Z homing')
                    baseline_values.append(abs(float(bus.snapshot['slaves'][3]['torque_raw'])))
                time.sleep(0.02)
            if len(baseline_values) < samples: raise RuntimeError('Timed out collecting Z torque baseline')
            baseline = statistics.mean(baseline_values)
            threshold = max(baseline + torque_delta, baseline * torque_ratio)
            hits = []
            bus.arm()
            try:
                bus.begin_z_homing()
                for repetition in range(repetitions):
                    hit = None
                    deadline = time.monotonic() + timeout
                    while time.monotonic() < deadline:
                        if self.home_cancel.is_set(): raise RuntimeError('Z homing cancelled')
                        bus.command(3, direction * velocity)
                        with bus.condition:
                            if bus._fresh():
                                sample = bus.snapshot['slaves'][3]
                                if abs(float(sample['torque_raw'])) >= threshold:
                                    hit = int(sample['position_raw']); break
                        time.sleep(0.05)
                    if hit is None: raise RuntimeError(f'Z homing movement {repetition + 1}/3 found no torque spike (threshold {threshold:.1f})')
                    hits.append(hit)
                    backoff_deadline = time.monotonic() + backoff_sec
                    while time.monotonic() < backoff_deadline:
                        if self.home_cancel.is_set(): raise RuntimeError('Z homing cancelled')
                        bus.command(3, -direction * backoff_velocity)
                        time.sleep(0.05)
            finally:
                bus.stop()
            if self.home_cancel.is_set(): raise RuntimeError('Z homing cancelled')
            average = int(round(statistics.mean(hits)))
            bus.set_z_reference(average)
            self.config['hardware']['ethercat']['z_zero_counts'] = average
            temporary = self.config_path.with_suffix(self.config_path.suffix + '.tmp')
            temporary.write_text(yaml.safe_dump(self.config, sort_keys=False, allow_unicode=True))
            os.replace(temporary, self.config_path)
            self.command_epoch_ns = self.get_clock().now().nanoseconds
            self.event('Z_HOME', f'hits={hits}, average={average}, threshold={threshold:.1f}')
        except Exception as exc:
            if bus is not None:
                try: bus.stop()
                except Exception: pass
            self.event('Z_HOME_ERROR', str(exc))

    def command_time_valid(self, stamp: int) -> bool:
        age = (self.get_clock().now().nanoseconds - stamp) / 1e9
        if stamp > self.command_epoch_ns and 0 <= age < self.controller.timeout:
            return True
        now = time.monotonic()
        if now - getattr(self, '_last_command_time_warning', float('-inf')) >= 1.0:
            self._last_command_time_warning = now
            self.event('COMMAND_TIME_REJECTED',
                       f'Command age={age:+.6f}s; requires 0 <= age < {self.controller.timeout}s '
                       'and timestamp after ARM/STOP. Check clock synchronization on ground and robot.')
        return False

    def on_jog(self, msg: JogCommand) -> None:
        stamp = msg.stamp.sec * 10**9 + msg.stamp.nanosec
        if not self.command_time_valid(stamp):
            return
        try:
            self.controller.jog(msg.axis, msg.velocity, time.monotonic())
        except (RuntimeError, ValueError) as exc:
            # Rejected commands do not refresh the watchdog.
            self.get_logger().warning(str(exc), throttle_duration_sec=1.0)
        except Exception as exc:
            self.controller.stop('JOG_ERROR')
            self.event('JOG_ERROR', str(exc))

    def heartbeat(self) -> None:
        if self.extensions.heartbeat_drop:
            return
        msg = RobotHeartbeat()
        msg.stamp = self.get_clock().now().to_msg()
        msg.robot_id = self.robot_id
        msg.sequence = self.sequence
        msg.uptime = time.monotonic() - self.started
        msg.state = self.controller.state.value
        msg.control_mode = self.controller.mode.value
        self.sequence += 1
        self.hb.publish(msg)

    def on_torque(self, msg: TorqueCommand) -> None:
        stamp = msg.stamp.sec * 10**9 + msg.stamp.nanosec
        if not self.command_time_valid(stamp):
            return
        try:
            self.controller.torque(msg.axis, msg.torque, time.monotonic())
        except (RuntimeError, ValueError) as exc:
            self.get_logger().warning(str(exc), throttle_duration_sec=1.0)
        except Exception as exc:
            self.controller.stop('TORQUE_ERROR')
            self.event('TORQUE_ERROR', str(exc))

    def diagnostics(self) -> None:
        msg = DiagnosticArray()
        msg.header.stamp = self.get_clock().now().to_msg()
        levels = {DeviceState.OK: 0, DeviceState.WARN: 1, DeviceState.ERROR: 2, DeviceState.OFFLINE: 3, DeviceState.UNKNOWN: 3}
        system = DiagnosticStatus(name='System', hardware_id=self.robot_id, level=bytes([0]), message=self.controller.state.value)
        auto = self.controller.auto
        # The all-axis cycle has no single POS/NEG state.  Keep the legacy
        # state when a legacy cycle provides it, otherwise expose a stable
        # RUNNING value instead of letting the diagnostics timer crash the
        # entire agent while motion is active.
        auto_state = 'IDLE'
        if auto is not None:
            state = getattr(auto, 'state', None)
            auto_state = getattr(state, 'value', state) or 'RUNNING'
        system.values = [KeyValue(key='auto_state', value=str(auto_state)), KeyValue(key='armed', value=str(self.controller.armed)), KeyValue(key='control_mode', value=self.controller.mode.value)]
        msg.status.append(system)
        system.values.append(KeyValue(key='monitor_only', value=str(bool(self.config.get('robot', {}).get('monitor_only', False)))))
        for name in self.controller.all_devices:
            status = self.controller.status(name)
            item = DiagnosticStatus(name=name, hardware_id=self.robot_id, level=bytes([levels[status.state]]), message=status.state.value + ': ' + status.detail)
            item.values = [KeyValue(key=k, value=str(v)) for k, v in status.values.items()]
            msg.status.append(item)
            previous = self.extensions.previous.get(name)
            if previous != status.state.value:
                self.csv.write('events', device=name, level=status.state.value, event='DEVICE_TRANSITION', detail=f'{previous} -> {status.state.value}: {status.detail}')
                self.extensions.previous[name] = status.state.value
        levels_seen = [int.from_bytes(s.level, 'little') for s in msg.status[1:]]
        if any(level >= 2 for level in levels_seen):
            self.controller.state = RobotState.FAULT
        elif any(level == 1 for level in levels_seen):
            self.controller.state = RobotState.WARNING
        elif self.controller.state in (RobotState.FAULT, RobotState.WARNING):
            self.controller.state = RobotState.RUNNING if self.controller.armed else RobotState.STOPPED
        msg.status[0].message = self.controller.state.value
        msg.status[0].level = bytes([max(levels_seen, default=0)])
        self.diag.publish(msg)

    def destroy_node(self):
        for stream in self.camera_streams:
            stream.close()
        self.controller.close()
        self.csv.close()
        return super().destroy_node()

def main(args=None):
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    rclpy.init(args=args)
    node = None
    try:
        node = RobotTestAgent()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
