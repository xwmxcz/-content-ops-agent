from alembic import command
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect, text

from src.storage.content_store import Base
from src.storage.schema import SchemaVersionError, alembic_config, assert_schema_current


def test_alembic_upgrades_empty_postgres_to_current_schema(pg_engine):
    Base.metadata.drop_all(pg_engine)
    with pg_engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))

    cfg = alembic_config(pg_engine.url.render_as_string(hide_password=False))
    try:
        command.upgrade(cfg, "head")
        inspector = inspect(pg_engine)
        assert set(Base.metadata.tables) <= set(inspector.get_table_names())
        assert "next_event_seq" in {
            column["name"] for column in inspector.get_columns("agent_runs")
        }
        constraints = inspector.get_unique_constraints("agent_run_events")
        assert any(item.get("name") == "uq_agent_run_events_run_seq" for item in constraints)
        action_indexes = {
            tuple(index.get("column_names") or [])
            for index in inspector.get_indexes("proposed_actions")
        }
        assert {("thread_id", "created_at"), ("status", "expires_at")} <= action_indexes
        # The ledger's uniqueness is what makes duplicate keyed writes impossible
        # at the database level rather than merely unlikely in application code.
        ledger_constraints = inspector.get_unique_constraints("idempotency_records")
        assert any(
            item.get("name") == "uq_idempotency_records_scope_key"
            and tuple(item.get("column_names") or []) == ("scope", "idempotency_key")
            for item in ledger_constraints
        )
        ledger_indexes = {
            tuple(index.get("column_names") or [])
            for index in inspector.get_indexes("idempotency_records")
        }
        assert ("scope", "created_at") in ledger_indexes
        with pg_engine.connect() as connection:
            assert MigrationContext.configure(connection).get_current_revision() == "0006_job_retry_fields"
        assert_schema_current(pg_engine)
        # Metadata and the migration head must remain in sync; otherwise a
        # fresh production database can pass revision validation while missing
        # a newly declared model change.
        command.check(cfg)
    finally:
        command.downgrade(cfg, "base")
        with pg_engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS alembic_version"))


def test_legacy_stamped_schema_receives_missing_runtime_ddl_columns(pg_engine):
    Base.metadata.drop_all(pg_engine)
    with pg_engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    cfg = alembic_config(pg_engine.url.render_as_string(hide_password=False))
    try:
        command.upgrade(cfg, "0001_baseline")
        with pg_engine.begin() as connection:
            connection.execute(text("ALTER TABLE agent_messages DROP COLUMN intent"))
            connection.execute(text("ALTER TABLE agent_messages DROP COLUMN plan"))
            connection.execute(text("ALTER TABLE agent_threads DROP COLUMN pinned"))
            connection.execute(text("ALTER TABLE agent_threads DROP COLUMN archived"))
            connection.execute(text("ALTER TABLE agent_threads DROP COLUMN title_pinned"))
            connection.execute(text("ALTER TABLE jobs DROP COLUMN token_usage"))
            connection.execute(text("ALTER TABLE jobs DROP COLUMN cost_estimate"))
            # Recreate the operational pre-Alembic state: application tables
            # exist but no revision table does. Adoption must explicitly stamp
            # the reviewed baseline before running later migrations.
            connection.execute(text("DROP TABLE alembic_version"))
        with pg_engine.connect() as connection:
            assert MigrationContext.configure(connection).get_current_revision() is None
        command.stamp(cfg, "0001_baseline")
        with pg_engine.connect() as connection:
            assert MigrationContext.configure(connection).get_current_revision() == "0001_baseline"
        command.upgrade(cfg, "head")
        inspector = inspect(pg_engine)
        assert {"intent", "plan"} <= {
            column["name"] for column in inspector.get_columns("agent_messages")
        }
        assert {"pinned", "archived", "title_pinned"} <= {
            column["name"] for column in inspector.get_columns("agent_threads")
        }
        assert {"token_usage", "cost_estimate"} <= {
            column["name"] for column in inspector.get_columns("jobs")
        }
        thread_indexes = {
            tuple(index.get("column_names") or [])
            for index in inspector.get_indexes("agent_threads")
        }
        assert {("updated_at",), ("pinned", "updated_at"), ("archived",)} <= thread_indexes
        assert_schema_current(pg_engine)
    finally:
        command.downgrade(cfg, "base")
        with pg_engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS alembic_version"))


def test_head_revision_with_type_nullability_and_fk_drift_fails_validation(pg_engine):
    Base.metadata.drop_all(pg_engine)
    with pg_engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    cfg = alembic_config(pg_engine.url.render_as_string(hide_password=False))
    try:
        command.upgrade(cfg, "head")
        with pg_engine.begin() as connection:
            connection.execute(text(
                "ALTER TABLE contents ALTER COLUMN content TYPE VARCHAR(5)"
            ))
            connection.execute(text(
                "ALTER TABLE contents ALTER COLUMN content DROP NOT NULL"
            ))
            connection.execute(text(
                "ALTER TABLE calendar_events "
                "DROP CONSTRAINT calendar_events_content_id_fkey"
            ))
        try:
            assert_schema_current(pg_engine)
        except SchemaVersionError as exc:
            message = str(exc)
            assert "ORM metadata mismatch" in message
            assert "content" in message
            assert "calendar_events" in message
        else:
            raise AssertionError("type/nullability/foreign-key drift was not detected")
    finally:
        command.downgrade(cfg, "base")
        with pg_engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS alembic_version"))


def test_head_revision_with_schema_drift_fails_validation(pg_engine):
    Base.metadata.drop_all(pg_engine)
    with pg_engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    cfg = alembic_config(pg_engine.url.render_as_string(hide_password=False))
    try:
        command.upgrade(cfg, "head")
        with pg_engine.begin() as connection:
            connection.execute(text("ALTER TABLE agent_messages DROP COLUMN intent"))
            # Drift validation covers the complete ORM shape, not only columns
            # historically managed by startup-time ALTER statements.
            connection.execute(text("ALTER TABLE contents DROP COLUMN style"))
            connection.execute(text(
                "ALTER TABLE agent_run_events "
                "DROP CONSTRAINT uq_agent_run_events_run_seq"
            ))
        try:
            assert_schema_current(pg_engine)
        except SchemaVersionError as exc:
            assert "schema drift" in str(exc)
            assert "agent_messages missing columns intent" in str(exc)
            assert "contents missing columns style" in str(exc)
            assert "agent_run_events missing unique constraints (run_id, seq)" in str(exc)
            # Restore the deliberately removed invariant so Alembic's normal
            # downgrade can exercise its own drop operation in ``finally``.
            with pg_engine.begin() as connection:
                connection.execute(text(
                    "ALTER TABLE agent_run_events ADD CONSTRAINT "
                    "uq_agent_run_events_run_seq UNIQUE (run_id, seq)"
                ))
        else:
            raise AssertionError("schema drift was not detected")
    finally:
        command.downgrade(cfg, "base")
        with pg_engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
