"""Regression checks for the shared ORM workspace boundary and linked writes."""
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.orm import aliased

from src.models import ContentType, GeneratedContent
from src.storage.content_store import (
    AgentMessage, AgentRun, AgentRunEvent, AgentThread, CalendarEvent, Content,
    ContentMetrics, ContentStore, IdempotencyRecord, Job, MediaAsset,
    PlatformPublication, ProposedAction, RunStep, User,
)
from src.storage.tenancy import TenantAccessError


@pytest.fixture
def workspaces(store):
    system = ContentStore(database_url=store.database_url, initialize_schema=False)
    with system._get_session() as session:
        session.add_all([
            User(id="a" * 32, username="storage_owner_a", password_hash="!"),
            User(id="b" * 32, username="storage_owner_b", password_hash="!"),
        ])
        session.commit()
    try:
        yield system, system.for_user("a" * 32), system.for_user("b" * 32)
    finally:
        system.engine.dispose()


def _content(store, title="Private content"):
    return store.save_content(GeneratedContent(
        title=title, content="private body", content_type=ContentType.BLOG,
    ))


def test_client_named_thread_can_only_be_created_or_updated_by_its_owner(workspaces):
    _, alice, bob = workspaces
    alice.upsert_agent_thread("client_chosen_thread", title="Private A")
    with pytest.raises(TenantAccessError):
        bob.upsert_agent_thread("client_chosen_thread", title="Intrusion")
    assert alice.get_agent_thread("client_chosen_thread")["title"] == "Private A"
    assert bob.get_agent_thread("client_chosen_thread") is None
    bob.upsert_agent_thread("bob_new_thread", title="Private B")
    assert bob.get_agent_thread("bob_new_thread")["title"] == "Private B"


def _seed_workspace(store, suffix):
    content_id = _content(store, suffix)
    store.save_calendar_event(content_id, "blog", date.today())
    message_id = store.save_agent_message(f"thread_{suffix}", "user", "private message")
    store.create_run(f"run_{suffix}", "private", "blog", "casual", thread_id=f"thread_{suffix}")
    store.append_run_event(f"run_{suffix}", "progress", {"private": suffix})
    store.save_run_step_checkpoint(f"run_{suffix}", 1, "writer")
    store.create_job(f"job_{suffix}", "content_generation", {"private": suffix})
    store.claim_idempotency_key(scope="create", key="same-key", args={"private": suffix})
    with store._get_session() as session:
        session.add_all([
            ContentMetrics(content_id=content_id, views=100),
            MediaAsset(content_id=content_id, media_type="image", source_type="upload",
                       file_name="private.png", file_path=f"private/{suffix}.png"),
            PlatformPublication(content_id=content_id, platform="blog", publish_type="draft", body="private"),
            ProposedAction(id=f"action_{suffix}", thread_id=f"thread_{suffix}",
                           proposing_message_id=message_id, tool_name="create_content", args_json="{}",
                           args_hash="f" * 64, impact_summary="private", expires_at=datetime.now() + timedelta(minutes=1)),
        ])
        session.commit()
    return content_id, message_id


def test_all_business_tables_and_scalar_aggregates_are_scoped(workspaces):
    system, first, second = workspaces
    first_id, _ = _seed_workspace(first, "first")
    second_id, _ = _seed_workspace(second, "second")
    models = (Content, CalendarEvent, ContentMetrics, MediaAsset, PlatformPublication,
              AgentThread, AgentMessage, Job, RunStep, AgentRun, AgentRunEvent,
              ProposedAction, IdempotencyRecord)
    with first._get_session() as session, system._get_session() as maintenance:
        for model in models:
            assert session.query(model).count() == 1
            assert session.query(model).filter(model.user_id == second.user_id).count() == 0
            assert maintenance.query(model).count() == 2
        assert session.scalar(select(func.count(Content.id))) == 1
        assert session.get(Content, second_id) is None
        assert session.get(Content, first_id).user_id == first.user_id
        alias = aliased(Content)
        assert session.scalars(select(alias.id)).all() == [first_id]
    assert first.get_content_stats()["total_contents"] == 1
    assert first.aggregate_performance()["total_contents"] == 1
    assert len(first.search_contents("private")) == 1
    assert first.get_content(second_id) is None


def test_inner_outer_joins_and_column_queries_keep_both_sides_scoped(workspaces):
    _, first, second = workspaces
    first_id, _ = _seed_workspace(first, "first")
    _seed_workspace(second, "second")
    assert [item["content_id"] for item in first.get_calendar_events()] == [first_id]
    threads = first.list_agent_threads()
    assert len(threads) == 1
    assert threads[0]["id"] == "thread_first"
    assert threads[0]["message_count"] == 1
    with first._get_session() as session:
        left, right = aliased(Content), aliased(Content)
        rows = session.execute(select(left.id, right.id).join(right, left.id == right.id)).all()
        assert rows == [(first_id, first_id)]


def test_bulk_updates_deletes_and_lease_claims_cannot_cross_users(workspaces):
    _, first, second = workspaces
    first_id = _content(first)
    second_id = _content(second)
    second.create_job("job_second", "generate", {})
    assert first.acquire_job_lease("job_second", "worker-first", 300) is False
    with first._get_session() as session:
        assert session.query(Content).update({Content.status: "archived"}) == 1
        session.commit()
    assert first.get_content(first_id)["status"] == "archived"
    assert second.get_content(second_id)["status"] == "draft"
    with first._get_session() as session:
        assert session.execute(update(Content).values(style="professional")).rowcount == 1
        assert session.execute(delete(Content).where(Content.id == second_id)).rowcount == 0
        session.commit()
    assert first.get_content(first_id)["style"] == "professional"
    assert second.get_content(second_id)["style"] == "casual"
    with first._get_session() as session:
        assert session.query(Content).delete(synchronize_session=False) == 1
        session.commit()
    assert second.get_content(second_id) is not None


@pytest.mark.parametrize("factory", [
    lambda cid, mid: Content(content="x", content_type="blog", style="casual", parent_id=cid),
    lambda cid, mid: CalendarEvent(content_id=cid, platform="blog", scheduled_date=date.today()),
    lambda cid, mid: ContentMetrics(content_id=cid),
    lambda cid, mid: MediaAsset(content_id=cid, media_type="image", source_type="upload", file_name="x", file_path="x"),
    lambda cid, mid: PlatformPublication(content_id=cid, platform="blog", publish_type="draft", body="x"),
    lambda cid, mid: AgentMessage(thread_id="thread_second", role="user", content="x"),
    lambda cid, mid: AgentRun(id="new_run", topic="x", content_type="blog", style="casual", saved_content_id=cid),
    lambda cid, mid: AgentRun(id="new_run", topic="x", content_type="blog", style="casual", thread_id="thread_second"),
    lambda cid, mid: RunStep(run_id="run_second", step_index=2, step_name="writer"),
    lambda cid, mid: AgentRunEvent(run_id="run_second", seq=2, event_type="progress", payload="{}"),
    lambda cid, mid: ProposedAction(id="new_action", thread_id="thread_first", proposing_message_id=mid,
                                   tool_name="create_content", args_json="{}", args_hash="f" * 64,
                                   impact_summary="x", expires_at=datetime.now()),
])
def test_cross_user_foreign_and_logical_references_are_rejected(workspaces, factory):
    _, first, second = workspaces
    first.upsert_agent_thread("thread_first")
    content_id, message_id = _seed_workspace(second, "second")
    with first._get_session() as session:
        session.add(factory(content_id, message_id))
        with pytest.raises(TenantAccessError, match="Referenced"):
            session.commit()
        session.rollback()


def test_missing_run_and_invalid_reference_updates_are_rejected(workspaces):
    _, first, second = workspaces
    own_id = _content(first)
    other_id = _content(second)
    with pytest.raises(TenantAccessError):
        first.save_run_step_checkpoint("missing_run", 1, "writer")
    with pytest.raises(TenantAccessError):
        first.update_content(own_id, parent_id=other_id)
    first.create_run("own_run", "x", "blog", "casual", thread_id="correlation_only")
    with pytest.raises(TenantAccessError):
        first.update_run("own_run", saved_content_id=other_id)
    with first._get_session() as session:
        with pytest.raises(TenantAccessError):
            session.query(Content).update({Content.parent_id: other_id})
        session.rollback()


def test_owner_is_filled_immutable_and_required_for_unscoped_writes(workspaces):
    system, first, second = workspaces
    own_id = _content(first)
    with pytest.raises(AttributeError):
        first.user_id = second.user_id
    with first.SessionLocal() as session:
        assert session.user_id == first.user_id
        session.info["user_id"] = second.user_id
        assert session.user_id == first.user_id
        assert session.get(Content, own_id).user_id == first.user_id
    with first._get_session() as session:
        session.add(Content(user_id=second.user_id, content="forged", content_type="blog", style="casual"))
        with pytest.raises(TenantAccessError):
            session.commit()
        session.rollback()
    with pytest.raises(TenantAccessError):
        first.update_content(own_id, user_id=second.user_id)
    with pytest.raises(TenantAccessError):
        _content(system)
    with system._get_session() as session:
        session.add(Content(user_id=first.user_id, content="explicit", content_type="blog", style="casual"))
        session.commit()
    assert first.get_content_stats()["total_contents"] == 2


def test_raw_sql_and_bulk_owner_bypasses_are_rejected(workspaces):
    _, first, second = workspaces
    _content(first)
    with first._get_session() as session:
        for statement in (
            text("SELECT * FROM contents"),
            insert(Content).values(user_id=second.user_id, content="x", content_type="blog", style="casual"),
            update(Content).values(user_id=second.user_id),
        ):
            with pytest.raises(TenantAccessError):
                session.execute(statement)
            session.rollback()


def test_idempotency_and_background_discovery_carry_the_real_owner(workspaces):
    system, first, second = workspaces
    a = first.claim_idempotency_key(scope="generate", key="same", args={"topic": "a"})
    b = second.claim_idempotency_key(scope="generate", key="same", args={"topic": "b"})
    assert a["record_id"] != b["record_id"]
    assert first.complete_idempotency_key(b["record_id"], result={"private": "b"}) is False
    assert first.complete_idempotency_key(a["record_id"], result={"private": "a"}) is True
    assert first.claim_idempotency_key(scope="generate", key="same", args={"topic": "a"})["result"] == {"private": "a"}
    second.create_job("job_second", "generate", {})
    second.create_run("run_second", "private", "blog", "casual")
    assert first.get_job("job_second") is None
    assert first.get_run("run_second") is None
    assert system.get_job("job_second")["user_id"] == second.user_id
    assert system.get_run("run_second")["user_id"] == second.user_id


def test_workspace_migration_preserves_legacy_data_without_public_claim(pg_engine):
    from alembic import command
    from src.storage.content_store import Base
    from src.storage.schema import alembic_config, assert_schema_current
    from src.storage.tenancy import LEGACY_USER_ID

    Base.metadata.drop_all(pg_engine)
    with pg_engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    cfg = alembic_config(pg_engine.url.render_as_string(hide_password=False))
    try:
        command.upgrade(cfg, "0008_job_lease_and_checkpoints")
        with pg_engine.begin() as connection:
            legacy_id = connection.execute(text(
                "INSERT INTO contents (title, content, content_type, style) "
                "VALUES ('legacy', 'private legacy data', 'blog', 'casual') RETURNING id"
            )).scalar_one()
        command.upgrade(cfg, "head")
        assert_schema_current(pg_engine)
        command.check(cfg)
        system = ContentStore(database_url=pg_engine.url.render_as_string(hide_password=False), initialize_schema=False)
        try:
            with system._get_session() as session:
                legacy = session.get(User, LEGACY_USER_ID)
                assert legacy.username == "__legacy_workspace__"
                assert legacy.is_active is False
                assert legacy.password_hash == "!"
                session.add(User(id="a" * 32, username="fresh_user", password_hash="!"))
                session.commit()
            assert system.for_user(LEGACY_USER_ID).get_content(legacy_id)["title"] == "legacy"
            assert system.for_user("a" * 32).get_content(legacy_id) is None
            assert system.for_user("a" * 32).list_contents() == []
            with pytest.raises(RuntimeError, match="Workspace downgrade"):
                command.downgrade(cfg, "0008_job_lease_and_checkpoints")
            with system._get_session() as session:
                session.delete(session.get(User, "a" * 32))
                session.commit()
        finally:
            system.engine.dispose()
    finally:
        command.downgrade(cfg, "base")
        with pg_engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
