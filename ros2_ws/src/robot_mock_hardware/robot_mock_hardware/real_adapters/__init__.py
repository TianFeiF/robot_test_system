"""Real hardware extension points. No hardware I/O is implemented in v0.1."""
from robot_test_core.adapters import DeviceAdapter, MotorAdapter, CameraAdapter
from robot_test_core.models import DeviceStatus, DeviceState

class UnimplementedDevice(DeviceAdapter):
    def __init__(self, config=None):
        self.config = config or {}

    def connect(self) -> None:
        raise NotImplementedError(f'{type(self).__name__} requires a real driver implementation')

    def disconnect(self) -> None:
        pass

    def get_status(self) -> DeviceStatus:
        return DeviceStatus(DeviceState.ERROR, 'Real backend not implemented')

class RealMotorAdapter(UnimplementedDevice, MotorAdapter):
    def enable(self) -> None:
        raise NotImplementedError('Real motor enable')

    def disable(self) -> None:
        raise NotImplementedError('Real motor disable')

    def jog(self, velocity: float) -> None:
        raise NotImplementedError('Real motor jog')

    def stop(self) -> None:
        raise NotImplementedError('Real motor stop')

    def get_position(self) -> float:
        raise NotImplementedError('Real motor position')

    def get_velocity(self) -> float:
        raise NotImplementedError('Real motor velocity')

    def get_error(self) -> str:
        return 'Not implemented'

class EtherCATMotorAdapter(RealMotorAdapter):
    pass

class CANopenMotorAdapter(RealMotorAdapter):
    pass

class RealSenseCameraAdapter(UnimplementedDevice, CameraAdapter):
    def is_connected(self) -> bool:
        return False

    def get_frame(self):
        raise NotImplementedError('RealSense acquisition')

    def get_fps(self) -> float:
        return 0.0

    def get_frame_count(self) -> int:
        return 0

    def get_drop_count(self) -> int:
        return 0

class RM75Adapter(UnimplementedDevice):
    pass

class RS485Adapter(UnimplementedDevice):
    pass

class LidarAdapter(UnimplementedDevice):
    pass
