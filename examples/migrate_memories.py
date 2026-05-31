"""One-shot migration from the legacy `agent_memories` SQL table to the new
Hermes-style MEMORY.md / USER.md files.

Run once after upgrading to the file-based memory system:

    python examples/migrate_memories.py [--db data/content_ops.db]
                                        [--memory-dir data/memory]
                                        [--dry-run]

Behavior:

- Reads all rows from `agent_memories`, ordered by importance DESC, updated_at DESC.
- Bucketing: `preference` → USER.md, everything else → MEMORY.md.
- Skips entries that would push a file over its char limit and writes them to
  `data/memory/_overflow_<timestamp>.md` for human review.
- Does NOT drop the `agent_memories` table — that happens automatically once
  you redeploy with the new content_store (the ORM model is removed in the
  same release). Run this script BEFORE that deploy.
- Does NOT touch any ChromaDB directory; delete `data/chroma/` yourself when
  you're confident the migration succeeded.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Iterable

# Make `python examples/migrate_memories.py` work without `pip install -e .`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text

from src.storage.file_memory import AGENT, FileMemory, USER


PREFERENCE_CATEGORIES = {"preference"}


def _fetch_legacy_rows(db_url: str) -> list[dict]:
    engine = create_engine(db_url, echo=False)
    with engine.connect() as conn:
        try:
            rows = conn.execute(text(
                "SELECT id, content, category, importance, updated_at "
                "FROM agent_memories "
                "ORDER BY importance DESC, updated_at DESC"
            )).all()
        except Exception as exc:
            print(f"No agent_memories table found (or unreadable): {exc}", file=sys.stderr)
            return []
    return [
        {"id": r[0], "content": r[1] or "", "category": (r[2] or "fact").lower(),
         "importance": r[3] or 0.0, "updated_at": r[4]}
        for r in rows
    ]


def _bucket(rows: Iterable[dict]) -> tuple[list[dict], list[dict]]:
    user_rows, agent_rows = [], []
    for row in rows:
        if row["category"] in PREFERENCE_CATEGORIES:
            user_rows.append(row)
        else:
            agent_rows.append(row)
    return agent_rows, user_rows


def _pack(rows: list[dict], limit: int) -> tuple[str, list[dict]]:
    kept_chunks: list[str] = []
    overflow: list[dict] = []
    delim = "\n§\n"
    trailing = "\n"
    for row in rows:
        entry = (row["content"] or "").strip()
        if not entry:
            continue
        proposed_chunks = kept_chunks + [entry]
        proposed_body = delim.join(proposed_chunks) + trailing
        if len(proposed_body) > limit:
            overflow.append(row)
            continue
        kept_chunks = proposed_chunks
    body = delim.join(kept_chunks) + trailing if kept_chunks else ""
    return body, overflow


def _write_overflow(memory_dir: Path, overflow: list[dict]) -> Path | None:
    if not overflow:
        return None
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = memory_dir / f"_overflow_{stamp}.md"
    lines = [
        "# Overflow entries from agent_memories migration",
        "# These did not fit the MEMORY.md / USER.md char limits.",
        "# Review, edit, and paste into the right file by hand.",
        "",
    ]
    for row in overflow:
        lines.append(f"## id={row['id']}  category={row['category']}  importance={row['importance']}")
        lines.append(row["content"].strip())
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="sqlite:///data/content_ops.db",
                        help="SQLAlchemy URL of the legacy DB (default sqlite:///data/content_ops.db)")
    parser.add_argument("--memory-dir", default="data/memory",
                        help="Target directory for MEMORY.md / USER.md (default data/memory)")
    parser.add_argument("--memory-limit", type=int, default=2200)
    parser.add_argument("--user-limit", type=int, default=1375)
    parser.add_argument("--dry-run", action="store_true", help="Print the plan, do not write files")
    args = parser.parse_args()

    db_url = args.db if "://" in args.db else f"sqlite:///{args.db}"
    memory_dir = Path(args.memory_dir)

    rows = _fetch_legacy_rows(db_url)
    print(f"Found {len(rows)} legacy memory rows in {db_url}")
    if not rows:
        print("Nothing to migrate.")
        return 0

    agent_rows, user_rows = _bucket(rows)
    print(f"  → MEMORY.md candidates: {len(agent_rows)}")
    print(f"  → USER.md   candidates: {len(user_rows)}")

    memory_body, memory_overflow = _pack(agent_rows, args.memory_limit)
    user_body, user_overflow = _pack(user_rows, args.user_limit)

    print(f"MEMORY.md packed: {len(memory_body)}/{args.memory_limit} chars, overflow {len(memory_overflow)}")
    print(f"USER.md   packed: {len(user_body)}/{args.user_limit} chars, overflow {len(user_overflow)}")

    if args.dry_run:
        print("Dry run — no files written.")
        return 0

    fm = FileMemory(memory_dir, memory_limit=args.memory_limit, user_limit=args.user_limit)
    fm.save(AGENT, memory_body)
    fm.save(USER, user_body)
    overflow_path = _write_overflow(memory_dir, memory_overflow + user_overflow)
    print(f"Wrote {fm.memory_path}")
    print(f"Wrote {fm.user_path}")
    if overflow_path:
        print(f"Overflow → {overflow_path} (review and merge manually)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
