"""Real ROS processes + real Qt widgets; isolated ROS_DOMAIN_ID recommended."""
import os
import signal
import subprocess
import time
import tempfile
import yaml
from robot_test_core.config import camera_configs
from pathlib import Path
import rclpy
from PySide6.QtWidgets import QApplication
from robot_test_ground.app import GroundWindow, load_configs
from robot_test_ground.bridge import GroundBridge, RosWorker

ROOT = Path(__file__).resolve().parents[1]
app = QApplication([])
rclpy.init()
configs = load_configs()
config_directory = ROOT / 'ros2_ws/src/robot_test_bringup/config'
temporary_config = None
if os.environ.get('TEST_CAMERA_COUNT') == '4':
    configs['robot_a']['cameras']['camera_5']['enabled'] = False
    temporary_config = tempfile.TemporaryDirectory(prefix='robot-camera-acceptance-')
    config_directory = Path(temporary_config.name)
    for rid, config in configs.items():
        (config_directory / f'{rid}.yaml').write_text(yaml.safe_dump(config))
camera_keys = [(rid, camera_id) for rid, cfg in configs.items() for camera_id in camera_configs(cfg)]
bridge = GroundBridge(configs)
worker = RosWorker(bridge)
window = GroundWindow(bridge, configs)
window.show()
if os.environ.get("TEST_LAYOUT") == "1":
    window.resize(1920, 1080)
processes = {}
logs = {}
results = []

def start(rid):
    logs[rid] = open(ROOT / 'logs' / f'p0_{rid}.log', 'a')
    processes[rid] = subprocess.Popen(['ros2','run','robot_test_agent','agent','--ros-args','-r',f'__ns:=/{rid}','-p',f'config_file:={config_directory}/{rid}.yaml'], stdout=logs[rid], stderr=subprocess.STDOUT, start_new_session=True)

def pump(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)

def until(predicate, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError('Timed out waiting for condition')

def value(rid, key='velocity', axis='drive'):
    return float(bridge.snapshot(rid).devices.get(axis, {}).get('values', {}).get(key, 'nan'))

def check(name, predicate):
    assert predicate, name
    results.append(name)
    print('PASS:', name, flush=True)

try:
    (ROOT / 'logs').mkdir(exist_ok=True)
    for rid in configs:
        start(rid)
    until(lambda: all(bridge.snapshot(r).online and bridge.snapshot(r).devices for r in configs), 12)
    pump(0.15)
    check('A/B ONLINE and Diagnostics', all('ONLINE' in window.labels[r].text() for r in configs))
    until(lambda: all(bridge.frame(*key) is not None for key in camera_keys), 8)
    until(lambda: all(window.previews[key].pixmap() and not window.previews[key].pixmap().isNull() for key in camera_keys), 3)
    check(f'All {len(camera_keys)} independent camera previews live', len(window.previews) == len(camera_keys))
    if os.environ.get('TEST_LAYOUT') == '1':
        from PySide6.QtCore import QPoint, QRect
        assert window.width() == 1920 and window.height() == 1080, (window.size(), window.minimumSizeHint())
        bounds = window.centralWidget().rect()
        widgets = list(window.previews.values()) + list(window.camera_panel.status_labels.values()) + [window.plus, window.minus, window.stop_button, window.stop_all_button, window.log, window.test_panel.description, window.test_panel.start, window.test_panel.stop] + list(window.test_panel.event_buttons.values())
        for widget in widgets:
            rect = QRect(widget.mapTo(window.centralWidget(), QPoint(0, 0)), widget.size())
            assert bounds.contains(rect), (widget, rect, bounds)
        for rid, table in window.tables.items():
            assert table.verticalScrollBar().maximum() == 0, (rid, 'rows need scrolling')
            assert table.horizontalScrollBar().maximum() == 0, (rid, 'columns need scrolling')
            for row in range(table.rowCount()):
                for col in range(table.columnCount()):
                    item = table.item(row, col)
                    if item:
                        assert all(table.fontMetrics().horizontalAdvance(line) <= table.columnWidth(col) - 8 for line in item.text().splitlines()), (rid, row, col, item.text())
        check('1920x1080: every device row, camera and control visible without elision', True)
        window.grab().save(str(ROOT / 'logs' / 'dashboard_1920x1080.png'))

    for rid, cfg in configs.items():
        expected = set(camera_configs(cfg))
        actual = {name for name in bridge.snapshot(rid).devices if name.startswith('camera_')}
        check(f'{rid}: configured camera diagnostics match', expected == actual)
    victim = ('robot_a', next(reversed(camera_configs(configs['robot_a']))))
    other_keys = [key for key in camera_keys if key != victim]
    before_frames = {key: bridge.frame(*key)[0] for key in other_keys}
    bridge.submit(victim[0], 'inject_fault', device=victim[1], active=True)
    until(lambda: bridge.snapshot(victim[0]).devices[victim[1]]['level'] == 3)
    pump(0.5)
    check('Single camera fault leaves every other stream running', all(bridge.frame(*key)[0] > before_frames[key] for key in other_keys))
    check('Faulted preview clears', window.previews[victim].pixmap().isNull())
    bridge.submit(victim[0], 'inject_fault', device=victim[1], active=False)
    until(lambda: bridge.snapshot(victim[0]).devices[victim[1]]['level'] == 0 and not window.previews[victim].pixmap().isNull())
    check('Individual camera recovers', True)
    window.plus.pressed.emit()
    until(lambda: value('robot_a') > 0)
    p = value('robot_a', 'position')
    pump(0.5)
    check('Held JOG advances position', value('robot_a', 'position') > p)
    window.plus.released.emit()
    until(lambda: value('robot_a') == 0)
    check('Release stops and disarms', bridge.snapshot('robot_a').devices['drive']['values']['enabled'] == 'False')
    window.press_jog(1)
    until(lambda: value('robot_a') > 0)
    # Cut transport stream without delivering STOP; agent watchdog must stop itself.
    window.active_jog = None
    began = time.monotonic()
    until(lambda: value('robot_a') == 0, 1.2)
    watchdog_observed = time.monotonic() - began
    check(f'500ms watchdog: stop observed in {watchdog_observed:.3f}s including telemetry delay', watchdog_observed < 0.85)
    for rid in configs:
        bridge.submit(rid, 'arm')
    pump(0.3)
    for _ in range(5):
        for rid in configs:
            bridge.submit(rid, 'jog', axis='drive', velocity=0.1)
        pump(0.1)
    check('Both robots moving before STOP ALL', all(value(r) > 0 for r in configs))
    window.stop_all_button.click()
    until(lambda: all(value(r) == 0 for r in configs))
    for _ in range(7):
        for rid in configs:
            bridge.submit(rid, 'jog', axis='drive', velocity=0.1)
        pump(0.1)
    check('STOP ALL rejects residual JOG', all(value(r) == 0 for r in configs))
    os.killpg(processes['robot_a'].pid, signal.SIGINT)
    processes['robot_a'].wait(timeout=5)
    until(lambda: not bridge.snapshot('robot_a').online, 3.3)
    pump(0.15)
    check('A offline, B remains online', 'OFFLINE' in window.labels['robot_a'].text() and bridge.snapshot('robot_b').online)
    start('robot_a')
    until(lambda: bridge.snapshot('robot_a').online, 8)
    pump(0.2)
    check('A restart recovers without restarting Ground', 'ONLINE' in window.labels['robot_a'].text())
    if os.environ.get('TEST_P1') == '1':
        import csv
        until(lambda: all(bridge.frame(*key) is not None for key in camera_keys), 5)
        pump(0.3)
        check('A/B live camera previews', all(window.previews[key].pixmap() and not window.previews[key].pixmap().isNull() for key in camera_keys))
        window.test_panel.start.click()
        until(lambda: value('robot_a') > 0)
        until(lambda: value('robot_a') == 0 and value('robot_a', 'position') > 0.99, 14)
        check('Auto reaches positive target and dwells', abs(value('robot_a', 'position') - 1.0) < 0.002)
        until(lambda: value('robot_a') < 0, 3)
        until(lambda: value('robot_a') == 0 and value('robot_a', 'position') < -0.99, 24)
        check('Auto reaches negative target and dwells', abs(value('robot_a', 'position') + 1.0) < 0.002)
        until(lambda: value('robot_a') > 0, 3)
        window.stop_button.click()
        until(lambda: value('robot_a') == 0)
        check('STOP interrupts Auto Cycle', bridge.snapshot('robot_a').devices['System']['values']['auto_state'] == 'IDLE')
        window.start_auto()
        until(lambda: value('robot_a') > 0)
        window.auto_robots.clear()
        until(lambda: value('robot_a') == 0, 1.2)
        check('Auto keepalive loss invokes watchdog', bridge.snapshot('robot_a').devices['System']['values']['auto_state'] == 'IDLE')
        for rid in configs:
            window.robot.setCurrentText(rid)
            window.start_auto()
            until(lambda: value(rid) != 0)
        window.stop_all()
        until(lambda: all(value(r) == 0 and bridge.snapshot(r).devices['System']['values']['auto_state'] == 'IDLE' for r in configs))
        check('STOP ALL cancels both automatic cycles', True)
        for rid, device, expected in [('robot_a','camera_1',3), ('robot_a','ethercat',2), ('robot_a','drive',2), ('robot_a','rs485',2), ('robot_b','canopen',3), ('robot_a','network',1)]:
            window.robot.setCurrentText(rid)
            window.test_panel.device.setCurrentText(device)
            window.test_panel.inject(True)
            until(lambda: bridge.snapshot(rid).devices[device]['level'] == expected)
            check(f'{rid}/{device} injected fault visible', True)
            window.test_panel.inject(False)
            until(lambda: bridge.snapshot(rid).devices[device]['level'] == 0)
            check(f'{rid}/{device} recovery', True)
            if device.startswith('camera_'):
                until(lambda: bridge.snapshot(rid).devices[device]['values']['reconnect_count'] != '0')
                check('Camera reconnect counter recorded', True)
        bridge.submit('robot_a', 'inject_fault', device='heartbeat', active=True)
        until(lambda: not bridge.snapshot('robot_a').online, 3.5)
        check('Heartbeat drop -> OFFLINE while B stays online', bridge.snapshot('robot_b').online)
        bridge.submit('robot_a', 'inject_fault', device='heartbeat', active=False)
        until(lambda: bridge.snapshot('robot_a').online, 3)
        window.test_panel.description.setText('Acceptance equipotential marker')
        window.test_panel.event_buttons['EQUIPOTENTIAL CONTACT'].click()
        pump(0.5)
        logdir = bridge.csv.directory
        rows = []
        for name in ['ground','robot_a','robot_b']:
            with (logdir / f'{name}_events.csv').open() as handle:
                marks = [r for r in csv.DictReader(handle) if r['event'] == 'EQUIPOTENTIAL CONTACT']
                assert marks, name
                rows.append(marks[-1])
        check('Event marker logged by all three with identical time/id', len({(r['timestamp'],r['value']) for r in rows}) == 1)
        check('All status CSV files contain records', all((logdir / f'{name}_status.csv').stat().st_size > 200 for name in ['ground','robot_a','robot_b']))
    window.grab().save(str(ROOT / 'logs' / f'multicamera_{len(camera_keys)}_ground.png'))
    (ROOT / 'logs' / f'multicamera_{len(camera_keys)}_results.txt').write_text('\n'.join(results) + '\n')
finally:
    window.stop_all()
    pump(0.3)
    worker.close()
    bridge.destroy_node()
    rclpy.shutdown()
    for process in processes.values():
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGINT)
            process.wait(timeout=5)
    for f in logs.values():
        f.close()

if temporary_config:
    temporary_config.cleanup()
