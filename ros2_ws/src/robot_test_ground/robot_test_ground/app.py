import os
# cv2 may modify Qt plugin paths; Qt plugins must come from PySide6.
os.environ.pop('QT_QPA_PLATFORM_PLUGIN_PATH', None)
import sys
import time
from pathlib import Path
import yaml
import rclpy
from ament_index_python.packages import get_package_share_directory
from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QTableWidget, QTableWidgetItem, QPlainTextEdit, QHeaderView, QAbstractItemView
from PySide6.QtGui import QColor, QImage, QPixmap, QShortcut, QKeySequence, QFont
from .telemetry import telemetry_cells
from .camera_panel import CameraPanel
from .test_panel import TestPanel
from .bridge import GroundBridge, RosWorker

class GroundWindow(QMainWindow):
    def __init__(self, bridge, configs):
        super().__init__()
        self.bridge = bridge
        self.configs = configs
        self.active_jog = None
        self.auto_robots = set()
        self.token = 0
        hardware_label = 'UVC CAMERA + MOCK MOTORS' if any(c.get('backend') == 'uvc' for cfg in configs.values() for c in cfg.get('cameras', {}).values()) else 'MOCK HARDWARE TEST'
        self.setWindowTitle('Robot Hardware Test System v0.1 — ' + hardware_label)
        self.resize(1920, 1080)
        self.setFont(QFont('DejaVu Sans', 10))
        QShortcut(QKeySequence('F11'), self, activated=self.toggle_fullscreen)
        QShortcut(QKeySequence('Escape'), self, activated=self.showNormal)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel(hardware_label + ' | Software STOP ≠ hardware emergency stop | F11: full screen / Esc: window'))
        close_button = QPushButton('EXIT / STOP ALL')
        close_button.clicked.connect(self.close)
        title_row.addWidget(close_button)
        layout.addLayout(title_row)
        panels = QHBoxLayout()
        layout.addLayout(panels, 1)
        self.labels = {}
        self.tables = {}
        for rid in configs:
            column = QVBoxLayout()
            panels.addLayout(column)
            label = QLabel(rid + ' OFFLINE')
            column.addWidget(label)
            table = QTableWidget(0, 5)
            table.setHorizontalHeaderLabels(['Device', 'State', 'Position', 'Velocity', 'Status / Counters'])
            table.verticalHeader().setDefaultSectionSize(24)
            table.setMinimumHeight(420)
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.verticalHeader().hide()
            for col_index, width in enumerate([106, 96, 88, 88]):
                table.setColumnWidth(col_index, width)
            table.setWordWrap(True)
            table.horizontalHeader().setStretchLastSection(True)
            column.addWidget(table)
            self.labels[rid] = label
            self.tables[rid] = table
        self.camera_panel = CameraPanel(bridge, configs)
        layout.addWidget(self.camera_panel)
        self.previews = self.camera_panel.previews
        row = QHBoxLayout()
        layout.addLayout(row)
        self.robot = QComboBox()
        self.robot.addItems(list(configs))
        self.axis = QComboBox()
        row.addWidget(self.robot)
        row.addWidget(self.axis)
        self.robot.currentTextChanged.connect(self.select_robot)
        self.axis.currentTextChanged.connect(lambda _: self.release_jog())
        self.select_robot(self.robot.currentText())
        self.minus = QPushButton('JOG − (hold)')
        self.plus = QPushButton('JOG + (hold)')
        self.stop_button = QPushButton('STOP')
        self.stop_all_button = QPushButton('STOP ALL')
        for b in [self.minus, self.stop_button, self.plus, self.stop_all_button]:
            row.addWidget(b)
        self.minus.pressed.connect(lambda: self.press_jog(-1))
        self.plus.pressed.connect(lambda: self.press_jog(1))
        self.minus.released.connect(self.release_jog)
        self.plus.released.connect(self.release_jog)
        self.stop_button.clicked.connect(self.stop_selected)
        self.stop_all_button.clicked.connect(self.stop_all)
        self.test_panel = TestPanel(self, layout)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        self.log.setFixedHeight(80)
        layout.addWidget(self.log)
        bridge.signals.changed.connect(lambda _rid: self.refresh(), Qt.QueuedConnection)
        bridge.signals.result.connect(self.on_result, Qt.QueuedConnection)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start(100)
        self.jog_timer = QTimer(self)
        self.jog_timer.timeout.connect(self.send_jog)
        self.jog_timer.start(100)
        QApplication.instance().installEventFilter(self)

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def select_robot(self, rid):
        self.release_jog()
        self.axis.clear()
        cfg = self.configs[rid]
        self.axis.addItems([name for name, axis in cfg['axes'].items() if cfg['hardware'][axis['bus']].get('enabled')])

    def press_jog(self, direction):
        self.release_jog()
        rid = self.robot.currentText()
        if not self.bridge.snapshot(rid).online:
            self.log.appendPlainText('JOG rejected: robot offline')
            return
        self.token += 1
        axis = self.axis.currentText()
        speed = self.configs[rid]['axes'][axis]['jog_velocity'] * direction
        self.active_jog = [rid, axis, speed, self.token, False]
        self.bridge.submit(rid, 'arm', self.token)

    def on_result(self, rid, action, token, ok, message):
        self.log.appendPlainText(f'{rid} {action}: {message}')
        if action == 'start_auto':
            if ok and token == self.token:
                self.auto_robots.add(rid)
            else:
                self.bridge.submit(rid, 'stop')
        if action == 'arm':
            if self.active_jog and token == self.active_jog[3] and ok:
                self.active_jog[4] = True
                self.send_jog()
            elif self.active_jog and token == self.active_jog[3]:
                self.release_jog()

    def send_jog(self):
        for rid in self.auto_robots:
            self.bridge.submit(rid, 'auto_keepalive')
        if self.active_jog and self.active_jog[4]:
            rid, axis, speed, _, _ = self.active_jog
            self.bridge.submit(rid, 'jog', axis=axis, velocity=speed)

    def release_jog(self):
        if self.active_jog:
            rid = self.active_jog[0]
            self.active_jog = None
            self.bridge.submit(rid, 'stop')

    def start_auto(self):
        self.release_jog()
        self.token += 1
        self.bridge.submit(self.robot.currentText(), 'start_auto', self.token)

    def stop_selected(self):
        self.token += 1
        self.auto_robots.discard(self.robot.currentText())
        self.release_jog()
        self.bridge.submit(self.robot.currentText(), 'stop')

    def stop_all(self):
        self.token += 1
        self.auto_robots.clear()
        self.release_jog()
        for rid in self.configs:
            self.bridge.submit(rid, 'stop')

    def refresh(self):
        for rid in self.configs:
            model = self.bridge.snapshot(rid)
            age = time.monotonic() - model.last_heartbeat if model.last_heartbeat else 0
            self.labels[rid].setText(f'{rid} {"ONLINE" if model.online else "OFFLINE"} | {model.robot_state} | {model.control_mode}\nHeartbeat age {age:.1f}s | uptime {model.uptime:.1f}s')
            self.labels[rid].setStyleSheet('color:' + ('green' if model.online else 'red'))
            self.camera_panel.refresh(rid, model)
            table = self.tables[rid]
            table.setRowCount(len(model.devices))
            for row, (name, device) in enumerate(model.devices.items()):
                cells = telemetry_cells(name, device, model.online)
                table.setRowHeight(row, 40 if '\n' in cells[-1] else 24)
                for col, val in enumerate(cells):
                    item = QTableWidgetItem(val)
                    item.setToolTip(device['message'] + '\n' + '\n'.join(f'{k}={v}' for k, v in device['values'].items()))
                    item.setForeground(QColor('gray' if device['message'].startswith('UNKNOWN') and model.online else {0:'green', 1:'#997000', 2:'red', 3:'red'}.get(device['level'], 'gray') if model.online else 'red'))
                    table.setItem(row, col, item)
            if not model.online:
                self.auto_robots.discard(rid)
            if self.active_jog and self.active_jog[0] == rid and not model.online:
                self.release_jog()
        online = self.bridge.snapshot(self.robot.currentText()).online
        self.plus.setEnabled(online)
        self.minus.setEnabled(online)

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.ApplicationDeactivate, QEvent.WindowDeactivate) and hasattr(self, 'active_jog'):
            self.release_jog()
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        self.stop_all()
        # Keep executor alive briefly so STOP service calls can be dispatched.
        QTimer.singleShot(300, QApplication.instance().quit)
        self.hide()
        event.ignore()

def load_configs():
    base = Path(os.environ['ROBOT_TEST_CONFIG_DIR']) if os.environ.get('ROBOT_TEST_CONFIG_DIR') else Path(get_package_share_directory('robot_test_bringup')) / 'config'
    return {p.stem: yaml.safe_load(p.read_text()) for p in sorted(base.glob('robot_*.yaml'))}

def main(args=None):
    rclpy.init(args=args)
    app = QApplication(sys.argv[:1])
    configs = load_configs()
    bridge = GroundBridge(configs)
    worker = RosWorker(bridge)
    window = GroundWindow(bridge, configs)
    window.showFullScreen()
    try:
        app.exec()
    finally:
        worker.close()
        bridge.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
