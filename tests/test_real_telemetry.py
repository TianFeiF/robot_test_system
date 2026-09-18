import time
import unittest
import math

from robot_mock_hardware.factory import create_hardware
from robot_mock_hardware.real_adapters.telemetry import EtherCATMonitor, RM75Monitor, EtherCATReadOnlyMotor
from robot_test_core.controller import RobotController
from robot_test_core.models import DeviceState, DeviceStatus
from robot_mock_hardware.motor import MockMotorAdapter


class TelemetryTests(unittest.TestCase):
    def test_torque_limits_and_watchdog(self):
        class TorqueMotor(MockMotorAdapter):
            def __init__(self):
                super().__init__()
                self.torque_value = 0
            def set_torque(self, value):
                self.torque_value = value
            def stop(self):
                super().stop()
                self.torque_value = 0
        motor = TorqueMotor()
        config = {'axes': {'clamp_left': {'control_mode': 'torque', 'torque_raw_max': 1000}},
                  'test': {'watchdog_timeout_ms': 500}}
        controller = RobotController({'clamp_left': motor}, {}, config)
        controller.arm()
        now = time.monotonic()
        with self.assertRaises(ValueError):
            controller.jog('clamp_left', .1, now)
        for value in (-1, 1001, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                controller.torque('clamp_left', value, now)
        controller.torque('clamp_left', 50, now)
        self.assertEqual(motor.torque_value, 50)
        controller.tick(now + .5)
        self.assertFalse(controller.armed)
        self.assertEqual(motor.torque_value, 0)

    def test_encoder_units_and_not_homed(self):
        bus = EtherCATMonitor({'backend': 'ethercat_monitor'})
        bus._status = DeviceStatus(DeviceState.WARN, 'Read only', {
            'slave_2_statusword': 592, 'slave_2_position_raw': 65536 * 51,
            'slave_2_velocity_raw': 65536 * 51})
        motor = EtherCATReadOnlyMotor(bus, {'slave_position': 2, 'encoder_counts_per_rev': 65536,
                                          'gear_ratio': 51, 'position_unit': 'rad'})
        self.assertAlmostEqual(motor.get_position(), 2 * math.pi)
        self.assertFalse(motor.get_status().values['homed'])
        bus._status.values.update(slave_3_statusword=592, slave_3_position_raw=65536 * 101,
                                  slave_3_velocity_raw=65536 * 101)
        z = EtherCATReadOnlyMotor(bus, {'slave_position': 3, 'encoder_counts_per_rev': 65536,
                                      'gear_ratio': 101, 'lead_m': .02})
        self.assertAlmostEqual(z.get_position(), .02)

    def test_ethercat_reads_only_and_detects_fault(self):
        bus = EtherCATMonitor({'backend': 'ethercat_monitor', 'expected_slaves': 1})
        commands = []
        def command(args):
            commands.append(args)
            if args[1] == 'slaves':
                return '0  0:0 PREOP + Servo\n'
            return {'0x6041': '0x0250 592', '0x6064': '0xfffffffe -2',
                    '0x606c': '0x0000 0', '0x603f': '0x0001 1',
                    '0x6077': '0x0000 0', '0x6061': '0x09 9'}[args[-2]]
        bus.command = command
        status = bus.poll()
        self.assertEqual(status.state, DeviceState.ERROR)
        self.assertEqual(status.values['slave_0_position_raw'], -2)
        self.assertTrue(all(c[1] in ('slaves', 'upload') for c in commands))

    def test_missing_slaves_and_stale_data(self):
        bus = EtherCATMonitor({'backend': 'ethercat_monitor', 'stale_sec': 1})
        bus.command = lambda args: ''
        self.assertEqual(bus.poll().state, DeviceState.ERROR)
        bus._status = bus.poll()
        bus._sample_time = time.monotonic() - 2
        self.assertEqual(bus.get_status().state, DeviceState.OFFLINE)

    def test_rm_errors_are_not_reported_healthy(self):
        rm = RM75Monitor({'backend': 'rm75_monitor', 'executable': 'query', 'host': 'localhost'})
        rm.command = lambda args: 'SDK info\n{"joint_degrees":[1,2,3,4,5,6,7],"arm_errors":[4116]}\n'
        self.assertEqual(rm.poll().state, DeviceState.ERROR)
        rm.command = lambda args: '{"joint_degrees":[1,2,3,4,5,6,7],"arm_errors":[0]}\n'
        self.assertEqual(rm.poll().state, DeviceState.OK)

    def test_mapped_axes_share_bus_and_reject_motion(self):
        config = {'robot': {'monitor_only': True},
                  'axes': {name: {'bus': 'ethercat', 'slave_position': pos}
                           for pos, name in enumerate(['clamp_left', 'clamp_right', 'drive', 'z_axis'])},
                  'hardware': {'ethercat': {'enabled': True, 'backend': 'ethercat_monitor'}},
                  'test': {'watchdog_timeout_ms': 500}}
        motors, devices = create_hardware(config)
        bus = devices['ethercat']
        bus.connect = lambda: None
        self.assertTrue(all(m.bus is bus for m in motors.values()))
        self.assertEqual(motors['z_axis'].position, 3)
        controller = RobotController(motors, devices, config)
        with self.assertRaisesRegex(RuntimeError, 'Monitor-only'):
            controller.arm()
        controller.stop()
        self.assertEqual(set(controller.stop_errors), set(motors))
        self.assertFalse(controller.armed)


if __name__ == '__main__':
    unittest.main()
