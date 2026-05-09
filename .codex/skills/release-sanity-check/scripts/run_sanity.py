#!/usr/bin/env python3
"""Run repository sanity checks in a fixed order and print a concise report."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


Command = Tuple[str, List[str], Path]


def find_repo_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / 'frontend' / 'package.json').exists() and (candidate / 'tests').exists():
            return candidate
    raise RuntimeError('Could not locate repository root')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run sanity checks for content-ops-agent.')
    parser.add_argument('--continue-on-error', action='store_true', help='Run all stages and collect failures.')
    parser.add_argument('--skip-frontend', action='store_true', help='Skip npm run build stage.')
    parser.add_argument('--python', dest='python_exe', default=sys.executable, help='Python executable path.')
    return parser.parse_args()


def build_stages(repo_root: Path, python_exe: str, skip_frontend: bool) -> List[Command]:
    stages: List[Command] = [
        ('backend-tests', [python_exe, '-m', 'pytest', 'tests', '-q'], repo_root),
        ('compileall', [python_exe, '-m', 'compileall', 'src', 'tests', 'examples'], repo_root),
    ]
    if not skip_frontend:
        stages.append(('frontend-build', ['npm', 'run', 'build'], repo_root / 'frontend'))
    return stages


def run_stage(name: str, command: List[str], cwd: Path) -> int:
    print(f'\\n[stage] {name}')
    print(f"[cmd] ({cwd}) {' '.join(command)}")
    result = subprocess.run(command, cwd=cwd)
    return result.returncode


def main() -> int:
    args = parse_args()
    script_path = Path(__file__).resolve()
    repo_root = find_repo_root(script_path)

    stages = build_stages(repo_root, args.python_exe, args.skip_frontend)
    failures: List[Tuple[str, int]] = []

    print('Sanity check plan:')
    for name, command, cwd in stages:
        print(f"- {name}: ({cwd}) {' '.join(command)}")

    for name, command, cwd in stages:
        code = run_stage(name, command, cwd)
        if code != 0:
            print(f'[fail] {name} (exit {code})')
            failures.append((name, code))
            if not args.continue_on_error:
                break
        else:
            print(f'[ok] {name}')

    print('\\nSummary:')
    for name, _, _ in stages:
        matched = next((f for f in failures if f[0] == name), None)
        if matched:
            print(f'- {name}: fail (exit {matched[1]})')
        else:
            print(f'- {name}: pass')

    if failures:
        print('- final: not ready')
        first = failures[0]
        print(f'- first failing stage: {first[0]} (exit {first[1]})')
        return 1

    print('- final: ready')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())