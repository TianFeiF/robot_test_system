from setuptools import setup
from glob import glob
setup(name='robot_test_ground', version='0.1.0', packages=['robot_test_ground'], data_files=[('share/ament_index/resource_index/packages', ['resource/robot_test_ground']), ('share/robot_test_ground', ['package.xml']), ('share/robot_test_ground/config', glob('config/*.yaml')), ('share/robot_test_ground/launch', glob('launch/*.launch.py'))], install_requires=['setuptools'], zip_safe=True, entry_points={'console_scripts':['ground_station = robot_test_ground.app:main']})
