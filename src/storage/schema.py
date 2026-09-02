"""Schema-version checks shared by API and worker startup."""
from __future__ import annotations

from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Engine


ROOT = Path(__file__).resolve().parents[2]


class SchemaVersionError(RuntimeError):
    pass


# Alembic revision alone is insufficient for databases adopted with a manual
# stamp. Compare every ORM table/column at validation-only startup; limiting
# this to the old runtime-DDL columns would let unrelated drift pass at head.
def _expected_schema_columns() -> dict[str, set[str]]:
    # Imported lazily to keep Alembic/config imports free of avoidable cycles.
    from src.storage.content_store import Base

    return {
        table_name: {column.name for column in table.columns}
        for table_name, table in Base.metadata.tables.items()
    }

# A database can be stamped manually at head while still missing constraints or
# indexes. Validate the correctness-critical event invariant and the indexes
# that pre-Alembic ``create_all`` installations could not add retroactively.
REQUIRED_SCHEMA_INDEXES: dict[str, set[tuple[str, ...]]] = {
    "agent_threads": {
        ("updated_at",),
        ("pinned", "updated_at"),
        ("archived",),
    },
    # Capability lookup and expiry sweeps must stay indexed: an unindexed
    # status/expiry scan would make the fail-closed path slow enough to be
    # skipped under load.
    "proposed_actions": {
        ("thread_id", "created_at"),
        ("status", "expires_at"),
    },
    "idempotency_records": {
        ("scope", "created_at"),
    },
}
# Duplicate-write prevention must be enforced by PostgreSQL, not by application
# check-then-write: without the unique constraint two racing claims both see no
# row and both proceed.
REQUIRED_UNIQUE_CONSTRAINTS: dict[str, set[tuple[str, ...]]] = {
    "agent_run_events": {("run_id", "seq")},
    "idempotency_records": {("scope", "idempotency_key")},
}


def alembic_config(database_url: str | None = None) -> AlembicConfig:
    cfg = AlembicConfig(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    if database_url:
        cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return cfg


def assert_schema_current(engine: Engine) -> None:
    cfg = alembic_config()
    expected = ScriptDirectory.from_config(cfg).get_current_head()
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
        if current != expected:
            raise SchemaVersionError(
                f"Database schema revision is {current or 'unversioned'}; expected {expected}. "
                "Run `alembic upgrade head` before starting the API or worker."
            )

        inspector = inspect(connection)
        drift: list[str] = []
        table_names = set(inspector.get_table_names())
        for table, required_columns in _expected_schema_columns().items():
            if table not in table_names:
                drift.append(f"missing table {table}")
                continue
            actual = {column["name"] for column in inspector.get_columns(table)}
            missing = sorted(required_columns - actual)
            if missing:
                drift.append(f"{table} missing columns {', '.join(missing)}")

        for table, required_indexes in REQUIRED_SCHEMA_INDEXES.items():
            if table not in table_names:
                continue
            actual_indexes = {
                tuple(index.get("column_names") or [])
                for index in inspector.get_indexes(table)
            }
            missing_indexes = sorted(required_indexes - actual_indexes)
            if missing_indexes:
                rendered = ", ".join("(" + ", ".join(columns) + ")" for columns in missing_indexes)
                drift.append(f"{table} missing indexes {rendered}")

        for table, required_constraints in REQUIRED_UNIQUE_CONSTRAINTS.items():
            if table not in table_names:
                continue
            actual_constraints = {
                tuple(constraint.get("column_names") or [])
                for constraint in inspector.get_unique_constraints(table)
            }
            missing_constraints = sorted(required_constraints - actual_constraints)
            if missing_constraints:
                rendered = ", ".join("(" + ", ".join(columns) + ")" for columns in missing_constraints)
                drift.append(f"{table} missing unique constraints {rendered}")

        # Revision stamps and name-only checks cannot detect a narrowed type,
        # dropped NOT NULL, or missing foreign key. Use Alembic's same metadata
        # comparator as `alembic check` at validation-only startup. This is a
        # startup cost, not a per-request operation.
        if not drift:
            from src.storage.content_store import Base

            comparison_context = MigrationContext.configure(
                connection,
                opts={"compare_type": True, "compare_server_default": False},
            )
            metadata_diffs = compare_metadata(comparison_context, Base.metadata)
            if metadata_diffs:
                preview = "; ".join(repr(item) for item in metadata_diffs[:5])
                if len(metadata_diffs) > 5:
                    preview += f"; ... ({len(metadata_diffs)} differences total)"
                drift.append(f"ORM metadata mismatch: {preview}")
        if drift:
            raise SchemaVersionError(
                "Database schema is stamped at head but has schema drift: "
                + "; ".join(drift)
                + ". Restore from backup or run the documented legacy normalization workflow."
            )
