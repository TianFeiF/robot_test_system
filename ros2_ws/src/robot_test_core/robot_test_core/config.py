"""Shared camera inventory for adapters, ROS transport and the ground UI."""
import re


def camera_configs(config: dict) -> dict:
    cameras = config.get('cameras', {})
    reserved = set(config.get('axes', {})) | set(config.get('hardware', {})) | {'System', 'heartbeat'}
    for camera_id in cameras:
        if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]*', camera_id) or camera_id in reserved:
            raise ValueError(f'Invalid or conflicting camera id: {camera_id}')
    return {name: settings for name, settings in cameras.items() if settings.get('enabled', True)}
