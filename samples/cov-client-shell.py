"""
Simple example that creates a change-of-value context and dumps out the
property identifier and its value from the notifications it receives.

The device address and monitored object identifier are the only required
parameters to `change_of_value()`.
"""
# from __future__ import annotations

import asyncio

from typing import Callable

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application
from bacpypes3.cmd import Cmd
from bacpypes3.comm import bind
from bacpypes3.console import Console
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.basetypes import PropertyReference

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# globals
assigned_ids = 0
running_processes = {}


@bacpypes_debugging
class Snork:
    def __init__(
        self,
        device_address: Address,
        object_identifier: ObjectIdentifier,
        property_identifier: PropertyReference,
    ):
        global assigned_ids

        # give this a name
        assigned_ids += 1
        self.process_identifier = assigned_ids
        if _debug:
            Snork._debug("__init__(%s)", self.process_identifier)

        # keep track of the args
        self.device_address = device_address
        self.object_identifier = object_identifier
        self.property_identifier = property_identifier

        # create a fini event
        self.fini = asyncio.Event()
        self.task = None

    async def run(self):
        if _debug:
            Snork._debug("run(%s)", self.process_identifier)

        try:
            # use a SubscriptionContextManager
            async with app.change_of_value(
                self.device_address,
                self.object_identifier,
                self.process_identifier,
                True,  # args.confirmed,
                30,  # args.lifetime,
            ) as scm:
                if _debug:
                    _log.debug("    - scm: %r", scm)

                while not self.fini.is_set():
                    incoming: asyncio.Future = asyncio.ensure_future(scm.get_value())
                    done, pending = await asyncio.wait(
                        [incoming, self.fini.wait()],
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    # cancel pending tasks to avoid leaking them
                    for task in pending:
                        task.cancel()

                    # send incoming messages up the stack
                    if incoming in done:
                        property_identifier, property_value = incoming.result()
                        print(
                            f"{self.process_identifier} {property_identifier} {property_value}"
                        )

            if _debug:
                _log.debug(f"{self.process_identifier} exited context")
        except Exception as err:
            if _debug:
                _log.debug("    - exception: %r", err)

    def stop(self):
        if _debug:
            Snork._debug("stop(%s)", self.process_identifier)

        # set the finished event
        self.fini.set()


@bacpypes_debugging
class SnorkCmd(Cmd):
    """
    Snork Cmd
    """

    _debug: Callable[..., None]

    async def do_start(
        self,
        device_address: Address,
        object_identifier: ObjectIdentifier,
        property_reference: PropertyReference,
    ) -> None:
        """
        usage: start address objid prop[indx]
        """
        if _debug:
            SnorkCmd._debug(
                "do_start %r %r %r",
                device_address,
                object_identifier,
                property_reference,
            )
        global running_processes

        # create an instance
        snork = Snork(
            device_address, object_identifier, property_reference.propertyIdentifier
        )
        if _debug:
            SnorkCmd._debug("    - snork: %r", snork)

        # save a reference
        running_processes[snork.process_identifier] = snork

        # stuff the task into the snork
        snork.task = asyncio.create_task(snork.run())
        if _debug:
            SnorkCmd._debug("    - task: %r", snork.task)

    async def do_stop(
        self,
        process_identifier: int,
    ) -> None:
        """
        usage: stop procid
        """
        if _debug:
            SnorkCmd._debug("do_stop %r", process_identifier)

        if process_identifier not in running_processes:
            await self.response("object identifier expected")
            return

        # find the snork
        snork = running_processes.pop(process_identifier)
        if _debug:
            SnorkCmd._debug("    - snork: %r", snork)

        # tell it to stop and wait for it to complete
        snork.stop()
        await snork.task


async def main() -> None:
    global app

    app = None
    try:
        parser = SimpleArgumentParser()
        args = parser.parse_args()
        if _debug:
            _log.debug("args: %r", args)

        # build a very small stack
        console = Console()
        cmd = SnorkCmd()
        bind(console, cmd)

        # build an application
        app = Application.from_args(args)
        if _debug:
            _log.debug("app: %r", app)

        # wait until the user is done
        await console.fini.wait()

    except KeyboardInterrupt:
        if _debug:
            _log.debug("keyboard interrupt")
    finally:
        if app:
            app.close()


if __name__ == "__main__":
    asyncio.run(main())
