"""Mock image source. Image dependencies load only in the capture worker."""
import threading
import time
from datetime import datetime
from robot_test_core.adapters import CameraAdapter, FaultInjectable
from robot_test_core.models import DeviceState, DeviceStatus

class MockCameraAdapter(CameraAdapter, FaultInjectable):
    def __init__(self, config: dict):
        self.lock = threading.RLock()
        self.connected = False
        self.fault = False
        self.error = ''
        self.label = config.get('label', 'MOCK CAMERA')
        self.frames = 0
        self.drops = 0
        self.disconnects = 0
        self.reconnects = 0
        self.ever_connected = False
        self.last_frame = 0.0
        self.fps = 0.0

    def connect(self) -> None:
        with self.lock:
            if not self.connected and self.ever_connected:
                self.reconnects += 1
            self.connected = True
            self.ever_connected = True

    def disconnect(self) -> None:
        with self.lock:
            if self.connected:
                self.disconnects += 1
            self.connected = False
            self.fps = 0.0

    def is_connected(self) -> bool:
        with self.lock:
            return self.connected

    def get_frame(self):
        with self.lock:
            if not self.connected or self.fault:
                self.drops += 1
                return None
            number = self.frames + 1
        try:
            import numpy as np
            import cv2
            frame = np.zeros((240, 400, 3), dtype=np.uint8)
            frame[:] = (25, 35, 45)
            lines = [self.label, f'Frame: {number}', f'FPS: {self.fps:.1f}', datetime.now().isoformat(timespec='seconds')]
            for i, line in enumerate(lines):
                cv2.putText(frame, line, (12, 35 + i * 48), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (100, 230, 180), 1)
            now = time.monotonic()
            with self.lock:
                if not self.connected:
                    self.drops += 1
                    return None
                self.fps = 1 / (now - self.last_frame) if self.last_frame else 0.0
                self.last_frame = now
                self.frames += 1
                self.error = ''
            return frame
        except Exception as exc:
            with self.lock:
                self.error = str(exc)
                self.drops += 1
            return None

    def get_fps(self) -> float:
        with self.lock:
            return self.fps

    def get_frame_count(self) -> int:
        with self.lock:
            return self.frames

    def get_drop_count(self) -> int:
        with self.lock:
            return self.drops

    def get_status(self) -> DeviceStatus:
        with self.lock:
            state = DeviceState.OFFLINE if not self.connected else DeviceState.ERROR if self.error else DeviceState.OK
            return DeviceStatus(state, self.error, dict(frame_count=self.frames, drop_count=self.drops, disconnect_count=self.disconnects,
                                                       reconnect_count=self.reconnects, fps=round(self.fps, 1)))

    def inject_fault(self, fault: str, active: bool) -> None:
        with self.lock:
            self.fault = active
            if active:
                self.disconnect()
            else:
                self.connect()
