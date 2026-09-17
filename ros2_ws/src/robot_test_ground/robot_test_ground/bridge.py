from robot_test_core.config import camera_configs
import copy
import json
import uuid
from builtin_interfaces.msg import Time
from robot_test_msgs.msg import TestEvent
from robot_test_msgs.srv import InjectFault
from robot_test_core.logger import CsvLogger, ros_timestamp
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Dict
import rclpy
from rclpy.node import Node
from rclpy.executors import SingleThreadedExecutor
from rclpy.qos import QoSProfile, ReliabilityPolicy
from PySide6.QtCore import QObject, Signal
from sensor_msgs.msg import Image
from rclpy.qos import qos_profile_sensor_data
from diagnostic_msgs.msg import DiagnosticArray
from std_srvs.srv import Trigger, SetBool
from robot_test_msgs.msg import RobotHeartbeat, JogCommand

@dataclass
class RobotViewModel:
    robot_id: str
    last_heartbeat: float = 0.0
    robot_state: str = 'OFFLINE'
    control_mode: str = 'MONITOR'
    uptime: float = 0.0
    sequence: int = 0
    devices: Dict[str, dict] = field(default_factory=dict)

    @property
    def online(self) -> bool:
        return self.last_heartbeat > 0 and time.monotonic() - self.last_heartbeat < 3.0

class Signals(QObject):
    changed = Signal(str)
    result = Signal(str, str, int, bool, str)

class GroundBridge(Node):
    """Executor owns ROS work; UI submits commands through a thread-safe queue."""
    def __init__(self, configs: dict):
        robot_ids = configs.keys()
        super().__init__('ground_station')
        self.signals = Signals()
        self.csv = CsvLogger('ground')
        self.online_states = {rid: False for rid in robot_ids}
        self.device_states = {}
        self.event_publishers = {}
        self.auto_publishers = {}
        self.lock = threading.Lock()
        self.frames = {}
        self.models = {rid: RobotViewModel(rid) for rid in robot_ids}
        self.commands = queue.Queue()
        self.stop_commands = queue.Queue()
        self.command_lock = threading.Lock()
        self.generations = {rid: 0 for rid in robot_ids}
        self.jog_publishers = {}
        self.service_clients = {}
        self.pending = []
        for rid in robot_ids:
            for camera_id in camera_configs(configs[rid]):
                self.create_subscription(Image, f'/{rid}/cameras/{camera_id}/image_raw',
                                         lambda m, r=rid, c=camera_id: self.on_frame(r, c, m), qos_profile_sensor_data)
            self.create_subscription(RobotHeartbeat, f'/{rid}/heartbeat', lambda m, r=rid: self.on_heartbeat(r, m), 10)
            self.create_subscription(DiagnosticArray, f'/{rid}/diagnostics', lambda m, r=rid: self.on_diagnostics(r, m), 10)
            self.jog_publishers[rid] = self.create_publisher(JogCommand, f'/{rid}/jog_command', QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT))
            self.event_publishers[rid] = self.create_publisher(TestEvent, f'/{rid}/test_event', 50)
            self.auto_publishers[rid] = self.create_publisher(Time, f'/{rid}/auto_keepalive', QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT))
            self.service_clients[rid] = {'stop': self.create_client(Trigger, f'/{rid}/stop'), 'arm': self.create_client(SetBool, f'/{rid}/arm')}
            self.service_clients[rid].update({
                'start_auto': self.create_client(Trigger, f'/{rid}/start_auto'),
                'stop_auto': self.create_client(Trigger, f'/{rid}/stop_auto'),
                'inject_fault': self.create_client(InjectFault, f'/{rid}/inject_fault')})
        self.create_timer(0.01, self.drain)
        self.create_timer(0.1, self.check_online)
        self.create_timer(1.0, self.log_status)

    def on_frame(self, rid, camera_id, msg):
        if msg.encoding != 'bgr8' or msg.height <= 0 or msg.width <= 0 or len(msg.data) < msg.step * msg.height:
            return
        with self.lock:
            self.frames[(rid, camera_id)] = (time.monotonic(), msg.width, msg.height, msg.step, bytes(msg.data))

    def frame(self, rid, camera_id):
        with self.lock:
            return self.frames.get((rid, camera_id))

    def snapshot(self, rid: str) -> RobotViewModel:
        with self.lock:
            return copy.deepcopy(self.models[rid])

    def on_heartbeat(self, rid, msg):
        with self.lock:
            model = self.models[rid]
            model.last_heartbeat = time.monotonic()
            model.robot_state = msg.state
            model.control_mode = msg.control_mode
            model.uptime = msg.uptime
            model.sequence = msg.sequence
        self.signals.changed.emit(rid)

    def on_diagnostics(self, rid, msg):
        with self.lock:
            self.models[rid].devices = {s.name: {'level': int.from_bytes(s.level, 'little'), 'message': s.message, 'values': {v.key:v.value for v in s.values}} for s in msg.status}
        for status in msg.status:
            key = (rid, status.name)
            state = (int.from_bytes(status.level, 'little'), status.message)
            if self.device_states.get(key) != state:
                self.csv.write('events', device=f'{rid}/{status.name}', level=str(state[0]), event='DEVICE_TRANSITION', detail=state[1])
                self.device_states[key] = state
        self.signals.changed.emit(rid)

    def check_online(self):
        for rid in self.models:
            online = self.snapshot(rid).online
            if online != self.online_states[rid]:
                self.online_states[rid] = online
                self.csv.write('events', device=rid, event='ONLINE' if online else 'OFFLINE')
                self.signals.changed.emit(rid)

    def log_status(self):
        for rid in self.models:
            model = self.snapshot(rid)
            self.csv.write('status', device=rid, event='STATUS', level='OK' if model.online else 'OFFLINE', value=json.dumps(model.devices), detail=model.robot_state)

    def submit(self, rid: str, action: str, token: int = 0, **data):
        with self.command_lock:
            if action in ('stop', 'stop_auto'):
                self.generations[rid] += 1
            data['_generation'] = self.generations[rid]
            data['_submitted_ns'] = time.time_ns()
            target = self.stop_commands if action in ('stop', 'stop_auto') else self.commands
            target.put((rid, action, token, data))

    def drain(self):
        while not self.stop_commands.empty() or not self.commands.empty():
            target = self.stop_commands if not self.stop_commands.empty() else self.commands
            rid, action, token, data = target.get_nowait()
            generation = data.pop('_generation')
            submitted = data.pop('_submitted_ns')
            with self.command_lock:
                canceled = generation != self.generations[rid]
            if action in ('jog', 'auto_keepalive', 'arm', 'start_auto'):
                if canceled or (time.time_ns() - submitted) > 300_000_000:
                    continue
            if action == 'event':
                msg = TestEvent(stamp=self.get_clock().now().to_msg(), event_id=str(uuid.uuid4()), event_type=data['event_type'], description=data.get('description', ''))
                self.csv.write('events', event=msg.event_type, value=msg.event_id, detail=msg.description, timestamp=ros_timestamp(msg.stamp))
                for pub in self.event_publishers.values():
                    pub.publish(msg)
                self.signals.result.emit(rid, action, token, True, msg.event_type + ' recorded and published')
                continue
            if action == 'auto_keepalive':
                self.auto_publishers[rid].publish(Time(sec=submitted // 10**9, nanosec=submitted % 10**9))
                continue
            if action == 'jog':
                msg = JogCommand()
                msg.stamp = Time(sec=submitted // 10**9, nanosec=submitted % 10**9)
                msg.axis = data['axis']
                msg.velocity = data['velocity']
                self.jog_publishers[rid].publish(msg)
                continue
            client = self.service_clients[rid][action]
            if not client.service_is_ready():
                self.signals.result.emit(rid, action, token, False, 'Service unavailable')
                continue
            if action == 'inject_fault':
                req = InjectFault.Request(device=data['device'], fault=data.get('fault', 'fault'), active=data['active'])
            else:
                req = SetBool.Request(data=True) if action == 'arm' else Trigger.Request()
            self.csv.write('events', device=rid, event=action.upper(), detail=json.dumps(data))
            future = client.call_async(req)
            self.pending.append((time.monotonic() + 2.0, rid, action, token, future))
        remaining = []
        for deadline, rid, action, token, future in self.pending:
            if future.done():
                try:
                    result = future.result()
                    self.csv.write('events', device=rid, event=action.upper() + '_RESULT', level='INFO' if result.success else 'ERROR', detail=result.message)
                    self.signals.result.emit(rid, action, token, result.success, result.message)
                except Exception as exc:
                    self.signals.result.emit(rid, action, token, False, str(exc))
            elif time.monotonic() > deadline:
                future.cancel()
                self.signals.result.emit(rid, action, token, False, 'Service response timeout')
            else:
                remaining.append((deadline, rid, action, token, future))
        self.pending = remaining

    def destroy_node(self):
        self.csv.close()
        return super().destroy_node()

class RosWorker:
    def __init__(self, node):
        self.executor = SingleThreadedExecutor()
        self.executor.add_node(node)
        self.thread = threading.Thread(target=self.executor.spin, name='ros-executor', daemon=True)
        self.thread.start()

    def close(self):
        self.executor.shutdown(timeout_sec=2)
        self.thread.join(timeout=2)
