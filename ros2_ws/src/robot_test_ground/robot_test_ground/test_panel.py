from robot_test_core.config import camera_configs
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QPushButton, QComboBox, QLineEdit, QLabel

EVENTS = ['TEST START', 'EMC START', 'EQUIPOTENTIAL CONTACT', 'EQUIPOTENTIAL WORK', 'MAGNETIC FIELD', 'TEMP HUMIDITY', 'TEST END']

class TestPanel:
    def __init__(self, window, layout):
        self.window = window
        row = QHBoxLayout()
        layout.addLayout(row)
        self.start = QPushButton('START AUTO TEST')
        self.stop = QPushButton('STOP AUTO TEST')
        row.addWidget(self.start)
        row.addWidget(self.stop)
        self.start.clicked.connect(window.start_auto)
        self.stop.clicked.connect(window.stop_selected)
        row = QHBoxLayout()
        layout.addLayout(row)
        row.addWidget(QLabel('MOCK FAULT'))
        self.device = QComboBox()
        row.addWidget(self.device)
        for title, active in [('INJECT', True), ('RECOVER', False)]:
            button = QPushButton(title)
            button.clicked.connect(lambda checked=False, a=active: self.inject(a))
            row.addWidget(button)
        window.robot.currentTextChanged.connect(self.update_devices)
        self.update_devices(window.robot.currentText())
        self.description = QLineEdit()
        self.description.setPlaceholderText('Event description / test conditions')
        layout.addWidget(self.description)
        row = QHBoxLayout()
        layout.addLayout(row)
        self.event_buttons = {}
        for event in EVENTS:
            button = QPushButton(event)
            button.clicked.connect(lambda checked=False, e=event: window.bridge.submit(window.robot.currentText(), 'event', event_type=e, description=self.description.text()))
            row.addWidget(button)
            self.event_buttons[event] = button

    def update_devices(self, rid):
        self.device.clear()
        config = self.window.configs[rid]
        self.device.addItems(['heartbeat'] + list(config['axes']) + [n for n,c in config['hardware'].items() if c.get('enabled')] + list(camera_configs(config)))

    def inject(self, active):
        self.window.bridge.submit(self.window.robot.currentText(), 'inject_fault', device=self.device.currentText(), active=active)
