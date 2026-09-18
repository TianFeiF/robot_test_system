"""UVC/OpenCV adapter. All potentially blocking camera I/O stays in capture thread."""
import threading
import time
from robot_test_core.adapters import CameraAdapter
from robot_test_core.models import DeviceState, DeviceStatus


class UVCCameraAdapter(CameraAdapter):
    def __init__(self, config: dict, capture_factory=None):
        self.config = config
        self.device = config.get('device', '/dev/video0')
        self.retry_sec = max(0.2, float(config.get('reconnect_sec', 2.0)))
        self._factory = capture_factory
        self._state_lock = threading.Lock()
        self._io_lock = threading.Lock()
        self._capture = None
        self._requested = False
        self._connected = False
        self._ever_connected = False
        self._next_retry = 0.0
        self._last_frame = 0.0
        self._fps = 0.0
        self._frames = self._drops = self._disconnects = self._reconnects = 0
        self._width = self._height = 0
        self._error = 'Not connected'
        self._rgb_device = None
        self._registry = None
        if config.get('rgb_selector'):
            from .rgb_devices import REGISTRY
            self._registry = REGISTRY

    def connect(self) -> None:
        # RobotController calls this on its own thread: defer hardware open to get_frame.
        with self._state_lock:
            self._requested = True
            self._error = 'Waiting for first frame'

    def _mark_offline(self, reason: str) -> None:
        with self._state_lock:
            if self._connected:
                self._disconnects += 1
            self._connected = False
            self._fps = 0.0
            self._error = reason

    def _release(self) -> None:
        capture, self._capture = self._capture, None
        try:
            if capture is not None:
                capture.release()
        finally:
            if self._registry:
                self._registry.release(self)

    def disconnect(self) -> None:
        with self._state_lock:
            self._requested = False
        self._mark_offline('Disconnected')
        # Never wait for a wedged USB driver in the control/shutdown thread.
        if self._io_lock.acquire(blocking=False):
            try:
                self._release()
            finally:
                self._io_lock.release()

    def _open(self):
        if self._factory:
            return self._factory(self.device)
        import cv2
        if self._registry:
            selected = self._registry.acquire(self, self.config['rgb_selector'])
            with self._state_lock:
                self.device = selected['device']
                self._rgb_device = selected
        cap = cv2.VideoCapture(self.device, cv2.CAP_V4L2)
        if cap.isOpened():
            if self._rgb_device:
                formats = self._rgb_device['formats']
                preferred_format = 'MJPG' if 'MJPG' in formats else 'YUYV' if 'YUYV' in formats else None
                if preferred_format:
                    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*preferred_format))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(self.config.get('width', 640)))
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(self.config.get('height', 480)))
            cap.set(cv2.CAP_PROP_FPS, float(self.config.get('fps', 5)))
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def get_frame(self):
        with self._io_lock:
            with self._state_lock:
                requested = self._requested
            if not requested:
                self._release()
                return None
            now = time.monotonic()
            if now < self._next_retry:
                return None
            try:
                if self._capture is None:
                    self._capture = self._open()
                if not self._capture.isOpened():
                    raise RuntimeError(f'Cannot open {self.device}; check privacy switch, permissions or another camera app')
                ok, frame = self._capture.read()
                if not ok or frame is None:
                    raise RuntimeError(f'No frame from {self.device}')
                if frame.ndim != 3 or frame.shape[2] != 3:
                    raise RuntimeError(f'{self.device} did not produce a BGR color frame')
                now = time.monotonic()
                with self._state_lock:
                    requested = self._requested
                    if requested:
                        if not self._connected and self._ever_connected:
                            self._reconnects += 1
                        self._fps = 1 / (now - self._last_frame) if self._connected and self._last_frame else 0.0
                        self._connected = self._ever_connected = True
                        self._frames += 1
                        self._last_frame = now
                        self._height, self._width = frame.shape[:2]
                        self._error = ''
                if not requested:
                    self._release()
                    return None
                return frame
            except Exception as exc:
                self._mark_offline(str(exc))
                with self._state_lock:
                    self._drops += 1
                self._release()
                self._next_retry = time.monotonic() + self.retry_sec
                return None

    def is_connected(self) -> bool:
        with self._state_lock:
            return self._connected and time.monotonic() - self._last_frame < 2.0

    def get_fps(self) -> float:
        with self._state_lock:
            return self._fps if time.monotonic() - self._last_frame < 2.0 else 0.0

    def get_frame_count(self) -> int:
        with self._state_lock:
            return self._frames

    def get_drop_count(self) -> int:
        with self._state_lock:
            return self._drops

    def get_status(self) -> DeviceStatus:
        with self._state_lock:
            fresh = self._connected and time.monotonic() - self._last_frame < 2.0
            return DeviceStatus(DeviceState.OK if fresh else DeviceState.OFFLINE,
                                self._error or ('' if fresh else 'No recent frame'),
                                dict(frame_count=self._frames, drop_count=self._drops,
                                     disconnect_count=self._disconnects, reconnect_count=self._reconnects,
                                     fps=round(self._fps, 1) if fresh else 0.0, device=str(self.device),
                                     usb_interface=self._rgb_device['key'] if self._rgb_device else '',
                                     width=self._width, height=self._height, backend='uvc'))
