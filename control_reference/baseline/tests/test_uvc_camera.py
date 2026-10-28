import threading
import time
import unittest
import numpy as np
from robot_mock_hardware.real_adapters.uvc_camera import UVCCameraAdapter

class Capture:
    def __init__(self, opened=True, read_ok=True):
        self.opened = opened
        self.read_ok = read_ok
        self.released = False
    def isOpened(self):
        return self.opened
    def read(self):
        return self.read_ok, np.zeros((12, 16, 3), dtype=np.uint8) if self.read_ok else None
    def release(self):
        self.released = True

class UVCTests(unittest.TestCase):
    def test_reconnect_and_counters(self):
        caps=[]
        def factory(device):
            cap=Capture();caps.append(cap);return cap
        cam=UVCCameraAdapter({},factory)
        cam.connect();self.assertEqual(len(caps),0)
        self.assertIsNotNone(cam.get_frame())
        caps[0].read_ok=False
        self.assertIsNone(cam.get_frame())
        self.assertFalse(cam.is_connected())
        self.assertEqual(cam.get_drop_count(),1)
        cam._next_retry=0
        self.assertIsNotNone(cam.get_frame())
        self.assertEqual(cam.get_status().values['reconnect_count'],1)
        cam.disconnect();self.assertTrue(caps[-1].released)
        self.assertIsNone(cam.get_frame())

    def test_missing_device_does_not_throw(self):
        cam=UVCCameraAdapter({},lambda _:Capture(False))
        cam.connect()
        self.assertIsNone(cam.get_frame())
        self.assertEqual(cam.get_status().state.value,'OFFLINE')
        cam.disconnect()

    def test_blocked_camera_does_not_block_diagnostics_or_disconnect(self):
        entered=threading.Event();release=threading.Event()
        class Slow(Capture):
            def read(self):
                entered.set();release.wait(2);return super().read()
        cap=Slow();cam=UVCCameraAdapter({},lambda _:cap)
        cam.connect();worker=threading.Thread(target=cam.get_frame);worker.start()
        try:
            self.assertTrue(entered.wait(1))
            start=time.monotonic();cam.get_status();cam.disconnect()
            self.assertLess(time.monotonic()-start,.1)
        finally:
            release.set();worker.join(2)
        self.assertTrue(cap.released)
        self.assertFalse(cam.is_connected())

if __name__=='__main__':
    unittest.main()
