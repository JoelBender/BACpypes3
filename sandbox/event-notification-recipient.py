"""
Event Notification Recipient
"""

import asyncio

from typing import Callable

from bacpypes3.debugging import ModuleLogger, bacpypes_debugging
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.apdu import SimpleAckPDU
from bacpypes3.app import Application

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class EventRecipientApplication(Application):
    """
    Event Recipient Application
    """

    _debug: Callable[..., None]

    async def do_ConfirmedEventNotificationRequest(self, apdu):
        print("ConfirmedEventNotificationRequest")
        apdu.debug_contents()

        await self.response(SimpleAckPDU(context=apdu))

    async def do_UnconfirmedEventNotificationRequest(self, apdu):
        print("UnconfirmedEventNotificationRequest")
        apdu.debug_contents()


async def main() -> None:
    app = None
    try:
        args = SimpleArgumentParser().parse_args()
        if _debug:
            _log.debug("args: %r", args)

        # build an application
        app = EventRecipientApplication.from_args(args)
        if _debug:
            _log.debug("app: %r", app)

        # like running forever
        await asyncio.Future()

    finally:
        if app:
            app.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        if _debug:
            _log.debug("keyboard interrupt")
