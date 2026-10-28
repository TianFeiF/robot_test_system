import unittest
import time
from pathlib import Path
from unittest.mock import Mock

import yaml

from robot_mock_hardware.motor import MockMotorAdapter
from robot_test_core.auto_cycle import AutoCycle
from robot_test_core.controller import RobotController


class AutoCycleAllAxesTests(unittest.TestCase):
    class TorqueMotor(MockMotorAdapter):
        def set_torque(self, value):
            self.torque = value

    def make_motor(self):
        motor = MockMotorAdapter()
        motor.connect()
        motor.enable()
        return motor

    def test_site_auto_stops_previous_drive_jog_and_cycles_other_axes(self):
        root = Path(__file__).resolve().parents[1]
        for robot in ('robot_a', 'robot_b'):
            with self.subTest(robot=robot):
                config = yaml.safe_load((root / 'config' / f'{robot}_control' / f'{robot}.yaml').read_text())
                motors = {name: self.TorqueMotor() if axis.get('control_mode') == 'torque'
                          else MockMotorAdapter() for name, axis in config['axes'].items()}
                controller = RobotController(motors, {}, config)
                controller.arm()
                controller.jog('drive', .05, time.monotonic())
                self.assertGreater(motors['drive'].velocity, 0)
                motors['drive'].jog = Mock(wraps=motors['drive'].jog)
                controller.start_auto()
                self.assertNotIn('drive', controller.auto.axes)
                excluded = {'drive', 'z_axis'} if robot == 'robot_a' else {'drive'}
                self.assertEqual(set(controller.auto.axes), set(motors) - excluded)
                motors['z_axis'].jog = Mock(wraps=motors['z_axis'].jog)
                start = controller.last_tick = time.monotonic()
                for step in range(121):
                    now = start + step * .1
                    controller.last_commands['__auto__'] = now
                    controller.tick(now)
                    self.assertTrue(controller.armed)
                    self.assertEqual(motors['drive'].velocity, 0)
                motors['drive'].jog.assert_not_called()
                if robot == 'robot_a':
                    motors['z_axis'].jog.assert_not_called()
                    self.assertEqual(motors['z_axis'].velocity, 0)
                else:
                    self.assertNotEqual(motors['z_axis'].velocity, 0)
                self.assertEqual(abs(motors['clamp_left'].torque), 400)
                if robot == 'robot_b':
                    self.assertEqual(abs(motors['support_left'].torque), 800)
                controller.stop()
                controller.arm()
                controller.jog('drive', .05, time.monotonic())
                self.assertEqual(motors['drive'].velocity, .05)
                controller.close()

    def test_torque_axes_reverse_every_half_period(self):
        motor = self.TorqueMotor()
        motor.connect()
        motor.enable()
        cycle = AutoCycle({'clamp_left': motor}, {'enabled': True,
            'axes': {'clamp_left': {'torque_raw': 600, 'period_sec': 10}}},
            {'clamp_left': {'control_mode': 'torque', 'torque_raw_min': -1000,
                            'torque_raw_max': 1000}})
        cycle.tick(0, .01)
        self.assertEqual(motor.torque, 600)
        cycle.tick(4.99, .01)
        self.assertEqual(motor.torque, 600)
        cycle.tick(5.01, .01)
        self.assertEqual(motor.torque, -600)

    def test_drive_reverses_at_five_seconds_and_z_uses_zero_to_20mm_window(self):
        drive, z = self.make_motor(), self.make_motor()
        axes = {'drive': {'max_velocity': 1}, 'z_axis': {
            'max_velocity': .01, 'position_min': -.02, 'position_max': .5}}
        cycle = AutoCycle({'drive': drive, 'z_axis': z}, {'enabled': True, 'axes': {
            'drive': {'velocity': .0872664626, 'reverse_period_sec': 5},
            'z_axis': {'position_min_m': 0.0, 'position_max_m': .02, 'velocity': .01}}}, axes)
        cycle.tick(0, .01)
        self.assertGreater(drive.velocity, 0)
        cycle.tick(5.01, .01)
        self.assertLess(drive.velocity, 0)
        z.position = .02
        cycle.tick(6, .01)
        self.assertLess(z.velocity, 0)


if __name__ == '__main__':
    unittest.main()
