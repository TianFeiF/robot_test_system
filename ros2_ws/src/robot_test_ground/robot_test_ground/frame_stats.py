"""Ground-side image delivery metrics; independent of camera capture counters."""
from collections import deque


class FrameStats:
    def __init__(self):
        self.received = 0
        self.decode_errors = 0
        self.last = None
        self.max_gap = 0.0
        self.gaps_over_2s = 0
        self.recent = deque(maxlen=120)

    def record(self, now):
        if self.last is not None:
            gap = now - self.last
            self.max_gap = max(self.max_gap, gap)
            self.gaps_over_2s += int(gap >= 2.0)
        self.last = now
        self.received += 1
        self.recent.append(now)

    def snapshot(self, now):
        recent = [stamp for stamp in self.recent if now - stamp < 2.0]
        age = None if self.last is None else max(0.0, now - self.last)
        return dict(received_frames=self.received, decode_errors=self.decode_errors,
                    age_sec=None if age is None else round(age, 3),
                    receive_fps=round(len(recent) / 2.0, 1),
                    max_gap_sec=round(max(self.max_gap, age or 0.0), 3),
                    gaps_over_2s=self.gaps_over_2s,
                    fresh=age is not None and age < 2.0)
