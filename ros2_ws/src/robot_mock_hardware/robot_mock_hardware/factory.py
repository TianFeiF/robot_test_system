"""Only the composition factory knows concrete backends; agent uses contracts."""
from robot_test_core.adapters import DeviceAdapter, MotorAdapter
from robot_test_core.config import camera_configs
from .motor import MockMotorAdapter
from .devices import MockDeviceAdapter

MOTOR_BACKENDS = {'mock': lambda config: MockMotorAdapter()}
DEVICE_BACKENDS = {'mock': lambda kind, config: MockDeviceAdapter(kind)}

def create_motor_adapter(config: dict) -> MotorAdapter:
    backend = config.get('backend', 'mock')
    if backend not in MOTOR_BACKENDS:
        raise NotImplementedError(f'Motor backend {backend!r} is not implemented')
    return MOTOR_BACKENDS[backend](config)

def create_device_adapter(kind: str, config: dict) -> DeviceAdapter:
    backend = config.get('backend', 'mock')
    if backend not in DEVICE_BACKENDS:
        raise NotImplementedError(f'{kind} backend {backend!r} is not implemented')
    if kind == 'camera' and backend == 'mock':
        from .camera import MockCameraAdapter
        return MockCameraAdapter(config)
    return DEVICE_BACKENDS[backend](kind, config)

# Real constructors deliberately return non-operational stubs, never a mock fallback.
from .real_adapters import (EtherCATMotorAdapter, CANopenMotorAdapter,
                            RealSenseCameraAdapter, RM75Adapter, RS485Adapter,
                            LidarAdapter, UnimplementedDevice)

def real_motor(config: dict) -> MotorAdapter:
    types = {'ethercat': EtherCATMotorAdapter, 'canopen': CANopenMotorAdapter}
    return types[config['bus']](config)

def real_device(kind: str, config: dict) -> DeviceAdapter:
    types = {'camera': RealSenseCameraAdapter, 'rm75': RM75Adapter, 'rs485': RS485Adapter, 'lidar': LidarAdapter}
    return types.get(kind, UnimplementedDevice)(config)

MOTOR_BACKENDS['real'] = real_motor
DEVICE_BACKENDS['real'] = real_device


def create_hardware(config: dict):
    """Axes inherit their bus backend; only the factory resolves backend wiring."""
    motors = {}
    for axis, settings in config['axes'].items():
        bus = config['hardware'][settings['bus']]
        if bus.get('enabled', False):
            motors[axis] = create_motor_adapter({**bus, **settings})
    devices = {name: create_device_adapter(name, settings)
               for name, settings in config['hardware'].items() if settings.get('enabled')}
    devices.update({name: create_device_adapter('camera', settings)
                    for name, settings in camera_configs(config).items()})
    return motors, devices
