import logging
import time
from pathlib import Path
import yaml
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from std_srvs.srv import Trigger, SetBool
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
        self.hb = self.create_publisher(RobotHeartbeat, 'heartbeat', 10)
        self.diag = self.create_publisher(DiagnosticArray, 'diagnostics', 10)
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT, durability=DurabilityPolicy.VOLATILE)
        self.create_subscription(JogCommand, 'jog_command', self.on_jog, qos)
        self.create_subscription(TorqueCommand, 'torque_command', self.on_torque, qos)
        self.create_service(Trigger, 'stop', self.on_stop)
        self.create_service(SetBool, 'arm', self.on_arm)
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
        response.success = self.controller.stop()
        self.command_epoch_ns = self.get_clock().now().nanoseconds
        response.message = self.controller.stop_message
        return response

    def on_jog(self, msg: JogCommand) -> None:
        stamp = msg.stamp.sec * 10**9 + msg.stamp.nanosec
        age = (self.get_clock().now().nanoseconds - stamp) / 1e9
        if stamp <= self.command_epoch_ns or not 0 <= age < self.controller.timeout:
            return
        try:
            self.controller.jog(msg.axis, msg.velocity, time.monotonic())
        except (RuntimeError, ValueError) as exc:
            # Rejected commands do not refresh the watchdog.
            self.get_logger().debug(str(exc))
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
        age = (self.get_clock().now().nanoseconds - stamp) / 1e9
        if stamp <= self.command_epoch_ns or not 0 <= age < self.controller.timeout:
            return
        try:
            self.controller.torque(msg.axis, msg.torque, time.monotonic())
        except (RuntimeError, ValueError) as exc:
            self.get_logger().debug(str(exc))
        except Exception as exc:
            self.controller.stop('TORQUE_ERROR')
            self.event('TORQUE_ERROR', str(exc))

    def diagnostics(self) -> None:
        msg = DiagnosticArray()
        msg.header.stamp = self.get_clock().now().to_msg()
        levels = {DeviceState.OK: 0, DeviceState.WARN: 1, DeviceState.ERROR: 2, DeviceState.OFFLINE: 3, DeviceState.UNKNOWN: 3}
        system = DiagnosticStatus(name='System', hardware_id=self.robot_id, level=bytes([0]), message=self.controller.state.value)
        system.values = [KeyValue(key='auto_state', value=self.controller.auto.state.value if self.controller.auto else 'IDLE'), KeyValue(key='armed', value=str(self.controller.armed)), KeyValue(key='control_mode', value=self.controller.mode.value)]
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
