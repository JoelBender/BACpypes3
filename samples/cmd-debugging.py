#!/usr/bin/python

"""
This application adds the CmdDebugging mixin class to provide support for
additional debugging commands.
"""

import sys
import asyncio

from typing import Callable

from bacpypes3.settings import settings
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import ArgumentParser

from bacpypes3.console import Console
from bacpypes3.cmd import Cmd, CmdDebugging
from bacpypes3.comm import bind

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class SampleCmd(Cmd, CmdDebugging):
    _debug: Callable[..., None]

    """
    Sample Cmd
    """

    async def do_hello(self) -> None:
        """
        usage: hello
        """
        await self.response("Hello!")


async def main() -> None:
    try:
        console = None
        args = ArgumentParser().parse_args()
        if _debug:
            _log.debug("args: %r", args)
            _log.debug("settings: %r", settings)

        # build a very small stack
        console = Console()
        cmd = SampleCmd()
        bind(console, cmd)

        # run until the console is done, canceled or EOF
        await console.fini.wait()

    finally:
        if console and console.exit_status:
            sys.exit(console.exit_status)


if __name__ == "__main__":
    asyncio.run(main())
