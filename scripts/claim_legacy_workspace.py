"""Explicitly claim pre-account data; public registration never adopts legacy records."""

from __future__ import annotations

import argparse
import shutil
import sys
from getpass import getpass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.api.passwords import hash_password, normalize_username
from src.storage.content_store import ContentStore, User
from src.storage.schema import assert_schema_current
from src.storage.tenancy import LEGACY_USER_ID
from src.utils import config


def claim_workspace(store: ContentStore, username: str, password: str, memory_root: Path) -> None:
    username = normalize_username(username)
    password_hash = hash_password(password)
    with store._get_session() as session:
        legacy = session.query(User).filter(User.id == LEGACY_USER_ID).with_for_update().first()
        if legacy is None or legacy.is_active:
            raise ValueError("没有待认领的迁移工作区；已认领的账号密码不会被覆盖")
        if session.query(User.id).filter(User.username == username, User.id != LEGACY_USER_ID).first():
            raise ValueError("用户名已被使用，请选择另一个名称")

        # Copy, do not remove, old files. A failed DB commit can be retried when
        # the copied bytes match; existing per-user notes are never overwritten.
        destination = memory_root / LEGACY_USER_ID
        for name in ("MEMORY.md", "USER.md"):
            source = memory_root / name
            target = destination / name
            if not source.is_file():
                continue
            if target.exists():
                if not target.is_file() or target.read_bytes() != source.read_bytes():
                    raise ValueError("迁移目标已有不同记忆内容，请先备份并检查")
            else:
                destination.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        legacy.username = username
        legacy.password_hash = password_hash
        legacy.is_active = True
        session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    args = parser.parse_args()
    normalize_username(args.username)
    password = getpass("设置迁移账号密码（12–128 字符）: ")
    if password != getpass("再次输入密码: "):
        raise SystemExit("两次密码输入不一致")
    store = ContentStore(initialize_schema=False)
    try:
        assert_schema_current(store.engine)
        claim_workspace(store, args.username, password, Path(config.MEMORY_DIR))
        print("工作区已认领。请使用该用户名和密码登录；原根目录记忆文件保留为备份。")
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    finally:
        store.engine.dispose()


if __name__ == "__main__":
    main()
