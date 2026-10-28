from robot_test_core.adapters import MotorAdapter, FaultInjectable
from robot_test_core.models import DeviceState, DeviceStatus

class MockMotorAdapter(MotorAdapter, FaultInjectable):
    def __init__(self):
        self.connected = False
        self.enabled = False
        self.position = 0.0
        self.velocity = 0.0
        self.error = ''
        self.error_count = 0
        self.reconnect_count = 0
        self._ever_connected = False

    def connect(self) -> None:
        if not self.connected and self._ever_connected:
            self.reconnect_count += 1
        self.connected = True
        self._ever_connected = True

    def disconnect(self) -> None:
        self.disable()
        self.connected = False

    def enable(self) -> None:
        if not self.connected or self.error:
            raise RuntimeError('Motor unavailable')
        self.enabled = True

    def disable(self) -> None:
        self.stop()
        self.enabled = False

    def jog(self, velocity: float) -> None:
        if not self.enabled or not self.connected or self.error:
            raise RuntimeError('Motor is not enabled or has a fault')
        self.velocity = velocity

    def stop(self) -> None:
        self.velocity = 0.0

    def update(self, dt: float) -> None:
        if self.enabled and self.connected and not self.error:
            self.position += self.velocity * dt

    def get_position(self) -> float:
        return self.position

    def get_velocity(self) -> float:
        return self.velocity

    def get_error(self) -> str:
        return self.error

    def get_status(self) -> DeviceStatus:
        state = DeviceState.OFFLINE if not self.connected else DeviceState.ERROR if self.error else DeviceState.OK
        return DeviceStatus(state, self.error, dict(enabled=self.enabled, position=self.position, velocity=self.velocity, error_count=self.error_count, reconnect_count=self.reconnect_count))

    def inject_fault(self, fault: str, active: bool) -> None:
        if active and not self.error:
            self.error_count += 1
        self.error = 'Injected motor fault' if active else ''
        if active:
            self.disable()
