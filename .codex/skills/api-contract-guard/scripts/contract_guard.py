#!/usr/bin/env python3
"""Recommend and optionally run contract checks for content-ops-agent changes."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple


def normalize_path(path: str) -> str:
    return path.replace('\\', '/').lstrip('./').lower()


def classify_paths(changed: Iterable[str]) -> Dict[str, bool]:
    flags = {
        'api_contract': False,
        'storage': False,
        'config': False,
        'jobs': False,
        'frontend_api': False,
        'frontend_any': False,
    }
    for raw in changed:
        p = normalize_path(raw)
        if p.startswith('src/api/routes/') or p.startswith('src/api/schemas/') or p.startswith('src/api/services/'):
            flags['api_contract'] = True
        if p.startswith('src/storage/') or p.startswith('src/models/'):
            flags['storage'] = True
        if p == 'src/utils/config.py':
            flags['config'] = True
        if p.startswith('src/jobs/'):
            flags['jobs'] = True
        if p.startswith('frontend/src/api/'):
            flags['frontend_api'] = True
        if p.startswith('frontend/'):
            flags['frontend_any'] = True
    return flags


def recommend_commands(flags: Dict[str, bool], changed: List[str]) -> List[Tuple[List[str], Path]]:
    commands: List[Tuple[List[str], Path]] = []

    def add(cmd: List[str], cwd: Path) -> None:
        entry = (cmd, cwd)
        if entry not in commands:
            commands.append(entry)

    if not changed:
        add([sys.executable, '-m', 'pytest', 'tests/test_api_contract.py', '-q'], Path('.'))
        add([sys.executable, '-m', 'pytest', 'tests/test_jobs_contract.py', '-q'], Path('.'))
        add([sys.executable, '-m', 'pytest', 'tests/test_config_contract.py', '-q'], Path('.'))
        add([sys.executable, '-m', 'compileall', 'src', 'tests', 'examples'], Path('.'))
        add(['npm', 'run', 'build'], Path('frontend'))
        return commands

    if flags['api_contract'] or flags['storage']:
        add([sys.executable, '-m', 'pytest', 'tests/test_api_contract.py', '-q'], Path('.'))

    if flags['jobs']:
        add([sys.executable, '-m', 'pytest', 'tests/test_jobs_contract.py', '-q'], Path('.'))

    if flags['config']:
        add([sys.executable, '-m', 'pytest', 'tests/test_config_contract.py', '-q'], Path('.'))

    if flags['api_contract'] or flags['storage'] or flags['config'] or flags['jobs']:
        add([sys.executable, '-m', 'compileall', 'src', 'tests', 'examples'], Path('.'))

    if flags['frontend_api']:
        add(['npm', 'run', 'build'], Path('frontend'))

    return commands


def run_commands(commands: List[Tuple[List[str], Path]]) -> int:
    for cmd, cwd in commands:
        printable = ' '.join(cmd)
        print(f'\\n[run] ({cwd}) {printable}')
        result = subprocess.run(cmd, cwd=cwd)
        if result.returncode != 0:
            print(f'[fail] exit code {result.returncode}: {printable}')
            return result.returncode
        print(f'[ok] {printable}')
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Recommend or run contract checks based on changed files.')
    parser.add_argument('--changed', nargs='*', default=[], help='Changed file paths relative to repository root.')
    parser.add_argument('--run', action='store_true', help='Execute the recommended commands in order.')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    changed = [p for p in args.changed if p.strip()]
    flags = classify_paths(changed)
    commands = recommend_commands(flags, changed)

    print('Changed files:')
    if changed:
        for path in changed:
            print(f'- {path}')
    else:
        print('- (none provided; using broad fallback checks)')

    print('\\nRecommended commands:')
    if not commands:
        print('- No checks recommended from provided paths.')
        print('  Run at least: python -m pytest tests/test_api_contract.py -q')
        return 0

    for cmd, cwd in commands:
        print(f"- ({cwd}) {' '.join(cmd)}")

    if not args.run:
        print('\\nDry run complete. Add --run to execute these commands.')
        return 0

    return run_commands(commands)


if __name__ == '__main__':
    raise SystemExit(main())