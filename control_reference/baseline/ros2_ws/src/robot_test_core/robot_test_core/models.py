from enum import Enum
from dataclasses import dataclass, field
from typing import Dict

class RobotState(str, Enum):
    OFFLINE = 'OFFLINE'
    INITIALIZING = 'INITIALIZING'
    READY = 'READY'
    RUNNING = 'RUNNING'
    WARNING = 'WARNING'
    FAULT = 'FAULT'
    STOPPED = 'STOPPED'

class DeviceState(str, Enum):
    UNKNOWN = 'UNKNOWN'
    OK = 'OK'
    WARN = 'WARN'
    ERROR = 'ERROR'
    OFFLINE = 'OFFLINE'

class ControlMode(str, Enum):
    MONITOR = 'MONITOR'
    MANUAL = 'MANUAL'
    AUTO_TEST = 'AUTO_TEST'

@dataclass
class DeviceStatus:
    state: DeviceState = DeviceState.UNKNOWN
    detail: str = ''
    values: Dict[str, object] = field(default_factory=dict)
