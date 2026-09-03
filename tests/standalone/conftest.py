# This directory contains standalone tests that must not use the shared test
# configuration in tests/conftest.py. These tests need to control the
# environment configuration from scratch.
#
# These tests are designed to run as standalone scripts, not through pytest.
# Pytest will collect them but they should be excluded from normal test runs.

import pytest

def pytest_collection_modifyitems(config, items):
    """Skip standalone tests when running pytest normally.
    
    These tests must run as standalone scripts to avoid config module caching.
    Use: python3 tests/standalone/test_production_validation.py
    """
    skip_standalone = pytest.mark.skip(reason="Standalone test - run directly as script")
    for item in items:
        if "standalone" in str(item.fspath):
            item.add_marker(skip_standalone)
