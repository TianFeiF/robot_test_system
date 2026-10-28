from setuptools import setup
from glob import glob
setup(name='robot_test_agent', version='0.1.0', packages=['robot_test_agent'], data_files=[('share/ament_index/resource_index/packages', ['resource/robot_test_agent']), ('share/robot_test_agent', ['package.xml']), ('share/robot_test_agent/config', glob('config/*.yaml')), ('share/robot_test_agent/launch', glob('launch/*.launch.py'))], install_requires=['setuptools'], zip_safe=True, entry_points={'console_scripts':['agent = robot_test_agent.node:main']})
