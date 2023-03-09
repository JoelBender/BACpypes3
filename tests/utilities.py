#!/usr/bin/python

"""
BACpypes Testing Utilities
--------------------------
"""

import os

from typing import Callable, cast

from bacpypes3.settings import os_settings
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import ArgumentParser

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# defaults for testing
BACPYPES_TEST = ""
BACPYPES_TEST_OPTION = ""

# parsed test options
test_options = None


@bacpypes_debugging
def setup_package() -> None:
    fn_debug = cast(Callable[..., None], setup_package._debug)  # type: ignore[attr-defined]
    global test_options

    # get the os settings
    os_settings()

    # create an argument parser
    parser = ArgumentParser(description=__doc__)

    # add an option
    parser.add_argument(
        "--option",
        help="this is an option",
        default=os.getenv("BACPYPES_TEST_OPTION") or BACPYPES_TEST_OPTION,
    )

    # get the debugging args and parse them
    arg_str = os.getenv("BACPYPES_TEST") or BACPYPES_TEST
    test_options = parser.parse_args(arg_str.split())

    if _debug:
        fn_debug("setup_package")
        fn_debug("    - test_options: %r", test_options)


@bacpypes_debugging
def teardown_package() -> None:
    fn_debug = cast(Callable[..., None], teardown_package._debug)  # type: ignore[attr-defined]

    if _debug:
        fn_debug("teardown_package")
