"""
Simple example that creates a change-of-value context and dumps out the
property identifier and its value from the notifications it receives.

The device address and monitored object identifier are the only required
parameters to `change_of_value()`.
"""

import asyncio
import signal

from bacpypes3.debugging import ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application

from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier

# some debugging
_debug = 0
_log = ModuleLogger(globals())


async def main() -> None:
    app = None
    try:
        parser = SimpleArgumentParser()
        parser.add_argument(
            "device_address",
            help="address of the server (B-device)",
        )
        parser.add_argument(
            "object_identifier",
            help="object identifier",
        )
        parser.add_argument(
            "--process-identifier",
            help="subscriber process identifier",
        )
        parser.add_argument(
            "--confirmed",
            action="store_true",
            help="issues confirmed notifications",
        )
        parser.add_argument(
            "--lifetime",
            help="lifetime",
        )
        args = parser.parse_args()
        if _debug:
            _log.debug("args: %r", args)

        # interpret the address
        device_address = Address(args.device_address)
        if _debug:
            _log.debug("device_address: %r", device_address)

        # interpret the object identifier
        object_identifier = ObjectIdentifier(args.object_identifier)
        if _debug:
            _log.debug("object_identifier: %r", object_identifier)

        # build an application
        app = Application.from_args(args)
        if _debug:
            _log.debug("app: %r", app)

        # add a Ctrl-C signal handler to terminate the application
        fini = asyncio.Event()
        loop: asyncio.events.AbstractEventLoop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGINT, lambda: fini.set())

        try:
            # use a SubscriptionContextManager
            async with app.change_of_value(
                device_address,
                object_identifier,
                args.process_identifier,
                args.confirmed,
                args.lifetime,
            ) as scm:
                if _debug:
                    _log.debug("    - scm: %r", scm)

                # do something with what is received
                while not fini.is_set():
                    property_identifier, property_value = await scm.get_value()
                    print(f"{property_identifier} {property_value}")

            if _debug:
                _log.debug("exited context")
        except Exception as err:
            if _debug:
                _log.debug("    - exception: %r", err)
    finally:
        if app:
            app.close()


if __name__ == "__main__":
    asyncio.run(main())
