"""All configured cameras visible together on the 1920x1080 dashboard."""
import time
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QLabel, QScrollArea, QSizePolicy
from robot_test_core.config import camera_configs


class CameraPanel(QWidget):
    def __init__(self, bridge, configs):
        super().__init__()
        self.bridge = bridge
        self.previews = {}
        self.status_labels = {}
        self.frame_times = {}
        self.setFixedHeight(210)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        column = 0
        for rid, config in configs.items():
            cameras = camera_configs(config)
            for camera_id, settings in cameras.items():
                tile = QWidget()
                layout = QVBoxLayout(tile)
                layout.setContentsMargins(3, 3, 3, 3)
                layout.setSpacing(3)
                title = QLabel(f'{config["robot"]["display_name"]} / {camera_id}')
                title.setToolTip(settings.get('label', camera_id))
                layout.addWidget(title)
                preview = QLabel('NO RECENT FRAME')
                preview.setAlignment(Qt.AlignCenter)
                preview.setMinimumWidth(0)
                preview.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
                preview.setWordWrap(True)
                preview.setFixedHeight(132)
                layout.addWidget(preview)
                status = QLabel('UNKNOWN')
                status.setWordWrap(True)
                layout.addWidget(status)
                key = (rid, camera_id)
                self.previews[key] = preview
                self.status_labels[key] = status
                grid.addWidget(tile, 0, column)
                grid.setColumnStretch(column, 1)
                column += 1

    def refresh(self, rid, model):
        for key, preview in self.previews.items():
            if key[0] != rid:
                continue
            camera_id = key[1]
            frame = self.bridge.frame(rid, camera_id)
            device = model.devices.get(camera_id, {})
            values = device.get('values', {})
            healthy = model.online and device.get('level') == 0
            fresh = bool(frame and time.monotonic() - frame[0] < 2.0)
            label = self.status_labels[key]
            state = 'OFFLINE' if not model.online else device.get('message', 'UNKNOWN')
            if healthy and not fresh:
                state = 'NO RECENT FRAME'
            label.setText(f'{state} | FPS {values.get("fps", "—")}\nFrames {values.get("frame_count", "—")}')
            label.setStyleSheet('color:' + ('green' if healthy and fresh else 'red' if device or not model.online else 'gray'))
            if healthy and fresh:
                if self.frame_times.get(key) != frame[0]:
                    received, width, height, step, data = frame
                    image = QImage(data, width, height, step, QImage.Format_BGR888).copy()
                    preview.setPixmap(QPixmap.fromImage(image).scaled(max(1, preview.width()), 132, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                    self.frame_times[key] = received
            else:
                preview.clear()
                preview.setText(f'{camera_id}: OFFLINE / NO RECENT FRAME')
                self.frame_times.pop(key, None)
