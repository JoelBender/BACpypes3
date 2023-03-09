"""
Simple console example that echos the input converted to uppercase.
"""

import sys
import asyncio

from typing import Callable

from bacpypes3.settings import settings
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import ArgumentParser
from bacpypes3.console import Console, ConsolePDU
from bacpypes3.comm import Server, bind

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class Echo(Server[ConsolePDU]):
    """
    This example server echos downstream strings as uppercase strings going
    upstream.  If the PDU is None the console is finished, and this could send
    an integer status code upstream to exit.
    """

    _debug: Callable[..., None]

    async def indication(self, pdu: ConsolePDU) -> None:
        """
        This function is called with each line of text from the console (or
        from a file or pipe) and called with None at end-of-file.  It is
        "downstream" of the Console() instance and gets this "indication" when
        the console is making a "request".
        """
        if _debug:
            Echo._debug("indication {!r}".format(pdu))
        if pdu is None:
            return

        # send the uppercase content back up the stack
        await self.response(pdu.upper())


async def main() -> None:
    try:
        console = None
        args = ArgumentParser().parse_args()
        if _debug:
            _log.debug("args: %r", args)
            _log.debug("settings: %r", settings)

        # build a very small stack
        console = Console()
        echo = Echo()
        if _debug:
            _log.debug("console, echo: %r, %r", console, echo)

        # bind the two objects together, top down
        bind(console, echo)

        # run until the console is done, canceled or EOF
        await console.fini.wait()

    finally:
        if console and console.exit_status:
            sys.exit(console.exit_status)


if __name__ == "__main__":
    asyncio.run(main())
