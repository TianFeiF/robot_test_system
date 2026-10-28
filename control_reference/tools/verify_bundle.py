#!/usr/bin/env python3
"""Read-only verification of the frozen reference package; no ROS or hardware calls."""
import hashlib
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / 'manifest.json').read_text())
errors = []
expected = set()
for entry in manifest['files']:
    relative = entry['path']
    path = root / relative
    if Path(relative).is_absolute() or '..' in Path(relative).parts:
        errors.append(f'Invalid manifest path: {relative}')
        continue
    expected.add(relative)
    if entry['type'] == 'symlink':
        if not path.is_symlink() or str(path.readlink()) != entry['target']:
            errors.append(f'Link mismatch: {relative}')
        elif not path.exists() or not path.resolve().is_relative_to(root):
            errors.append(f'Broken/external link: {relative}')
    elif not path.is_file() or path.is_symlink():
        errors.append(f'Missing/non-regular file: {relative}')
    elif hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
        errors.append(f'Hash mismatch: {relative}')
actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() or p.is_symlink()}
extras = actual - expected - {'manifest.json'}
if extras:
    errors.append(f'Unlisted files: {sorted(extras)}')
for line in errors:
    print('ERROR:', line)
if errors:
    sys.exit(1)
print(f'PASS: {len(expected)} entries verified; all links stay within the bundle.')
print('Source archive only. Vendor SDK/runtime completeness and hardware readiness are not certified.')
