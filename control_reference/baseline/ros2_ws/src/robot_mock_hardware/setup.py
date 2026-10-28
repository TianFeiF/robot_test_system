from setuptools import setup, find_packages
from glob import glob
setup(name='robot_mock_hardware', version='0.1.0', packages=find_packages(), data_files=[('share/ament_index/resource_index/packages', ['resource/robot_mock_hardware']), ('share/robot_mock_hardware', ['package.xml']), ('share/robot_mock_hardware/config', glob('config/*.yaml')), ('share/robot_mock_hardware/launch', glob('launch/*.launch.py'))], install_requires=['setuptools'], zip_safe=True, entry_points={'console_scripts':[]})
