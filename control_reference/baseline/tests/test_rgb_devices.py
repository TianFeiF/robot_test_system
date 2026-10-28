import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from robot_mock_hardware.real_adapters.rgb_devices import RGBDeviceRegistry, scan_rgb_devices


class RGBDiscoveryTests(unittest.TestCase):
    def test_duplicate_names_are_claimed_once_and_follow_renumbering(self):
        devices = [dict(device='/dev/video0', key='usb-1:1.0', name='USB Camera:', formats=['MJPG']),
                   dict(device='/dev/video8', key='usb-6:1.0', name='USB Camera:', formats=['MJPG'])]
        registry = RGBDeviceRegistry(lambda: devices)
        one, two = object(), object()
        config = {'name_regex': '^USB Camera:'}
        self.assertNotEqual(registry.acquire(one, config)['key'], registry.acquire(two, config)['key'])
        with self.assertRaises(RuntimeError):
            registry.acquire(object(), config)
        registry.release(one)
        devices[0] = dict(devices[0], device='/dev/video12')
        self.assertEqual(registry.acquire(one, config)['device'], '/dev/video12')
        registry.release(one)
        devices.pop(0)
        with self.assertRaises(RuntimeError):
            registry.acquire(one, config)
        devices.append(dict(device='/dev/video14', key='usb-1:1.0', name='USB Camera:', formats=['MJPG']))
        self.assertEqual(registry.acquire(one, config)['device'], '/dev/video14')

    def test_realSense_depth_ir_and_metadata_are_not_color_candidates(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            sysroot, devroot = root/'sys', root/'dev'
            sysroot.mkdir(); devroot.mkdir()
            formats = {'video2': ['Z16 '], 'video3': [], 'video4': ['GREY', 'UYVY'],
                       'video6': ['YUYV', 'RW16']}
            for name in formats:
                entry = sysroot/name
                entry.mkdir(); (entry/'name').write_text('Intel RealSense Depth Module')
                (devroot/name).touch()
                (entry/'device').symlink_to(root / ('usb-interface-' + name))
            def ioctl(fd, request, data, mutate):
                name = Path(os.readlink(f'/proc/self/fd/{fd}')).name
                index = int.from_bytes(data[:4], 'little')
                if index >= len(formats[name]):
                    raise OSError('No format')
                data[44:48] = formats[name][index].encode()
            with patch('fcntl.ioctl', side_effect=ioctl):
                devices = scan_rgb_devices(sysroot, devroot)
            self.assertEqual([Path(d['device']).name for d in devices], ['video6'])


if __name__ == '__main__':
    unittest.main()
