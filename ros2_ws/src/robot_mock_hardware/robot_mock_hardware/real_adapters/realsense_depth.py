"""D456 depth visualization via the existing native librealsense installation."""
import os
import selectors
import struct
import subprocess
import time

from .uvc_camera import UVCCameraAdapter


class DepthCapture:
    def __init__(self, executable, serial):
        self.process = subprocess.Popen([executable, serial], stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, bufsize=0)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)

    def isOpened(self):
        return self.process.poll() is None

    def _read(self, count, deadline):
        data = bytearray()
        while len(data) < count:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not self.selector.select(remaining):
                raise TimeoutError('RealSense depth capture timed out')
            part = os.read(self.process.stdout.fileno(), count - len(data))
            if not part:
                raise RuntimeError('RealSense capture ended; check serial, USB or device ownership')
            data.extend(part)
        return data

    def read(self):
        import numpy as np
        deadline = time.monotonic() + 5
        width, height, count = struct.unpack('<III', self._read(12, deadline))
        if not 0 < width <= 1920 or not 0 < height <= 1080 or count != width * height * 3:
            raise ValueError('Invalid depth preview frame')
        rgb = np.frombuffer(self._read(count, deadline), dtype=np.uint8).reshape(height, width, 3)
        return True, rgb[:, :, ::-1].copy()

    def release(self):
        self.selector.close()
        self.process.terminate()
        try:
            self.process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=1)
        self.process.stdout.close()


class RealSenseDepthAdapter(UVCCameraAdapter):
    def _open(self):
        return DepthCapture(self.config['executable'], self.config['serial'])

    def get_status(self):
        status = super().get_status()
        status.values.update(backend='realsense_depth', serial=self.config['serial'],
                             preview='depth pseudocolor; not metric RGB pixels')
        status.values.pop('device', None)
        return status
