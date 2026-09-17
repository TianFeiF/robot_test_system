from enum import Enum
from .adapters import MotorAdapter

class CycleState(str, Enum):
    IDLE = 'IDLE'
    MOVE_POSITIVE = 'MOVE_POSITIVE'
    DWELL_POSITIVE = 'DWELL_POSITIVE'
    MOVE_NEGATIVE = 'MOVE_NEGATIVE'
    DWELL_NEGATIVE = 'DWELL_NEGATIVE'

class AutoCycle:
    def __init__(self, motor: MotorAdapter, config: dict):
        self.motor = motor
        self.config = config
        self.state = CycleState.MOVE_POSITIVE
        self.dwell_until = 0.0
        self.cycles = 0

    def tick(self, now: float, dt: float) -> None:
        # Approach targets from measured position, reducing final step to avoid overshoot.
        if self.state in (CycleState.DWELL_POSITIVE, CycleState.DWELL_NEGATIVE):
            self.motor.stop()
            if now >= self.dwell_until:
                self.state = CycleState.MOVE_NEGATIVE if self.state == CycleState.DWELL_POSITIVE else CycleState.MOVE_POSITIVE
            return
        positive = self.state == CycleState.MOVE_POSITIVE
        target = self.config['positive_target'] if positive else self.config['negative_target']
        remaining = target - self.motor.get_position()
        if abs(remaining) <= 0.0001:
            self.motor.stop()
            self.state = CycleState.DWELL_POSITIVE if positive else CycleState.DWELL_NEGATIVE
            self.dwell_until = now + self.config['dwell_sec']
            if not positive:
                self.cycles += 1
        else:
            speed = min(self.config['velocity'], abs(remaining) / max(dt, 0.001))
            self.motor.jog(speed if remaining > 0 else -speed)
