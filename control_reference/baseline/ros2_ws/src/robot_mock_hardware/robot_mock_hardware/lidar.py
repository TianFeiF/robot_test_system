"""Diagnostics-only LiDAR simulation: no real packets or point cloud are published."""
from robot_test_core.adapters import DeviceAdapter, FaultInjectable
from robot_test_core.models import DeviceState, DeviceStatus


class MockLidarAdapter(DeviceAdapter, FaultInjectable):
    def __init__(self, config: dict):
        self.model = config.get('model', 'Livox (model pending)')
        self.rate = float(config.get('mock_scan_hz', 10.0))
        self.points_per_scan = int(config.get('mock_points_per_scan', 20000))
        self.packets_per_scan = int(config.get('mock_packets_per_scan', 200))
        if self.rate <= 0 or min(self.points_per_scan, self.packets_per_scan) <= 0:
            raise ValueError('LiDAR simulation rates must be positive')
        self.connected = False
        self.fault = False
        self.elapsed = 0.0
        self.frame_count = self.point_count = self.packet_count = 0
        self.drop_count = self.error_count = self.disconnect_count = self.reconnect_count = 0
        self.ever_connected = False

    def connect(self) -> None:
        if not self.connected and self.ever_connected:
            self.reconnect_count += 1
        self.connected = True
        self.ever_connected = True

    def disconnect(self) -> None:
        if self.connected:
            self.disconnect_count += 1
        self.connected = False

    def update(self, dt: float) -> None:
        self.elapsed += max(0.0, dt)
        scans = int((self.elapsed + 1e-9) * self.rate)
        self.elapsed -= scans / self.rate
        if not self.connected or self.fault:
            self.drop_count += scans * self.packets_per_scan
        else:
            self.frame_count += scans
            self.point_count += scans * self.points_per_scan
            self.packet_count += scans * self.packets_per_scan

    def get_status(self) -> DeviceStatus:
        healthy = self.connected and not self.fault
        return DeviceStatus(DeviceState.OK if healthy else DeviceState.OFFLINE,
                            f'MOCK diagnostics only; {self.model}',
                            dict(backend='mock', model=self.model, scan_hz=self.rate if healthy else 0.0,
                                 points_per_second=int(self.rate * self.points_per_scan) if healthy else 0,
                                 frame_count=self.frame_count, point_count=self.point_count,
                                 packet_count=self.packet_count, drop_count=self.drop_count,
                                 error_count=self.error_count, disconnect_count=self.disconnect_count,
                                 reconnect_count=self.reconnect_count))

    def inject_fault(self, fault: str, active: bool) -> None:
        if active and not self.fault:
            self.error_count += 1
            self.disconnect()
        elif not active and self.fault:
            self.connect()
        self.fault = active
