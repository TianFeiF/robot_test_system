"""Bounded automatic cycles for every configured motor."""
import math

class AutoAxisCycle:
    def __init__(self, motor, axis_config, cycle_config):
        self.motor, self.axis_config, self.config = motor, axis_config, cycle_config
        self.torque = axis_config.get('control_mode') == 'torque' or axis_config.get('bus') == 'canopen'
        self.default_torque = 800 if axis_config.get('bus') == 'canopen' else 400
        self.direction = 1
        self.next_reverse = 0.0
        self.start_position = motor.get_position()

    def tick(self, now, dt):
        if self.torque:
            period = float(self.config.get('period_sec', 10.0))
            if self.next_reverse == 0.0:
                self.next_reverse = now + period / 2.0
            elif now >= self.next_reverse:
                self.direction *= -1
                self.next_reverse = now + period / 2.0
            self.motor.set_torque(self.direction * float(self.config.get('torque_raw', self.default_torque)))
            return
        position = self.motor.get_position()
        travel = float(self.config.get('travel_m', 0.0))
        absolute_window = 'position_min_m' in self.config or 'position_max_m' in self.config
        if not travel and not absolute_window and self.next_reverse == 0.0:
            self.next_reverse = now + float(self.config.get('reverse_period_sec', 5.0))
        elif not travel and not absolute_window and now >= self.next_reverse:
            self.direction *= -1
            self.next_reverse = now + float(self.config.get('reverse_period_sec', 5.0))
        if travel > 0 or absolute_window:
            # A configured absolute pair is used for axes whose test window
            # is tied to a calibrated reference (the Z cycle is 0..20 mm).
            # Keep the legacy relative-to-start behavior for other axes.
            if 'position_min_m' in self.config or 'position_max_m' in self.config:
                low = float(self.config.get('position_min_m', self.axis_config.get('position_min', -math.inf)))
                high = float(self.config.get('position_max_m', low + travel))
            else:
                low = max(float(self.axis_config.get('position_min', -math.inf)), self.start_position)
                high = min(float(self.axis_config.get('position_max', math.inf)), self.start_position + travel)
            if not math.isfinite(low) or not math.isfinite(high) or high <= low:
                raise ValueError(f'Invalid auto-cycle position window [{low}, {high}]')
            if position <= low + 1e-6: self.direction = 1
            elif position >= high - 1e-6: self.direction = -1
        speed = min(float(self.config.get('velocity', self.axis_config['max_velocity'])), float(self.axis_config['max_velocity']))
        self.motor.jog(self.direction * speed)

class AutoCycle:
    """Run all configured axes, retaining the legacy single-axis cycle as fallback."""
    def __init__(self, motors, config, axes_config=None):
        self.axes = {}
        self.legacy = None
        axes_config = axes_config or {}
        if not config.get('axes'):
            name = config.get('axis')
            if name in motors:
                self.legacy = {'motor': motors[name], 'config': config, 'state': 'POS', 'dwell_until': 0.0}
            return
        for name, motor in motors.items():
            if config.get('axes', {}).get(name, {}).get('enabled', True) is False:
                continue
            axis = axes_config.get(name, {})
            if axis.get('control_mode') == 'torque' or axis.get('bus') == 'canopen':
                cycle = {'period_sec': 10.0, 'torque_raw': 800 if axis.get('bus') == 'canopen' else 400}
            elif name == 'z_axis':
                cycle = {'travel_m': 0.1, 'velocity': axis.get('max_velocity', 0.01)}
            else:
                cycle = {'travel_m': 0.0, 'velocity': math.radians(10), 'reverse_period_sec': 5.0}
            cycle.update(config.get('axes', {}).get(name, {}))
            self.axes[name] = AutoAxisCycle(motor, axis, cycle)

    def tick(self, now, dt):
        if self.legacy:
            motor, cfg, state = self.legacy['motor'], self.legacy['config'], self.legacy['state']
            if state.startswith('DWELL'):
                motor.stop()
                if now >= self.legacy['dwell_until']:
                    self.legacy['state'] = 'NEG' if state == 'DWELL_POS' else 'POS'
                return
            positive = state == 'POS'
            target = cfg['positive_target'] if positive else cfg['negative_target']
            remaining = target - motor.get_position()
            if abs(remaining) <= 0.0001:
                motor.stop(); self.legacy['state'] = 'DWELL_POS' if positive else 'DWELL_NEG'
                self.legacy['dwell_until'] = now + cfg['dwell_sec']
            else:
                motor.jog((1 if remaining > 0 else -1) * min(cfg['velocity'], abs(remaining) / max(dt, .001)))
            return
        for cycle in self.axes.values(): cycle.tick(now, dt)
