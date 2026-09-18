"""Run on ground with a separately started monitor-only Robot A in the same ROS domain.

Never sends JOG/auto commands. Checks the explicit monitor-only interlock before
testing arm rejection. Saves actual diagnostics and one received color image.
"""
import json
import argparse
import time
from pathlib import Path

import cv2
import numpy as np
import rclpy
from rclpy.qos import qos_profile_sensor_data
from diagnostic_msgs.msg import DiagnosticArray
from sensor_msgs.msg import CompressedImage
from std_srvs.srv import SetBool
from robot_test_msgs.msg import RobotHeartbeat, TestEvent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rgb-only', action='store_true', help='Do not require lidar for a camera-only field check')
    args = parser.parse_args()
    rclpy.init()
    node = rclpy.create_node('site_readonly_probe')
    diagnostics = {}
    counts = {'heartbeat': 0, 'camera_1': 0, 'camera_2': 0, 'camera_3': 0}
    frames = {}
    def heartbeat(msg):
        counts['heartbeat'] += 1
    def diag(msg):
        for entry in msg.status:
            diagnostics[entry.name] = {'message': entry.message,
                                      'values': {v.key: v.value for v in entry.values}}
    def frame(msg, name):
        counts[name] += 1
        frames[name] = msg
    node.create_subscription(RobotHeartbeat, '/robot_a/heartbeat', heartbeat, 10)
    node.create_subscription(DiagnosticArray, '/robot_a/diagnostics', diag, 10)
    for name in ('camera_1', 'camera_2', 'camera_3'):
        node.create_subscription(CompressedImage, f'/robot_a/cameras/{name}/image_raw/compressed',
                                 lambda msg, n=name: frame(msg, n), qos_profile_sensor_data)
    end = time.monotonic() + 20
    while time.monotonic() < end:
        rclpy.spin_once(node, timeout_sec=0.2)
    assert counts['heartbeat'] >= 3, counts
    assert all(counts[name] >= 30 for name in ('camera_1', 'camera_2', 'camera_3')), counts
    if not args.rgb_only:
        assert diagnostics['lidar']['message'].startswith('OK'), diagnostics['lidar']
        assert float(diagnostics['lidar']['values']['points_per_second']) > 100000
    assert diagnostics['System']['values'].get('monitor_only') == 'True', diagnostics
    client = node.create_client(SetBool, '/robot_a/arm')
    assert client.wait_for_service(timeout_sec=3)
    future = client.call_async(SetBool.Request(data=True))
    rclpy.spin_until_future_complete(node, future, timeout_sec=3)
    assert future.done() and not future.result().success
    assert 'Monitor-only' in future.result().message
    publisher = node.create_publisher(TestEvent, '/robot_a/test_event', 10)
    end = time.monotonic() + 3
    while not publisher.get_subscription_count() and time.monotonic() < end:
        rclpy.spin_once(node, timeout_sec=0.1)
    assert publisher.get_subscription_count()
    event = TestEvent(event_id='site_readonly_validation', event_type='REMOTE_LINK_TEST',
                      description='Read-only deployment validation; no motion')
    event.stamp = node.get_clock().now().to_msg()
    publisher.publish(event)
    end = time.monotonic() + 1
    while time.monotonic() < end:
        rclpy.spin_once(node, timeout_sec=0.1)
    root = Path('logs/rgb_reconnect_validation' if args.rgb_only else 'logs/robot_a_site_validation')
    root.mkdir(parents=True, exist_ok=True)
    report = {'counts': counts, 'diagnostics': diagnostics, 'arm_rejection': future.result().message}
    (root / 'ground_probe.json').write_text(json.dumps(report, indent=2))
    for name, msg in frames.items():
        pixels = cv2.imdecode(np.frombuffer(bytes(msg.data), dtype=np.uint8), cv2.IMREAD_COLOR)
        assert pixels is not None
        cv2.imwrite(str(root / (name + '.jpg')), pixels)
    print(json.dumps(report, indent=2))
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
