import unittest
from robot_mock_hardware.lidar import MockLidarAdapter

class LidarTests(unittest.TestCase):
    def test_time_based_counts_and_fault_recovery(self):
        lidar=MockLidarAdapter({})
        lidar.connect()
        for _ in range(100):
            lidar.update(.01)
        self.assertEqual(lidar.point_count,200000)
        self.assertEqual(lidar.packet_count,2000)
        lidar.inject_fault('offline',True)
        lidar.update(1)
        self.assertEqual(lidar.point_count,200000)
        self.assertEqual(lidar.drop_count,2000)
        self.assertEqual(lidar.get_status().state.value,'OFFLINE')
        lidar.inject_fault('offline',False)
        lidar.update(.1)
        self.assertEqual(lidar.point_count,220000)
        self.assertEqual(lidar.reconnect_count,1)
        self.assertEqual(lidar.error_count,1)
