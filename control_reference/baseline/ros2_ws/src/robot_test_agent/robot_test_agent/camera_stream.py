"""Bounded latest-frame mailbox. Slow capture must never block motion callbacks."""
import logging
import threading
import time
from sensor_msgs.msg import Image, CompressedImage
from rclpy.qos import qos_profile_sensor_data
from robot_test_core.adapters import CameraAdapter

class CameraStream:
    def __init__(self, node, adapter: CameraAdapter, fps: float, camera_id: str, transport: str = 'raw'):
        self.node = node
        self.camera_id = camera_id
        self.adapter = adapter
        if transport not in ('raw', 'compressed'):
            raise ValueError('Camera transport must be raw or compressed')
        self.compressed = transport == 'compressed'
        self.period = 1.0 / max(1.0, min(float(fps), 10.0))
        self.lock = threading.Lock()
        self.latest = None
        self.quit = threading.Event()
        topic = f'cameras/{camera_id}/image_raw' + ('/compressed' if self.compressed else '')
        self.publisher = node.create_publisher(CompressedImage if self.compressed else Image, topic, qos_profile_sensor_data)
        self.timer = node.create_timer(self.period, self.publish)
        self.thread = threading.Thread(target=self.capture, name=f'capture-{camera_id}', daemon=True)
        self.thread.start()

    def capture(self):
        previous_error = ''
        while not self.quit.is_set():
            began = time.monotonic()
            try:
                frame = self.adapter.get_frame()
                if frame is not None:
                    if self.compressed:
                        import cv2
                        ok, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                        if not ok:
                            raise RuntimeError('JPEG encoding failed')
                        msg = CompressedImage(format='bgr8; jpeg compressed bgr8', data=encoded.tobytes())
                    else:
                        msg = Image()
                        msg.height, msg.width = frame.shape[:2]
                        msg.encoding = 'bgr8'
                        msg.step = msg.width * 3
                        msg.data = frame.tobytes()
                    msg.header.frame_id = f'{self.node.robot_id}/{self.camera_id}'
                    msg.header.stamp.sec, msg.header.stamp.nanosec = divmod(time.time_ns(), 10**9)
                    with self.lock:
                        self.latest = msg
                previous_error = ''
            except Exception as exc:
                if str(exc) != previous_error:
                    self.node.event('CAMERA_ERROR', f'{self.camera_id}: {exc}')
                    previous_error = str(exc)
            self.quit.wait(max(0.001, self.period - (time.monotonic() - began)))

    def publish(self):
        with self.lock:
            frame, self.latest = self.latest, None
        if frame is not None:
            self.publisher.publish(frame)

    def close(self):
        self.quit.set()
        self.thread.join(timeout=1)
