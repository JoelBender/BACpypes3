"""
The bacpypes3.cmd.Cmd class is patterned after the Python Cmd class but
supports parameter and keyword argument inspection to translate strings into
appropriate parameter values so the `do_x()` functions already have that done
for them.

Note that the Cmd class is a Server, it interprets the strings coming downstream
and does something with them.  In sample applications the upstream object is
a Console which sends PDUs as strings downstream it has gathered from stdin
and writes the PDUs it receives upstream (like from this sample) to stdout.

This sample application has a list of simple commands that take a variety
of required and optional parameters and keyword arguments and is used to test
that the `Cmd` class is interpreting the downsteam string correctly.
"""

import sys
import asyncio

from typing import Awaitable, Callable, Union

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
    _debug: Callable[..., None]

    """
    Sample Cmd
    """

    async def do_sleep(self, seconds: float) -> None:
        """
        usage: sleep seconds
        """
        if _debug:
            SampleCmd._debug("do_sleep %r", seconds)

        await asyncio.sleep(seconds)

    def do_a(self, x: int = 1, y: int = 2, z: int = 3) -> Awaitable[None]:
        """
        usage: a [ x:int [ y:int [ z:int ] ] ]
        """
        if _debug:
            SampleCmd._debug("do_a %r %r %r", x, y, z)

        return self.response(f"a {x} {y} {z}")

    async def do_b(self, x: str, y: int = 2, *z: str) -> None:
        """
        usage: b x:str [ y:int [ z:str ... ] ]
        """
        if _debug:
            SampleCmd._debug("do_b %r %r %r", x, y, z)

        await self.response(f"b {x!r} {y!r} {z!r}")

    async def do_c(self, *, x: int = 4) -> None:
        """
        usage: c [ --x:int ]
        """
        if _debug:
            SampleCmd._debug("do_c %r", x)

        await self.response(f"c {x!r}")

    async def do_d(self, *, x: int) -> None:
        """
        usage: d --x:int
        """
        if _debug:
            SampleCmd._debug("do_d %r", x)

        await self.response(f"d {x!r}")

    async def do_e(self, *, x: bool = False) -> None:
        """
        usage: e [ --x ]
        """
        if _debug:
            SampleCmd._debug("do_e %r", x)

        await self.response(f"e {x!r}")

    async def do_f1(self, **kwargs) -> None:
        """
        usage: f1 **kwargs
        """
        await self.response(f"f1 {kwargs!r}")

    async def do_f2(self, **kwargs: bool) -> None:
        await self.response(f"f2 {kwargs!r}")

    async def do_f3(self, **kwargs: int) -> None:
        await self.response(f"f3 {kwargs!r}")

    async def do_f4(self, **kwargs: Address) -> None:
        await self.response(f"f4 {kwargs!r}")

    async def do_f5(self, **kwargs: Union[IPv4Address, IPv6Address]) -> None:
        await self.response(f"f5 {kwargs!r}")

    async def do_g1(self, *args) -> None:
        """
        usage: g1 *args
        """
        await self.response(f"g1 {args!r}")


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
