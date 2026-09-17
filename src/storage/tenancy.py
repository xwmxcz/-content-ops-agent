"""Own workspace isolation for ORM reads, bulk mutations, and linked writes.

Account tables are deliberately outside this boundary. An unscoped session is
reserved for authentication, migration, and worker discovery; its new business
rows still require an explicit owner. Request and job sessions have one fixed
owner for their entire lifetime.
"""
from __future__ import annotations

from sqlalchemy import Column, ForeignKey, String, event, inspect, select
from sqlalchemy.orm import Session, with_loader_criteria
from sqlalchemy.sql.elements import BindParameter, Null

LEGACY_USER_ID = "00000000000000000000000000000001"


class TenantAccessError(ValueError):
    """A write would cross a workspace boundary or omit its owner."""


class OwnedMixin:
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)


# Non-FK references are checked alongside actual foreign keys. Pipeline thread
# IDs can be standalone correlation IDs, but an existing thread must be owned.
_LOGICAL_REFERENCES = {
    "contents": {"parent_id": ("contents", "id", False)},
    "agent_runs": {
        "thread_id": ("agent_threads", "id", True),
        "saved_content_id": ("contents", "id", False),
    },
    "run_steps": {"run_id": ("agent_runs", "id", False)},
    "proposed_actions": {
        "proposing_message_id": ("agent_messages", "id", False),
        "consuming_message_id": ("agent_messages", "id", False),
    },
}


class TenantSession(Session):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._user_id = self.info.get("user_id")

    @property
    def user_id(self) -> str | None:
        return self._user_id

    def bulk_save_objects(self, objects, *args, **kwargs):
        raise TenantAccessError("Use add_all() so ownership checks run before writing")

    def bulk_insert_mappings(self, mapper, mappings, *args, **kwargs):
        raise TenantAccessError("Use add_all() so ownership checks run before writing")

    def bulk_update_mappings(self, mapper, mappings):
        raise TenantAccessError("Use ORM objects so ownership checks run before writing")


def _reference_columns(mapper):
    references = dict(_LOGICAL_REFERENCES.get(mapper.local_table.name, {}))
    for column in mapper.columns:
        for foreign_key in column.foreign_keys:
            target = foreign_key.column
            if target.table.name != "users":
                references[column.key] = (target.table.name, target.key, False)
    return references


@event.listens_for(TenantSession, "do_orm_execute")
def _scope_statement(state):
    user_id = state.session.user_id
    if user_id is None:
        return
    if not state.is_orm_statement:
        raise TenantAccessError("Workspace sessions require ORM statements")

    mapper = state.bind_mapper
    if mapper is not None and issubclass(mapper.class_, OwnedMixin):
        if state.is_insert:
            raise TenantAccessError("Use ORM objects so ownership checks run before writing")
        if state.is_update:
            # Bulk DML skips before_flush. Only ordinary field updates and
            # clearing references are supported; owner/PK changes are rejected.
            immutable = {"user_id", *(column.key for column in mapper.primary_key)}
            references = _reference_columns(mapper)
            values = state.statement._values or {}
            parameters = state.parameters
            parameter_rows = parameters if isinstance(parameters, list) else [parameters or {}]
            assignments = list(values.items())
            for row in parameter_rows:
                assignments.extend(row.items())
            for column, value in assignments:
                key = column if isinstance(column, str) else column.key
                if key in immutable:
                    raise TenantAccessError("Workspace ownership and primary keys are immutable")
                if key in references:
                    clears_reference = not parameters and (
                        isinstance(value, Null) or value is None or (
                            isinstance(value, BindParameter)
                            and value.value is None and not value.required
                        )
                    )
                    if not clears_reference:
                        raise TenantAccessError("Update references through ORM objects")

    if state.is_select or state.is_update or state.is_delete:
        state.statement = state.statement.options(
            with_loader_criteria(
                OwnedMixin,
                lambda model: model.user_id == user_id,
                include_aliases=True,
            )
        )


@event.listens_for(TenantSession, "before_flush")
def _validate_owned_writes(session, flush_context, instances):
    owned = [
        item for item in session.new.union(session.dirty).union(session.deleted)
        if isinstance(item, OwnedMixin)
    ]
    for item in owned:
        state = inspect(item)
        if item in session.new and item.user_id is None:
            item.user_id = session.user_id
        if not item.user_id:
            raise TenantAccessError("Business rows require an explicit workspace owner")
        if session.user_id is not None:
            if item.user_id != session.user_id:
                raise TenantAccessError("Record does not belong to this workspace")
            if item in session.new:
                # Client-named threads remain supported, but reusing another
                # user's global primary key is an access miss, not an insert.
                primary_key = list(state.mapper.primary_key)
                if all(getattr(item, column.key) is not None for column in primary_key):
                    table = state.mapper.local_table
                    owner = session.connection().execute(
                        select(table.c.user_id).where(*(
                            column == getattr(item, column.key) for column in primary_key
                        ))
                    ).scalar_one_or_none()
                    if owner is not None and owner != session.user_id:
                        raise TenantAccessError("Record does not belong to this workspace")
            if item not in session.new and state.attrs.user_id.history.has_changes():
                raise TenantAccessError("Workspace ownership is immutable")
            if item not in session.new and any(
                state.attrs[column.key].history.has_changes()
                for column in state.mapper.primary_key
            ):
                raise TenantAccessError("Workspace primary keys are immutable")

    # Fill all pending owners first, so a thread and its first message can be
    # inserted together without weakening reference checks.
    for item in owned:
        if item in session.deleted:
            continue
        state = inspect(item)
        for key, (table_name, target_key, allow_missing) in _reference_columns(state.mapper).items():
            if item not in session.new and not state.attrs[key].history.has_changes():
                continue
            value = getattr(item, key)
            if value is None:
                continue
            target = state.mapper.local_table.metadata.tables[table_name]
            if "user_id" not in target.c:
                continue
            pending = next((
                candidate for candidate in session.new.union(session.dirty)
                if isinstance(candidate, OwnedMixin)
                and inspect(candidate).mapper.local_table.name == table_name
                and getattr(candidate, target_key) == value
            ), None)
            if pending is not None:
                owner = pending.user_id
            else:
                # Use the known metadata table internally, so a foreign owner
                # and a missing correlation thread can be distinguished. This
                # value is never exposed to callers.
                owner = session.connection().execute(
                    select(target.c.user_id).where(target.c[target_key] == value)
                ).scalar_one_or_none()
            if owner != item.user_id and not (owner is None and allow_missing):
                raise TenantAccessError(f"Referenced {key} is not in this workspace")
