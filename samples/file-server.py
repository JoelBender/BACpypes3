"""
Simple example that has a device object and an additional custom object.
"""

import asyncio
from typing import Callable

from bacpypes3.debugging import ModuleLogger, bacpypes_debugging
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.ipv4.app import Application
from bacpypes3.local.file import (
    LocalRecordAccessFileObject,
    LocalStreamAccessFileObject,
)
from bacpypes3.service.file import FileServices

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class CustomApplication(Application, FileServices):
    """
    Add file services to a custom application before rolling it into the rest of
    the included services for an Application.
    """

    _debug: Callable[..., None]


async def main() -> None:
    app: Application | None = None
    try:
        args = SimpleArgumentParser().parse_args()
        if _debug:
            _log.debug("args: %r", args)

        # build an application
        app = CustomApplication.from_args(args)
        if _debug:
            _log.debug("app: %r", app)

        # create a local file object
        record_access_file_object = LocalRecordAccessFileObject(
            objectIdentifier=("file", 1),
            objectName="File 1",
        )
        if _debug:
            _log.debug("record_access_file_object: %r", record_access_file_object)

        app.add_object(record_access_file_object)

        # create aother local file object
        stream_access_file_object = LocalStreamAccessFileObject(
            objectIdentifier=("file", 2),
            objectName="File 2",
        )
        if _debug:
            _log.debug("stream_access_file_object: %r", stream_access_file_object)

        app.add_object(stream_access_file_object)

        # like running forever
        await asyncio.Future()

    finally:
        if app:
            app.close()


if __name__ == "__main__":
    asyncio.run(main())
