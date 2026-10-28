import unittest
from robot_test_ground.frame_stats import FrameStats


class FrameStatsTests(unittest.TestCase):
    def test_stall_is_visible_before_recovery(self):
        stats = FrameStats()
        self.assertFalse(stats.snapshot(10)['fresh'])
        stats.record(10)
        stats.record(10.2)
        self.assertTrue(stats.snapshot(11)['fresh'])
        stalled = stats.snapshot(15)
        self.assertFalse(stalled['fresh'])
        self.assertEqual(stalled['receive_fps'], 0)
        self.assertEqual(stalled['max_gap_sec'], 4.8)
        stats.record(16)
        recovered = stats.snapshot(16)
        self.assertTrue(recovered['fresh'])
        self.assertEqual(recovered['gaps_over_2s'], 1)
        self.assertEqual(recovered['received_frames'], 3)
        self.assertEqual(recovered['max_gap_sec'], 5.8)
