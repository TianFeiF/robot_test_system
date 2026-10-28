import unittest
from robot_test_core.config import camera_configs
from robot_mock_hardware.factory import create_hardware


class CameraInventoryTests(unittest.TestCase):
    def test_disable_fifth_camera_and_independent_adapters(self):
        config = {'axes': {}, 'hardware': {}, 'cameras': {
            f'camera_{i}': {'enabled': True, 'backend': 'mock'} for i in range(1, 6)}}
        _, devices = create_hardware(config)
        self.assertEqual(len(devices), 5)
        for device in devices.values():
            device.connect()
        devices['camera_5'].inject_fault('offline', True)
        self.assertFalse(devices['camera_5'].is_connected())
        self.assertTrue(all(devices[f'camera_{i}'].is_connected() for i in range(1, 5)))
        config['cameras']['camera_5']['enabled'] = False
        _, devices = create_hardware(config)
        self.assertEqual(set(devices), {f'camera_{i}' for i in range(1, 5)})

    def test_invalid_camera_ids_cannot_replace_motor_devices(self):
        for camera_id in ['drive', 'bad/id', 'heartbeat']:
            with self.subTest(camera_id=camera_id), self.assertRaises(ValueError):
                camera_configs({'axes': {'drive': {}}, 'cameras': {camera_id: {}}})
