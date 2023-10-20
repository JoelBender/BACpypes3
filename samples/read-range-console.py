"""
Simple example that sends Read Property requests.
"""

import asyncio
import re
from typing import Callable, List, Optional

from bacpypes3.apdu import ErrorRejectAbortNack
from bacpypes3.app import Application
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.cmd import Cmd
from bacpypes3.comm import bind
from bacpypes3.console import Console
from bacpypes3.constructeddata import AnyAtomic
from bacpypes3.debugging import ModuleLogger, bacpypes_debugging
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# 'property[index]' matching
property_index_re = re.compile(r"^([0-9A-Za-z-]+)(?:\[([0-9]+)\])?$")

# globals
app: Application


@bacpypes_debugging
class SampleCmd(Cmd):
    """
    Sample Cmd
    """

    _debug: Callable[..., None]

    async def do_read_range(
        self,
        address: Address,
        object_identifier: ObjectIdentifier,
        property_identifier: str,
        _type: str = "t",
        first: str = None,
        date: str = "2023-10-18",
        time: str = "10:00:00",
        count: int = -2,
        # arr_index: Optional[int] = None
    ) -> None:
        """
        usage: read_range address object_identifier property_identifier type first date time count

        ex.

        range_params=('t', None, '2023-10-18', '10:00:00', -2)
        range_type: one of ['p', 's', 't']
                        p - RangeByPosition:
                                uses (first, count)
                        s - RangeBySequenceNumber:
                                uses (first, count)
                        t - RangeByTime: Filter by the given time
                                uses (date, time, count)
            first: int, first element when querying by Position or Sequence Number
            date: str, "YYYY-mm-DD" passed to bacpypes.primitivedata.Date constructor
            time: str, "HH:MM:SS" passed to bacpypes.primitivedata.Time constructor
            count: int, number of elements to return, negative numbers reverse direction of search

        """
        if _debug:
            SampleCmd._debug(
                "do_read_range %r %r %r",
                address,
                object_identifier,
                property_identifier,
                (_type, first, date, time, count),
            )

        try:
            property_value = await app.read_range(
                address,
                object_identifier,
                property_identifier,
                range_params=(_type, first, date, time, count),
            )
            if _debug:
                SampleCmd._debug("    - property_value: %r", property_value)
        except ErrorRejectAbortNack as err:
            if _debug:
                SampleCmd._debug("    - exception: %r", err)
            property_value = err

        if isinstance(property_value, AnyAtomic):
            if _debug:
                SampleCmd._debug("    - schedule objects")
            property_value = property_value.get_value()

        await self.response(str(property_value))


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
        cmd = SampleCmd()
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
