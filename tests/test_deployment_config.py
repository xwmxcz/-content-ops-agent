"""Deployment-surface regressions found only by running the container stack.

Both bugs guarded here were invisible to unit tests and code review: they live in
files that are executed by gunicorn and alembic rather than imported by the app,
so nothing exercised them until Docker Compose actually started.
"""

import importlib.util
import logging
import sys
from logging.config import fileConfig
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_module_namespace(path: Path, module_name: str) -> dict:
    """Import a standalone config file the way gunicorn does, returning vars()."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        return vars(module)
    finally:
        sys.modules.pop(module_name, None)


def test_gunicorn_config_has_no_name_colliding_with_a_gunicorn_setting():
    """Every colliding module-level name must survive gunicorn's own validation.

    Gunicorn treats each module-level name in its config file that matches one of
    its ~119 settings as a value for that setting. It has a setting literally
    called `config` (the -c option) which must be a string, so
    `from src.utils import config` bound a Config object to it and gunicorn
    rejected its own config file with "Not a string: <Config object>". The api
    container then crash-looped and never passed its healthcheck.

    This runs gunicorn's real `Config.set()` validation rather than re-deriving
    the rules, so any future collision fails here instead of at deploy time.
    """
    from gunicorn.config import Config

    namespace = _load_module_namespace(ROOT / "gunicorn.conf.py", "_gunicorn_conf_probe")
    cfg = Config()

    collisions = {
        key: value
        for key, value in namespace.items()
        if key in cfg.settings and not key.startswith("_")
    }
    # Guard the guard: if this file stopped defining any recognised setting, the
    # test would pass while checking nothing.
    assert "bind" in collisions, "expected gunicorn.conf.py to set at least `bind`"

    for key, value in collisions.items():
        try:
            cfg.set(key.lower(), value)
        except Exception as exc:  # noqa: BLE001 - surface the offending name
            pytest.fail(
                f"gunicorn would reject its own config file: setting {key!r} "
                f"got {value!r} ({type(value).__name__}): {exc}. "
                "Alias the import (e.g. `from src.utils import config as app_config`) "
                "so the module-level name does not shadow a gunicorn setting."
            )


def test_gunicorn_config_binds_configured_host_and_port():
    """The aliased import must still produce a real bind address."""
    from src.utils import config as app_config

    namespace = _load_module_namespace(ROOT / "gunicorn.conf.py", "_gunicorn_conf_bind")

    assert namespace["bind"] == f"{app_config.API_HOST}:{app_config.API_PORT}"
    assert namespace["worker_class"] == "uvicorn.workers.UvicornWorker"
    # Gunicorn/Uvicorn must not run their own X-Forwarded-* trust policy; the app
    # middleware validates the peer against TRUSTED_PROXY_CIDRS instead.
    assert namespace["forwarded_allow_ips"] == ""


def test_alembic_logging_config_preserves_application_loggers():
    """Alembic's fileConfig must not disable the application's loggers.

    `logging.config.fileConfig` defaults to `disable_existing_loggers=True`, which
    sets `disabled = True` on every logger absent from alembic.ini -- including all
    of `src.*`. Any in-process alembic run then silently muted application logging
    for the rest of the process. In the suite this surfaced as five unrelated
    caplog assertions failing only when `test_migrations.py` ran first; in
    production it would silently drop log events after a migration.
    """
    probe_name = "src.api.services.dynamic_pipeline"
    probe = logging.getLogger(probe_name)
    was_disabled = probe.disabled
    try:
        probe.disabled = False

        # Establish that the default really is destructive, so this test fails for
        # the right reason if the alembic.ini logger sections change.
        fileConfig(str(ROOT / "alembic.ini"))
        assert probe.disabled is True, (
            "expected the default fileConfig to disable existing loggers; "
            "if this no longer holds, this regression test needs rewriting"
        )

        # This is how migrations/env.py must call it.
        fileConfig(str(ROOT / "alembic.ini"), disable_existing_loggers=False)
        assert probe.disabled is False
    finally:
        probe.disabled = was_disabled


def test_migrations_env_disables_existing_loggers_explicitly():
    """Pin the call site, since the destructive behaviour is the library default.

    A future edit that drops the keyword would restore a silent, hard-to-trace
    logging failure, so the argument is asserted at the source rather than only
    through its effect.
    """
    source = (ROOT / "migrations" / "env.py").read_text(encoding="utf-8")

    assert "disable_existing_loggers=False" in source, (
        "migrations/env.py must call fileConfig(..., disable_existing_loggers=False) "
        "or alembic will disable every src.* logger for the rest of the process"
    )
