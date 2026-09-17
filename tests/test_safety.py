import time
import unittest
from robot_mock_hardware.motor import MockMotorAdapter
from robot_test_core.controller import RobotController

class SafetyTests(unittest.TestCase):
    def make(self):
        motor = MockMotorAdapter()
        events = []
        controller = RobotController({'drive': motor}, {}, {'test':{'watchdog_timeout_ms':500}, 'axes':{'drive':{'max_velocity':0.2}}}, lambda *e: events.append(e))
        return controller, motor, events

    def test_watchdog_boundary_and_latch(self):
        c,m,events = self.make()
        c.arm()
        now = time.monotonic()
        c.last_tick = now
        c.jog('drive', 0.1, now)
        c.tick(now + 0.499)
        self.assertGreater(m.get_position(), 0)
        self.assertGreater(m.get_velocity(), 0)
        c.tick(now + 0.500)
        self.assertEqual(m.get_velocity(), 0)
        self.assertFalse(c.armed)
        with self.assertRaises(RuntimeError):
            c.jog('drive', 0.1, now + 0.6)
        self.assertTrue(any(e[0]=='WATCHDOG' for e in events))

    def test_stop_fault_invalid_velocity(self):
        c,m,_ = self.make()
        c.arm()
        for speed in [float('nan'), float('inf'), 0.21]:
            with self.assertRaises(ValueError):
                c.jog('drive', speed, time.monotonic())
        c.jog('drive', 0.1, time.monotonic())
        c.stop()
        self.assertEqual(m.get_velocity(), 0)
        c.arm()
        m.inject_fault('fault', True)
        c.tick(time.monotonic())
        self.assertFalse(c.armed)
        with self.assertRaises(RuntimeError):
            c.arm()
        m.inject_fault('fault', False)
        self.assertFalse(c.armed)
        c.arm()
        self.assertTrue(c.armed)

class ErrorIsolationTests(unittest.TestCase):
    def test_stop_failure_attempts_disable_and_other_axes(self):
        class BrokenStop(MockMotorAdapter):
            def stop(self):
                raise RuntimeError('stop failure')
            def disable(self):
                self.enabled = False
                self.velocity = 0
        failed, good = BrokenStop(), MockMotorAdapter()
        c = RobotController({'bad':failed, 'good':good}, {}, {'test':{'watchdog_timeout_ms':500}}, lambda *_: None)
        failed.velocity = good.velocity = 0.1
        c.stop()
        self.assertEqual(good.velocity, 0)
        self.assertEqual(failed.velocity, 0)
        self.assertIn('bad', c.stop_errors)
        self.assertFalse(c.armed)

    def test_optional_device_exception_does_not_kill_motor_control(self):
        from robot_mock_hardware.devices import MockDeviceAdapter
        class BadCamera(MockDeviceAdapter):
            def update(self, dt):
                raise RuntimeError('USB disconnected')
        motor = MockMotorAdapter()
        c = RobotController({'drive':motor}, {'camera':BadCamera('camera')}, {'test':{'watchdog_timeout_ms':500}, 'axes':{'drive':{'max_velocity':0.2}}})
        c.arm()
        t = time.monotonic()
        c.jog('drive', 0.1, t)
        c.tick(t + 0.1)
        self.assertTrue(c.armed)
        self.assertGreater(motor.position, 0)
        self.assertEqual(c.status('camera').state.value, 'ERROR')
        c.tick(t + 0.5)
        self.assertEqual(motor.velocity, 0)

    def test_per_axis_watchdog(self):
        a, b = MockMotorAdapter(), MockMotorAdapter()
        cfg = {'test':{'watchdog_timeout_ms':500}, 'axes':{n:{'max_velocity':0.2} for n in ['a','b']}}
        c = RobotController({'a':a,'b':b}, {}, cfg)
        c.arm()
        t = time.monotonic()
        c.jog('a', 0.1, t)
        c.jog('b', 0.1, t + 0.4)
        c.tick(t + 0.49)
        c.tick(t + 0.50)
        self.assertEqual(a.velocity, 0)
        self.assertEqual(b.velocity, 0)

if __name__ == '__main__':
    unittest.main()
