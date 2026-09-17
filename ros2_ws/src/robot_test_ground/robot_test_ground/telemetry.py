"""Compact, labelled telemetry without hiding motion values in an elided blob."""
COUNTERS = {
    'ethercat': [('cycle_count', 'cycle'), ('error_count', 'err'), ('slave_lost_count', 'lost'), ('recover_count', 'recover')],
    'canopen': [('message_count', 'msg'), ('timeout_count', 'timeout'), ('error_count', 'err')],
    'rs485': [('request_count', 'req'), ('response_count', 'resp'), ('timeout_count', 'timeout'), ('crc_error_count', 'CRC')],
}


def number(value: str) -> str:
    try:
        return f'{float(value):.4f}'
    except (ValueError, TypeError):
        return str(value)


def telemetry_cells(name: str, device: dict, online: bool) -> list:
    values = device['values']
    position = number(values['position']) if 'position' in values else '—'
    velocity = number(values['velocity']) if 'velocity' in values else '—'
    if 'position' in values:
        keys = [('enabled', 'enabled'), ('error_count', 'err'), ('reconnect_count', 'reconnect')]
    elif 'frame_count' in values:
        keys = [('fps', 'FPS'), ('frame_count', 'frames'), ('drop_count', 'drop'), ('disconnect_count', 'disconnect'), ('reconnect_count', 'reconnect')]
    elif name == 'System':
        keys = [('armed', 'armed'), ('control_mode', 'mode'), ('auto_state', 'auto')]
    else:
        keys = COUNTERS.get(name, [('rx_count', 'rx'), ('tx_count', 'tx'), ('timeout_count', 'timeout'), ('error_count', 'err'), ('reconnect_count', 'reconnect')])
    items = [f'{label}={values[key]}' for key, label in keys if key in values]
    summary = '\n'.join('  '.join(items[i:i+3]) for i in range(0, len(items), 3))
    state = device['message'].split(':', 1)[0] if online else 'OFFLINE'
    return [name, state, position, velocity, summary]
