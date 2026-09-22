import unittest
import queue
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

from robot_test_agent.node import RobotTestAgent
from robot_mock_hardware.real_adapters.ethercat import EtherCATMotor
from robot_test_ground.bridge import GroundBridge


class ControlRegressionTests(unittest.TestCase):
    def test_clock_mismatch_blocks_arm_but_not_stop(self):
        for skew in (0.95, 33108.0, -0.95):
            for action in ('arm', 'stop'):
                client = Mock()
                client.service_is_ready.return_value = False
                node = SimpleNamespace(
                    commands=queue.Queue(), stop_commands=queue.Queue(), pending=[],
                    command_lock=threading.Lock(), generations={'robot_a': 0},
                    snapshot=lambda _: SimpleNamespace(online=True, heartbeat_age_sec=skew),
                    signals=SimpleNamespace(result=Mock()),
                    service_clients={'robot_a': {'stop': client}})
                node.commands.put(('robot_a', action, 1,
                                   {'_generation': 0, '_submitted_ns': time.time_ns()}))
                GroundBridge.drain(node)
                message = node.signals.result.emit.call_args.args[-1]
                if action == 'arm':
                    self.assertIn('时钟', message)
                    client.service_is_ready.assert_not_called()
                else:
                    client.service_is_ready.assert_called_once()
                    self.assertEqual(message, 'Service unavailable')

    def test_command_age_epoch_and_rejection_diagnostic(self):
        events = []
        node = SimpleNamespace(
            get_clock=lambda: SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=2_000_000_000)),
            command_epoch_ns=1_000_000_000,
            controller=SimpleNamespace(timeout=0.5), event=lambda *args: events.append(args))
        valid = lambda stamp: RobotTestAgent.command_time_valid(node, stamp)
        self.assertTrue(valid(1_900_000_000))
        self.assertTrue(valid(2_000_000_000))
        for stamp in (2_000_000_001, 1_500_000_000, 999_999_999):
            self.assertFalse(valid(stamp))
        self.assertEqual(len(events), 1)  # Repeated rejected packets do not flood logs.
        self.assertEqual(events[0][0], 'COMMAND_TIME_REJECTED')
        node.command_epoch_ns = 1_950_000_000
        self.assertFalse(valid(1_900_000_000))  # Recent but before STOP/ARM.

    def test_signed_clamp_torque_bounds(self):
        bus = SimpleNamespace(command=Mock())
        motor = EtherCATMotor(bus, {'slave_position': 0, 'control_mode': 'torque',
                                   'torque_raw_min': -1000, 'torque_raw_max': 1000})
        for value in (-1000, -50, 0, 50, 1000):
            motor.set_torque(value)
            bus.command.assert_called_with(0, value)
        bus.command.reset_mock()
        for value in (-1001, 1001, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                motor.set_torque(value)
        bus.command.assert_not_called()

    def test_legacy_unsigned_profile_stays_unsigned(self):
        motor = EtherCATMotor(SimpleNamespace(command=Mock()), {
            'slave_position': 0, 'control_mode': 'torque', 'torque_raw_max': 1000})
        with self.assertRaises(ValueError):
            motor.set_torque(-1)
