"""
This example reads in a CVS list of DeviceAddressObjectPropertyReference
and reads them as a batch.

The text file contains:
    key                 - any simple value to identify the row
    device address      - an Address, like '192.168.0.12' or '5101:16'
    object identifier   - an ObjectIdentifier, like 'analog-value,12'
    property reference  - a PropertyReference, like 'present-value'

The property reference can also include an array index like 'priority-array[6]'.
"""

import sys
import asyncio

from typing import Union

from bacpypes3.settings import settings
from bacpypes3.debugging import ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application

from bacpypes3.apdu import ErrorRejectAbortNack
from bacpypes3.lib.batchread import DeviceAddressObjectPropertyReference, BatchRead
from bacpypes3.pdu import Address

import csv

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
        print(f"{key}: {value.errorClass}, {value.errorCode}")
    else:
        print(f"{key} = {value}")


async def main() -> None:
    global app, batch_read

    try:
        app = None
        parser = SimpleArgumentParser()

        # MB: added file to arguments
        parser.add_argument(
            "file", type=str, help="path to csv file with list of items read"
        )

        args = parser.parse_args()
        if _debug:
            _log.debug("settings: %r", settings)

        # build the application
        app = Application.from_args(args)

        # transform the list of stuff to read
        daopr_list = []

        # MB: read from file
        with open(args.file) as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                daopr_list.append(DeviceAddressObjectPropertyReference(*row))
        batch_read = BatchRead(daopr_list)

        # run until the batch is done
        await batch_read.run(app, callback)

    except KeyboardInterrupt:
        if _debug:
            _log.debug("keyboard interrupt")
    finally:
        if app:
            app.close()


if __name__ == "__main__":
    asyncio.run(main())
