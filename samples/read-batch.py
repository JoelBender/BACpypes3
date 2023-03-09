"""
Simple console example that reads batches of values.
"""

import sys
import asyncio

from typing import Callable

from bacpypes3.settings import settings
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application

from bacpypes3.console import Console
from bacpypes3.cmd import Cmd
from bacpypes3.comm import bind

from bacpypes3.lib.batchread import DeviceAddressObjectPropertyReference, BatchRead

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# globals
app: Application
batch_read: BatchRead

# stuff to read, parameters to DeviceAddressObjectPropertyReference
stuff_to_read = [
    (1, "100:2", "device,10002", "object-name"),
    (2, "100:2", "device,10002", "local-date"),
    (3, "100:2", "device,10002", "local-time"),
    (4, "100:2", "analog-value,1", "object-name"),
    (5, "100:2", "analog-value,1", "present-value"),
    (6, "100:3", "device,10003", "object-name"),
    (7, "100:4", "device,10004", "object-name"),
    (8, "100:5", "device,10005", "object-name"),
    (9, "200:2", "device,20002", "object-name"),
    (10, "200:2", "analog-value,1", "present-value"),
    (11, "200:2", "analog-value,2", "present-value"),
    (12, "200:3", "device:20003", "object-name"),
]


@bacpypes_debugging
class SampleCmd(Cmd):
    """
    Sample Cmd
    """

    _debug: Callable[..., None]

    async def do_read(self) -> None:
        """
        usage: read
        """
        if _debug:
            SampleCmd._debug("do_read")

        asyncio.ensure_future(batch_read.run(app, self.callback))

    def callback(self, key, value) -> None:
        asyncio.ensure_future(self.response(f"{key} = {value}"))

    async def do_stop(self) -> None:
        """
        usage: stop
        """
        global batch_read
        batch_read.stop()


async def main() -> None:
    global app, batch_read

    try:
        app = None
        args = SimpleArgumentParser().parse_args()
        if _debug:
            _log.debug("settings: %r", settings)

        # build a very small stack
        console = Console()
        cmd = SampleCmd()
        bind(console, cmd)

        # build the application
        app = Application.from_args(args)

        # transform the list of stuff to read
        daopr_list = [
            DeviceAddressObjectPropertyReference(*args) for args in stuff_to_read
        ]
        batch_read = BatchRead(daopr_list)

        # run until the console is done, canceled or EOF
        await console.fini.wait()

    except KeyboardInterrupt:
        if _debug:
            _log.debug("keyboard interrupt")
    finally:
        if app:
            app.close()
        if console and console.exit_status:
            sys.exit(console.exit_status)


if __name__ == "__main__":
    asyncio.run(main())
