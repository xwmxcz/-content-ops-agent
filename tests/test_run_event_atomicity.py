from concurrent.futures import ThreadPoolExecutor
import threading

from sqlalchemy import inspect


def _create_run(store, run_id):
    return store.create_run(
        run_id=run_id,
        topic="atomic test",
        content_type="blog",
        style="professional",
    )


def test_run_event_schema_has_unique_run_sequence(store):
    constraints = inspect(store.engine).get_unique_constraints("agent_run_events")
    assert any(
        constraint.get("name") == "uq_agent_run_events_run_seq"
        and set(constraint.get("column_names") or []) == {"run_id", "seq"}
        for constraint in constraints
    )


def test_concurrent_run_events_receive_unique_contiguous_sequences(store):
    run_id = "run_concurrent_events"
    _create_run(store, run_id)

    with ThreadPoolExecutor(max_workers=12) as pool:
        sequences = list(pool.map(
            lambda index: store.append_run_event(run_id, "token", {"index": index}),
            range(120),
        ))

    assert sorted(sequences) == list(range(1, 121))
    persisted = store.list_run_events(run_id, limit=200)
    assert [event["seq"] for event in persisted] == list(range(1, 121))
    assert store.get_run(run_id)["next_event_seq"] == 121


def test_terminal_event_is_durable_end_of_stream(store):
    run_id = "run_terminal_end"
    _create_run(store, run_id)
    terminal = store.transition_run_and_append_event(
        run_id,
        expected_statuses={"running"},
        new_status="cancelled",
        event_type="run_cancelled",
        payload={"run_id": run_id},
    )
    assert terminal is not None
    assert store.append_run_event(run_id, "step_complete", {"late": True}) is None
    assert store.append_run_event(run_id, "step_token", {"delta": "late"}) is None
    assert [event["event_type"] for event in store.list_run_events(run_id)] == ["run_cancelled"]
    assert store.get_run(run_id)["next_event_seq"] == 2


def test_terminal_transition_and_event_are_compare_and_set_atomic(store):
    run_id = "run_terminal_race"
    _create_run(store, run_id)
    barrier = threading.Barrier(2)

    def transition(status, event_type):
        barrier.wait()
        return store.transition_run_and_append_event(
            run_id,
            expected_statuses={"running"},
            new_status=status,
            event_type=event_type,
            payload={"status": status},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        completed = pool.submit(transition, "completed", "run_complete")
        cancelled = pool.submit(transition, "cancelled", "run_cancelled")
        results = [completed.result(), cancelled.result()]

    assert sum(result is not None for result in results) == 1
    events = store.list_run_events(run_id)
    terminal_events = [event for event in events if event["event_type"] in {"run_complete", "run_cancelled"}]
    assert len(terminal_events) == 1
    assert store.get_run(run_id)["status"] in {"completed", "cancelled"}


def test_cancel_race_cannot_leave_agent_final_content_for_cancelled_run(store):
    run_id = "run_content_cancel_race"
    _create_run(store, run_id)
    barrier = threading.Barrier(2)

    def complete():
        barrier.wait()
        return store.complete_run_with_content(
            run_id,
            payload={"run_id": run_id, "saved_content_id": None},
            content_fields={
                "title": "atomic",
                "content": "final body",
                "content_type": "blog",
                "style": "professional",
                "keywords": "[]",
                "tags": "[]",
                "status": "agent_final",
            },
            plan=[],
            revision_count=0,
            total_prompt_tokens=1,
            total_completion_tokens=1,
            total_cost=0.0,
        )

    def cancel():
        barrier.wait()
        return store.transition_run_and_append_event(
            run_id,
            expected_statuses={"running"},
            new_status="cancelled",
            event_type="run_cancelled",
            payload={"run_id": run_id},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        complete_future = pool.submit(complete)
        cancel_future = pool.submit(cancel)
        completed = complete_future.result()
        cancelled = cancel_future.result()

    run = store.get_run(run_id)
    saved = store.list_contents(status="agent_final")
    if run["status"] == "cancelled":
        assert completed is None
        assert cancelled is not None
        assert run["saved_content_id"] is None
        assert saved == []
    else:
        assert completed is not None
        assert cancelled is None
        assert run["saved_content_id"] is not None
        assert len(saved) == 1
