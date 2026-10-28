import unittest
from types import SimpleNamespace
from robot_test_core.controller import RobotController
from robot_test_core.models import DeviceState, RobotState
from robot_mock_hardware.motor import MockMotorAdapter
from robot_test_agent.node import RobotTestAgent
from robot_test_ground.app import GroundWindow


class ReadOnlyMotor(MockMotorAdapter):
    def __init__(self):
        super().__init__()
        self.commands = []
    def stop(self):
        self.commands.append('stop')
        raise RuntimeError('read only')
    def disable(self):
        self.commands.append('disable')
        raise RuntimeError('read only')
    def disconnect(self):
        self.connected = False


class MonitorStopTests(unittest.TestCase):
    def make(self, monitor=True):
        motor = ReadOnlyMotor()
        events = []
        controller = RobotController({'drive': motor}, {}, {
            'robot': {'monitor_only': monitor}, 'test': {'watchdog_timeout_ms': 500}},
            lambda *args: events.append(args))
        node = SimpleNamespace(controller=controller, get_clock=lambda: SimpleNamespace(
            now=lambda: SimpleNamespace(nanoseconds=123)))
        return controller, motor, events, node

    def test_stop_and_disarm_rejected_without_fault_or_hardware_calls(self):
        c, m, events, node = self.make()
        for handler, request in ((RobotTestAgent.on_stop, None),
                                 (RobotTestAgent.on_arm, SimpleNamespace(data=False))):
            reply = handler(node, request, SimpleNamespace())
            self.assertFalse(reply.success)
            self.assertIn('no hardware command sent', reply.message)
            self.assertEqual(c.status('drive').state, DeviceState.OK)
            self.assertEqual(c.state, RobotState.READY)
            self.assertEqual(c.exceptions, {})
            self.assertEqual(c.stop_errors, {})
        self.assertEqual(m.commands, [])
        self.assertTrue(all(e[0]=='STOP_UNSUPPORTED' for e in events))
        with self.assertRaisesRegex(RuntimeError, 'Monitor-only'):
            c.arm()
        c.close()
        self.assertFalse(m.connected)
        self.assertEqual(m.commands, [])
        self.assertEqual(events[-1][0], 'SHUTDOWN')

    def test_rejection_preserves_existing_faults(self):
        c, _, _, _ = self.make()
        c.exceptions['drive'] = 'existing read failure'
        c.state = RobotState.FAULT
        self.assertFalse(c.stop())
        self.assertEqual(c.status('drive').detail, 'existing read failure')
        self.assertEqual(c.state, RobotState.FAULT)

    def test_control_stop_failure_still_calls_both_and_returns_failure(self):
        c, m, events, node = self.make(False)
        response = RobotTestAgent.on_arm(node, SimpleNamespace(data=False), SimpleNamespace())
        self.assertFalse(response.success)
        self.assertEqual(m.commands, ['stop', 'disable'])
        self.assertEqual(c.state, RobotState.FAULT)
        c.close()
        self.assertEqual(m.commands, ['stop', 'disable'] * 2)
        self.assertTrue(any(e[0]=='STOP_ERROR' for e in events))

    def test_monitor_window_exit_skips_monitor_but_explicit_stop_does_not(self):
        calls = []
        window = SimpleNamespace(token=0, auto_robots=set(), release_jog=lambda: None,
            configs={'monitor': {'robot': {'monitor_only': True}}, 'control': {}},
            bridge=SimpleNamespace(submit=lambda *args: calls.append(args)))
        GroundWindow._stop_all(window, include_monitors=False)
        self.assertEqual(calls, [('control', 'stop')])
        calls.clear()
        GroundWindow._stop_all(window, include_monitors=True)
        self.assertEqual(calls, [('monitor', 'stop'), ('control', 'stop')])
