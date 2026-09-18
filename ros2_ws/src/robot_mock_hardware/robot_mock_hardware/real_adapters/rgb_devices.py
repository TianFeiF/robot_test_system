"""Discover color-capable V4L2 nodes; never trust a composite device's index0."""
import fcntl
import os
from pathlib import Path
import re
import struct
import threading

VIDIOC_ENUM_FMT = 0xC0405602
COLOR_FORMATS = {'MJPG', 'JPEG', 'YUYV', 'RGB3', 'BGR3'}


def scan_rgb_devices(sys_root=Path('/sys/class/video4linux'), dev_root=Path('/dev')):
    devices = []
    for entry in sorted(sys_root.glob('video*')):
        node = dev_root / entry.name
        fd = None
        try:
            fd = os.open(node, os.O_RDONLY | os.O_NONBLOCK)
            formats = []
            for index in range(64):
                data = bytearray(64)
                struct.pack_into('II', data, 0, index, 1)  # VIDEO_CAPTURE, not metadata
                try:
                    fcntl.ioctl(fd, VIDIOC_ENUM_FMT, data, True)
                except OSError:
                    break
                formats.append(bytes(data[44:48]).decode('ascii', errors='replace'))
            if not COLOR_FORMATS.intersection(formats):
                continue
            # USB interface path survives /dev/videoN renumbering.
            key = str((entry / 'device').resolve())
            devices.append({'device': str(node), 'key': key,
                            'name': (entry / 'name').read_text().strip(), 'formats': formats})
        except (OSError, ValueError):
            continue
        finally:
            if fd is not None:
                os.close(fd)
    return sorted(devices, key=lambda item: (item['key'], item['device']))


class RGBDeviceRegistry:
    def __init__(self, scanner=scan_rgb_devices):
        self.scanner = scanner
        self.lock = threading.Lock()
        self.claims = {}
        self.previous = {}

    def acquire(self, owner, config):
        candidates = self.scanner()
        name_pattern = config.get('name_regex', '.*')
        candidates = [d for d in candidates if re.search(name_pattern, d['name'])]
        preferred = os.path.realpath(config.get('preferred_path', '/nonexistent'))
        with self.lock:
            used = {key for user, key in self.claims.items() if user is not owner}
            candidates = [d for d in candidates if d['key'] not in used]
            candidates.sort(key=lambda d: (d['key'] != self.previous.get(owner),
                                           os.path.realpath(d['device']) != preferred, d['key']))
            if not candidates:
                raise RuntimeError(f'No unclaimed RGB camera matching {name_pattern}; retrying discovery')
            device = candidates[0]
            self.claims[owner] = self.previous[owner] = device['key']
            return device

    def release(self, owner):
        with self.lock:
            self.claims.pop(owner, None)


REGISTRY = RGBDeviceRegistry()
