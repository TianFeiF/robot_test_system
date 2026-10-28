#!/usr/bin/env python3
"""Read-only image reception probe. Source scripts/env.sh and select ROS_DOMAIN_ID."""
import argparse
import json
import time
import rclpy
from diagnostic_msgs.msg import DiagnosticArray
from sensor_msgs.msg import CompressedImage
from rclpy.qos import QoSProfile, ReliabilityPolicy
from robot_test_ground.frame_stats import FrameStats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--robot', default='robot_a')
    parser.add_argument('--cameras', nargs='+', default=['camera_1', 'camera_2', 'camera_3'])
    parser.add_argument('--seconds', type=float, default=60)
    parser.add_argument('--reliable', action='store_true')
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error('--seconds must be positive')
    rclpy.init()
    node = rclpy.create_node('rgb_transport_probe')
    stats = {name: FrameStats() for name in args.cameras}
    capture = {name: {} for name in args.cameras}
    def diagnostics(msg):
        for entry in msg.status:
            if entry.name in capture:
                values = {v.key: v.value for v in entry.values}
                record = capture[entry.name]
                record.setdefault('first_frame_count', values.get('frame_count'))
                record.update(last_frame_count=values.get('frame_count'),
                              last_device_state=entry.message)
    qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE if args.reliable else ReliabilityPolicy.BEST_EFFORT)
    for name in stats:
        node.create_subscription(CompressedImage, f'/{args.robot}/cameras/{name}/image_raw/compressed',
                                 lambda msg, name=name: stats[name].record(time.monotonic()), qos)
    node.create_subscription(DiagnosticArray, f'/{args.robot}/diagnostics', diagnostics, 10)
    try:
        end = time.monotonic() + args.seconds
        while time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=min(.2, max(0., end-time.monotonic())))
        print(json.dumps({name: dict(stats[name].snapshot(time.monotonic()), **capture[name])
                          for name in stats}, indent=2, ensure_ascii=False))
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
