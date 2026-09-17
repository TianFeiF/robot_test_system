"""P1 services and durable test telemetry, independent of GUI and image support."""
import json
import time
from builtin_interfaces.msg import Time
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_srvs.srv import Trigger
from robot_test_msgs.msg import TestEvent
from robot_test_msgs.srv import InjectFault
from robot_test_core.adapters import FaultInjectable
from robot_test_core.logger import ros_timestamp

class TestExtensions:
    def __init__(self, node):
        self.node = node
        self.heartbeat_drop = False
        self.previous = {}
        node.create_subscription(Time, 'auto_keepalive', self.keepalive, QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT))
        node.create_service(Trigger, 'start_auto', self.start_auto)
        node.create_service(Trigger, 'stop_auto', node.on_stop)
        node.create_service(InjectFault, 'inject_fault', self.inject)
        node.create_subscription(TestEvent, 'test_event', self.on_event, 50)
        node.create_timer(1.0, self.log_status)

    def keepalive(self, msg):
        age = (self.node.get_clock().now().nanoseconds - (msg.sec * 10**9 + msg.nanosec)) / 1e9
        controller = self.node.controller
        if controller.auto and controller.armed and 0 <= age < controller.timeout:
            controller.last_commands['__auto__'] = time.monotonic()

    def start_auto(self, request, response):
        try:
            self.node.controller.start_auto()
            response.success = True
            response.message = 'Auto cycle started'
        except Exception as exc:
            response.success = False
            response.message = str(exc)
        return response

    def inject(self, request, response):
        n = self.node
        try:
            if request.device == 'heartbeat':
                self.heartbeat_drop = request.active
                if request.active:
                    n.controller.stop('HEARTBEAT_DROP')
            else:
                adapter = n.controller.all_devices.get(request.device)
                if not isinstance(adapter, FaultInjectable):
                    raise ValueError('Device does not support mock fault injection')
                adapter.inject_fault(request.fault, request.active)
                # A mock fault is synchronous: publish its transition immediately.
                if request.active and (request.device in n.controller.motors or request.device in ('ethercat', 'canopen')):
                    n.controller.stop('INJECTED_MOTION_FAULT')
            n.event('FAULT_INJECTION', f'{request.device} {request.fault} active={request.active}')
            n.diagnostics()
            response.success = True
            response.message = 'Fault active' if request.active else 'Fault cleared; motion remains disarmed'
        except Exception as exc:
            response.success = False
            response.message = str(exc)
        return response

    def on_event(self, msg):
        self.node.csv.write('events', event=msg.event_type, value=msg.event_id, detail=msg.description, timestamp=ros_timestamp(msg.stamp))

    def log_status(self):
        n = self.node
        for name in n.controller.all_devices:
            status = n.controller.status(name)
            n.csv.write('status', device=name, level=status.state.value, event='STATUS', detail=status.detail, value=json.dumps(status.values))
