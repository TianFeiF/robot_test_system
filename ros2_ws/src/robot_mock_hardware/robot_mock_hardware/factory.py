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
    if kind == 'ethercat' and backend in ('ethercat', 'eyou'):
        from .real_adapters.ethercat import EtherCATBus
        return EtherCATBus(config)
    if kind == 'camera' and backend == 'realsense_depth':
        from .real_adapters.realsense_depth import RealSenseDepthAdapter
        return RealSenseDepthAdapter(config)
    if kind == 'lidar' and backend == 'livox':
        from .real_adapters.livox import LivoxMonitor
        return LivoxMonitor(config)
    if backend in ('ethercat_monitor', 'rm75_monitor', 'unavailable'):
        from .real_adapters.telemetry import EtherCATMonitor, RM75Monitor, UnavailableDevice
        return {'ethercat_monitor': EtherCATMonitor, 'rm75_monitor': RM75Monitor,
                'unavailable': UnavailableDevice}[backend](config)
    if kind == 'camera' and backend == 'uvc':
        from .real_adapters.uvc_camera import UVCCameraAdapter
        return UVCCameraAdapter(config)
    if backend not in DEVICE_BACKENDS:
        raise NotImplementedError(f'{kind} backend {backend!r} is not implemented')
    if kind == 'lidar' and backend == 'mock':
        from .lidar import MockLidarAdapter
        return MockLidarAdapter(config)
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
    devices = {name: create_device_adapter(name, settings)
               for name, settings in config['hardware'].items() if settings.get('enabled')}
    motors = {}
    for axis, settings in config['axes'].items():
        bus = config['hardware'][settings['bus']]
        if bus.get('enabled', False):
            if bus.get('backend') in ('ethercat', 'eyou'):
                from .real_adapters.ethercat import EtherCATMotor
                motors[axis] = EtherCATMotor(devices[settings['bus']], settings)
            elif bus.get('backend') == 'ethercat_monitor':
                from .real_adapters.telemetry import EtherCATReadOnlyMotor
                motors[axis] = EtherCATReadOnlyMotor(devices[settings['bus']], settings)
            else:
                motors[axis] = create_motor_adapter({**bus, **settings})
    devices.update({name: create_device_adapter('camera', settings)
                    for name, settings in camera_configs(config).items()})
    return motors, devices
