"""
This example reads in a tab-delimited list of DeviceAddressObjectPropertyReference
and reads them as a batch.

The text file contains:
    key                 - any simple value to identify the row
    device address      - an Address, like '192.168.0.12' or '5101:16'
    object identifier   - an ObjectIdentifier, like 'analog-value,12'
    property reference  - a PropertyReference, like 'present-value'

Note that the property reference can also include an array index like
'priority-array[6]'.
"""

import sys
import asyncio

from typing import Callable

from bacpypes3.settings import settings
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application

from bacpypes3.apdu import ErrorRejectAbortNack
from bacpypes3.lib.batchread import DeviceAddressObjectPropertyReference, BatchRead

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# globals
app: Application
batch_read: BatchRead


def callback(key: str, value: Union[float, ErrorRejectAbortNack]) -> None:
    """
    This is called when the batch has found a value or an error.  The alternative
    to using a callback is to wait for the batch to complete and zip() the
    results with the list of keys.
    """
    if isinstance(value, ErrorRejectAbortNack):
        print(f"{objprop}: {value.errorClass}, {value.errorCode}")
    else:
        print(f"{objprop} = {value}")


async def main() -> None:
    global app, batch_read

    try:
        app = None
        args = SimpleArgumentParser().parse_args()
        if _debug:
            _log.debug("settings: %r", settings)

        # build the application
        app = Application.from_args(args)

        # transform the list of stuff to read
        daopr_list = []
        while line := readline():
            line_args = line[:-1].split("\t")
            daopr_list.append(DeviceAddressObjectPropertyReference(*line_args))
        batch_read = BatchRead(daopr_list)

        # run until the batch is done
        await batch_read.run(app, callback)

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
