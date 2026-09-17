from setuptools import setup
from glob import glob
setup(name='robot_test_bringup', version='0.1.0', packages=['robot_test_bringup'], data_files=[('share/ament_index/resource_index/packages', ['resource/robot_test_bringup']), ('share/robot_test_bringup', ['package.xml']), ('share/robot_test_bringup/config', glob('config/*.yaml')), ('share/robot_test_bringup/launch', glob('launch/*.launch.py'))], install_requires=['setuptools'], zip_safe=True, entry_points={'console_scripts':[]})
