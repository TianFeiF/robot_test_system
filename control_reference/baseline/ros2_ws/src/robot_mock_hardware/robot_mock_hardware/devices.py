from robot_test_core.adapters import DeviceAdapter, FaultInjectable
from robot_test_core.models import DeviceState, DeviceStatus

class MockDeviceAdapter(DeviceAdapter, FaultInjectable):
    def __init__(self, kind: str):
        self.kind = kind
        self.connected = False
        self.fault = False
        self.counters = dict(rx_count=0, tx_count=0, timeout_count=0, error_count=0, reconnect_count=0,
                             cycle_count=0, slave_lost_count=0, recover_count=0, message_count=0,
                             request_count=0, response_count=0, crc_error_count=0)

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def update(self, dt: float) -> None:
        c = self.counters
        c['tx_count'] += 1
        c['cycle_count'] += 1
        c['request_count'] += 1
        if self.connected and not self.fault:
            for key in ['rx_count', 'message_count', 'response_count']:
                c[key] += 1
        elif self.fault:
            c['timeout_count'] += 1

    def get_status(self) -> DeviceStatus:
        state = DeviceState.OK
        if not self.connected:
            state = DeviceState.OFFLINE
        elif self.fault:
            state = DeviceState.WARN if self.kind == 'network' else DeviceState.OFFLINE if self.kind == 'canopen' else DeviceState.ERROR
        return DeviceStatus(state, 'Injected fault' if self.fault else '', dict(self.counters))

    def inject_fault(self, fault: str, active: bool) -> None:
        if active and not self.fault:
            self.counters['error_count'] += 1
            if self.kind == 'ethercat':
                self.counters['slave_lost_count'] += 1
        elif self.fault and not active:
            self.counters['recover_count'] += 1
            self.counters['reconnect_count'] += 1
        self.fault = active
