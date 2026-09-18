#!/usr/bin/env python3
"""Fallback for `make <target>` when GNU Make is not installed.

GNU Make is standard on macOS and Linux, and CI uses it. On Windows it is not
part of Git for Windows and is not always on PATH, so this script provides the
same targets without it. It shells out to the identical commands the Makefile
uses, so the two cannot drift.

Usage:
    python scripts/dev.py <target> [target ...]
    python scripts/dev.py              # list targets

Targets mirror the Makefile: install, lock, lint, format, typecheck, test,
test-db, test-frontend, check, audit, db-up, db-down.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://content_ops:content_ops@127.0.0.1:55432/content_ops_test"
TEST_CONTAINER = "content-ops-test-pg"


def _run(*command: str, env: dict[str, str] | None = None, cwd: Path | None = None) -> None:
    merged = dict(os.environ)
    if env:
        merged.update(env)
    print(f"+ {' '.join(command)}", flush=True)
    result = subprocess.run(command, cwd=cwd or ROOT, env=merged, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def _python() -> str:
    return sys.executable


def _npx(*args: str) -> None:
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if npx is None:
        raise SystemExit("npx not found; install Node.js 20+ first.")
    _run(npx, *args, cwd=ROOT / "frontend")


def install() -> None:
    """Backend dev deps plus npm ci."""
    _run(_python(), "-m", "pip", "install", "-r", "requirements-dev.txt")
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if npm is None:
        raise SystemExit("npm not found; install Node.js 20+ first.")
    _run(npm, "ci", cwd=ROOT / "frontend")


def lock() -> None:
    """Re-resolve requirements.lock (cross-platform, py>=3.11)."""
    _run(
        "uv",
        "pip",
        "compile",
        "--universal",
        "--python-version",
        "3.11",
        "-o",
        "requirements.lock",
        "requirements.txt",
    )


def lint() -> None:
    """ruff check plus ruff format --check."""
    _run("ruff", "check", ".")
    _run("ruff", "format", "--check", ".")


def format_code() -> None:
    """Apply ruff fixes and formatting."""
    _run("ruff", "check", ".", "--fix")
    _run("ruff", "format", ".")


def typecheck() -> None:
    """mypy over src/."""
    _run("mypy")


def test() -> None:
    """Fast unit tests; database-backed tests skip."""
    _run(_python(), "-m", "pytest", "-q")


def test_db() -> None:
    """Full suite against PostgreSQL; silent DB skips are fatal."""
    _run(
        _python(),
        "-m",
        "pytest",
        "-q",
        env={
            "TEST_DATABASE_URL": os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL),
            "REQUIRE_TEST_DATABASE": "1",
        },
    )


def test_frontend() -> None:
    """vue-tsc typecheck plus vitest."""
    _npx("vue-tsc", "--noEmit")
    _npx("vitest", "run")


def check() -> None:
    """Everything CI enforces: lint, typecheck, tests, frontend."""
    lint()
    typecheck()
    test_db()
    test_frontend()


def audit() -> None:
    """pip-audit plus npm audit."""
    _run("pip-audit", "-r", "requirements.lock")
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if npm is None:
        raise SystemExit("npm not found; install Node.js 20+ first.")
    _run(npm, "audit", "--audit-level=high", cwd=ROOT / "frontend")


def db_up() -> None:
    """Start the throwaway test PostgreSQL on :55432 (idempotent)."""
    docker = shutil.which("docker")
    if docker is None:
        raise SystemExit("docker not found; install Docker Desktop first.")
    # Idempotent: reuse an existing container rather than failing on the name.
    existing = subprocess.run(
        [docker, "ps", "-a", "--filter", f"name=^{TEST_CONTAINER}$", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if existing:
        _run(docker, "start", TEST_CONTAINER)
        return
    _run(
        docker,
        "run",
        "-d",
        "--name",
        TEST_CONTAINER,
        "-e",
        "POSTGRES_USER=content_ops",
        "-e",
        "POSTGRES_PASSWORD=content_ops",
        "-e",
        "POSTGRES_DB=content_ops_test",
        "-p",
        "55432:5432",
        "postgres:16-alpine",
    )


def db_down() -> None:
    """Remove the throwaway test PostgreSQL container."""
    docker = shutil.which("docker")
    if docker is None:
        raise SystemExit("docker not found; install Docker Desktop first.")
    _run(docker, "rm", "-f", TEST_CONTAINER)


TARGETS = {
    "install": install,
    "lock": lock,
    "lint": lint,
    "format": format_code,
    "typecheck": typecheck,
    "test": test,
    "test-db": test_db,
    "test-frontend": test_frontend,
    "check": check,
    "audit": audit,
    "db-up": db_up,
    "db-down": db_down,
}


def main(argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help", "list"}:
        print(__doc__)
        print("Available targets:")
        for name, fn in TARGETS.items():
            summary = (fn.__doc__ or "").strip().splitlines()[0] if fn.__doc__ else ""
            print(f"  {name:<14} {summary}")
        return 0
    for target in argv:
        if target not in TARGETS:
            print(f"Unknown target: {target}", file=sys.stderr)
            print(f"Known targets: {', '.join(TARGETS)}", file=sys.stderr)
            return 2
        TARGETS[target]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
