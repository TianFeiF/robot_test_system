from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
from pathlib import Path

def generate_launch_description():
    config = Path(get_package_share_directory('robot_test_bringup')) / 'config'
    return LaunchDescription([
        Node(package='robot_test_agent', executable='agent', namespace=rid,
             parameters=[{'config_file':str(config / (rid + '.yaml'))}], output='screen')
        for rid in ('robot_a', 'robot_b')
    ])
