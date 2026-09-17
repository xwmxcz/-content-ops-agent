"""Own password hashing and credential validation for registration and migration."""

from __future__ import annotations

import re

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, type=Type.ID)


def normalize_username(value: str) -> str:
    username = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9_]{3,32}", username):
        raise ValueError("用户名需为 3–32 位字母、数字或下划线")
    return username


def validate_password(value: str) -> str:
    if not 12 <= len(value) <= 128 or not value.strip() or "\x00" in value:
        raise ValueError("密码长度需为 12–128 个字符，且应包含非空白字符")
    return value


def hash_password(password: str) -> str:
    return _hasher.hash(validate_password(password))


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


# Unknown usernames still incur the same password hashing work as known ones.
DUMMY_PASSWORD_HASH = _hasher.hash("content-ops-invalid-login-placeholder")
