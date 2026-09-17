#!/usr/bin/env python3
"""Validate account-runtime profiles in isolated subprocesses without a database."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REMOVED_AUTH_SETTINGS = (
    "AUTH_ENABLED",
    "AUTH_USERNAME",
    "AUTH_PASSWORD",
    "AUTH_STREAM_TICKET_SECONDS",
)
BASE_ENV = {
    "PYTHON_DOTENV_DISABLED": "1",
    "APP_ENV": "production",
    "SCHEMA_MANAGEMENT": "validate",
    "AUTH_SECRET_KEY": "f8Jt5Vc3Zw9Hx1Qr7Kn4Sm2Py6Lb0DaE",
    "DATABASE_URL": "postgresql+psycopg://user:B7xD9nL2aV6qR4sW@localhost/db",
    "REDIS_URL": "redis://:K3rV8aC4qJ9wT2dM@localhost:6379/0",
    "JOB_QUEUE_MODE": "rq",
    "DEBUG": "false",
    "API_RELOAD": "false",
    "ENFORCE_HTTPS": "true",
    "CORS_ORIGINS": "https://content.example.com",
    "TRUSTED_PROXY_CIDRS": "",
}
CASES = [
    ("accept production", {}, None),
    ("reject missing signing key", {"AUTH_SECRET_KEY": ""}, "AUTH_SECRET_KEY"),
    ("reject short signing key", {"AUTH_SECRET_KEY": "short"}, "high-entropy AUTH_SECRET_KEY"),
    ("reject repeated signing key", {"AUTH_SECRET_KEY": "A" * 40}, "high-entropy AUTH_SECRET_KEY"),
    (
        "reject placeholder signing key",
        {"AUTH_SECRET_KEY": "CHANGE_ME_WITH_32_RANDOM_CHARACTERS"},
        "high-entropy AUTH_SECRET_KEY",
    ),
    ("reject debug", {"DEBUG": "true"}, "DEBUG=false"),
    ("reject HTTP", {"ENFORCE_HTTPS": "false"}, "ENFORCE_HTTPS=true"),
    ("reject HTTP CORS", {"CORS_ORIGINS": "http://example.com"}, "CORS_ORIGINS"),
    ("reject weak database secret", {"DATABASE_URL": "postgresql+psycopg://user:dev@localhost/db"}, "DATABASE_URL"),
    ("reject weak Redis secret", {"REDIS_URL": "redis://:dev@localhost:6379/0"}, "REDIS_URL"),
    (
        "reject shared signing/database secret",
        {"DATABASE_URL": "postgresql+psycopg://user:" + BASE_ENV["AUTH_SECRET_KEY"] + "@localhost/db"},
        "must be distinct",
    ),
    ("accept development", {"APP_ENV": "development", "SCHEMA_MANAGEMENT": "create", "AUTH_SECRET_KEY": "dev"}, None),
    ("accept test", {"APP_ENV": "test", "SCHEMA_MANAGEMENT": "create", "AUTH_SECRET_KEY": "test"}, None),
    (
        "reject development missing key",
        {"APP_ENV": "development", "AUTH_SECRET_KEY": ""},
        "AUTH_SECRET_KEY is required",
    ),
    ("reject test missing key", {"APP_ENV": "test", "AUTH_SECRET_KEY": " "}, "AUTH_SECRET_KEY is required"),
    *[("reject removed " + name, {name: ""}, "migration required") for name in REMOVED_AUTH_SETTINGS],
]


def verify_case(overrides, expected_error):
    env = dict(os.environ)
    for name in REMOVED_AUTH_SETTINGS:
        env.pop(name, None)
    env.update(BASE_ENV)
    env.update(overrides)
    result = subprocess.run(
        [sys.executable, "-c", "from src.utils import config; config.validate_runtime()"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if expected_error:
        assert result.returncode != 0, "Unsafe configuration unexpectedly passed"
        assert expected_error in result.stderr, result.stderr
    else:
        assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("name,overrides,expected_error", CASES, ids=[case[0] for case in CASES])
def test_runtime_profile(name, overrides, expected_error):
    verify_case(overrides, expected_error)


def main():
    for name, overrides, expected_error in CASES:
        verify_case(overrides, expected_error)
        print("PASS: " + name)
    print(f"{len(CASES)}/{len(CASES)} runtime configuration checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
