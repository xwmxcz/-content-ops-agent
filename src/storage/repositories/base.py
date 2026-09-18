"""Declare the kernel that every repository mixin relies on.

The mixins share one session and one workspace scope, so they must be composed
into a single class rather than injected separately. That sharing is exactly what
makes them invisible to a type checker: ``ThreadRepositoryMixin`` calls
``self._get_session()`` and reads ``self.user_id``, neither of which it defines.

This module states that contract once. Each mixin inherits from
``RepositoryMixin``, so the methods it borrows from the host class are declared
in one place instead of being re-derived per module or silenced per call site.
The host class (``ContentStore``) supplies the implementations and is what
actually gets instantiated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import Session


class RepositoryMixin:
    """Kernel members a repository mixin may assume the host class provides."""

    #: Canonical 32-hex workspace owner, or None on the unscoped system store.
    _user_id: str | None

    #: Shared engine; ``for_user`` returns a store that reuses this object.
    engine: Engine

    #: Session factory bound to the host's engine, producing TenantSessions.
    SessionLocal: object

    @property
    def user_id(self) -> str | None:
        """The workspace this store is scoped to, or None when unscoped."""
        raise NotImplementedError

    def _get_session(self) -> Session:
        """Open a session scoped to :attr:`user_id`."""
        raise NotImplementedError


def assigned_pk(instance: object, field: str) -> int:
    """Return an integer primary key that the database has already assigned.

    SQLAlchemy types a primary key as Optional because it is unset before the
    flush. Every caller reads it immediately after ``commit()``, so a None would
    mean the flush silently did nothing -- a real bug worth failing loudly on
    rather than a case to paper over.

    This lives with the kernel contract rather than with the models: it asserts a
    store-side invariant (a commit populated the key), not a property of the
    schema.
    """
    value = getattr(instance, field)
    if value is None:
        raise RuntimeError(f"{type(instance).__name__}.{field} is unset after flush")
    return int(value)
