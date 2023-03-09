#!/usr/bin/python

"""
Glue routines to simulate package setup and teardown.
"""

import _pytest  # type: ignore[import]

from .utilities import setup_package, teardown_package
from .clocked_test import clocked_test  # noqa: F401


def pytest_configure(config: _pytest.config.Config) -> None:
    setup_package()


def pytest_unconfigure() -> None:
    teardown_package()
