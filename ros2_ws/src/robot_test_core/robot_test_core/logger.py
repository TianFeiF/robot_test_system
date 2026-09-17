"""Append-only CSV; UTC timestamps and immediate flush for test correlation."""
import csv
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

FIELDS = ['timestamp', 'robot', 'device', 'level', 'event', 'value', 'detail']

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')

def ros_timestamp(stamp) -> str:
    return datetime.fromtimestamp(stamp.sec + stamp.nanosec / 1e9, timezone.utc).isoformat(timespec='microseconds')

class CsvLogger:
    def __init__(self, name: str):
        self.name = name
        session = os.environ.get('ROBOT_TEST_SESSION', datetime.now(timezone.utc).strftime('%Y%m%d'))
        root = Path(os.environ.get('ROBOT_TEST_LOG_ROOT', str(Path.cwd() / 'logs')))
        self.directory = root / session
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.files = {}
        self.writers = {}
        self.failed = False
        for kind in ['status', 'events']:
            path = self.directory / f'{name}_{kind}.csv'
            handle = path.open('a', newline='', buffering=1)
            writer = csv.DictWriter(handle, FIELDS)
            if path.stat().st_size == 0:
                writer.writeheader()
            self.files[kind] = handle
            self.writers[kind] = writer

    def write(self, kind: str, *, device='', level='INFO', event='', value='', detail='', timestamp=None):
        try:
            with self.lock:
                self.writers[kind].writerow(dict(timestamp=timestamp or utc_now(), robot=self.name, device=device,
                                               level=level, event=event, value=value, detail=detail))
                self.files[kind].flush()
        except OSError:
            if not self.failed:
                logging.exception('CSV logging failed; control loop remains operational')
            self.failed = True

    def close(self):
        with self.lock:
            for handle in self.files.values():
                handle.close()
