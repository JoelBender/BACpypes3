"""
Same as the `console.py` application but adds a `--prompt` option to
change the prompt.
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
    _debug: Callable[..., None]

    async def indication(self, pdu: ConsolePDU) -> None:
        if _debug:
            Echo._debug("indication {!r}".format(pdu))
        if pdu is None:
            return

        assert isinstance(pdu, str)
        await self.response(pdu.upper())


async def main() -> None:
    try:
        console = None

        # add a way to change the console prompt
        parser = ArgumentParser()
        parser.add_argument(
            "--prompt",
            type=str,
            help="change the prompt",
            default="> ",
        )

        args = parser.parse_args()
        if _debug:
            _log.debug("args: %r", args)
            _log.debug("settings: %r", settings)

        # build a very small stack
        console = Console(prompt=args.prompt)
        echo = Echo()
        bind(console, echo)

        # run until the console is done, canceled or EOF
        await console.fini.wait()

    finally:
        if console and console.exit_status:
            sys.exit(console.exit_status)


if __name__ == "__main__":
    asyncio.run(main())
