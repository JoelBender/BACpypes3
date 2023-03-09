#!/usr/bin/python

"""
Address parameters for command line interpreters
"""

import sys
import asyncio

from typing import Callable, Optional, Union

from bacpypes3.settings import settings
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import ArgumentParser

from bacpypes3.console import Console
from bacpypes3.cmd import Cmd
from bacpypes3.comm import bind
from bacpypes3.pdu import Address, IPv4Address, IPv6Address

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class SampleCmd(Cmd):
    """
    Sample Console Command utility demonstrating addresses support in bacpypes3
    Using the typing module, bacpypes3 can evaluate at runtime the argument
    passed to the function then return the right type (or an exception).
    """

    _debug: Callable[..., None]

    async def do_test1(self, addr: Address) -> None:
        """
        test1 requires an address argument that will be evaluated as a
        bacpypes3.pdu.Address, and if that interpretation is successful,
        provided as the parameter value.

        usage: test1 addr

        ex. test1 2:4 or test1 192.168.1.2
        """
        if _debug:
            SampleCmd._debug("do_test1 %r", addr)

        await self.response(f"test1 {addr!r}")

    async def do_test2(self, addr: Optional[Address] = None) -> None:
        """
        test2 is similar to test1 with an optional address.

        usage: test2 [ addr:Address ]

        ex. test2 2:4 or test2 192.168.1.2 or test2
        """
        if _debug:
            SampleCmd._debug("do_test2 %r", addr)

        await self.response(f"test2 {addr!r}")

    async def do_test3(self, addr: Union[IPv4Address, IPv6Address]) -> None:
        """
        This varient accepts only IPv4 or IPv6 addresses or will raise an
        exception.

        usage: test3 addr
        """
        if _debug:
            SampleCmd._debug("do_test3 %r", addr)

        await self.response(f"test3 {addr!r}")


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
