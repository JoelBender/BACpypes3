"""
Simple example that sends Read Property requests.
"""

import asyncio
from typing import Callable

from bacpypes3.debugging import ModuleLogger, bacpypes_debugging
from bacpypes3.argparse import SimpleArgumentParser

from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier, Integer, Unsigned, OctetString
from bacpypes3.apdu import ErrorRejectAbortNack
from bacpypes3.app import Application
from bacpypes3.cmd import Cmd
from bacpypes3.comm import bind
from bacpypes3.console import Console
from bacpypes3.service.file import FileServices

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# globals
app: Application | None = None


@bacpypes_debugging
class CustomApplication(Application, FileServices):
    """
    Add file services to a custom application before rolling it into the rest of
    the included services for an Application.
    """

    _debug: Callable[..., None]


@bacpypes_debugging
class SampleCmd(Cmd):
    """
    read_record and read_stream commands.
    """

    _debug: Callable[..., None]

    async def do_read_record(
        self,
        address: Address,
        object_identifier: ObjectIdentifier,
        file_start_record: Integer,
        requested_record_count: Unsigned,
    ) -> None:
        """
        usage: read_record address object_identifier file_start_record requested_record_count
        """
        if _debug:
            SampleCmd._debug(
                "do_read_record %r %r %r %r",
                address,
                object_identifier,
                file_start_record,
                requested_record_count,
            )

        try:
            (
                end_of_file,
                file_start_record,
                returned_record_count,
                file_record_data,
            ) = await app.read_record(
                address,
                object_identifier,
                file_start_record,
                requested_record_count,
            )
        except ErrorRejectAbortNack as err:
            if _debug:
                SampleCmd._debug("    - exception: %r", err)
            return

        await self.response(
            f"{end_of_file=}, {returned_record_count=}, {file_record_data=}"
        )

    async def do_write_record(
        self,
        address: Address,
        object_identifier: ObjectIdentifier,
        file_start_record: Integer,
        *record_data: str,
    ) -> None:
        """
        usage: write_record address object_identifier file_start_record [ record ... ]
        """
        if _debug:
            SampleCmd._debug(
                "do_write_record %r %r %r %r",
                address,
                object_identifier,
                file_start_record,
                record_data,
            )

        try:
            file_start_record = await app.write_record(
                address,
                object_identifier,
                file_start_record,
                [OctetString(record.encode() + b"\n") for record in record_data],
            )
        except ErrorRejectAbortNack as err:
            if _debug:
                SampleCmd._debug("    - exception: %r", err)
            return

        await self.response(f"{file_start_record=}")

    async def do_read_stream(
        self,
        address: Address,
        object_identifier: ObjectIdentifier,
        file_start_position: Integer,
        requested_octet_count: Unsigned,
    ) -> None:
        """
        usage: read_stream address object_identifier file_start_position requested_octet_count
        """
        if _debug:
            SampleCmd._debug(
                "do_read_stream %r %r %r %r",
                address,
                object_identifier,
                file_start_position,
                requested_octet_count,
            )

        try:
            end_of_file, file_start_position, file_data = await app.read_stream(
                address,
                object_identifier,
                file_start_position,
                requested_octet_count,
            )
            if _debug:
                SampleCmd._debug("    - file_data: %r", file_data)
        except ErrorRejectAbortNack as err:
            if _debug:
                SampleCmd._debug("    - exception: %r", err)
            return

        await self.response(f"{end_of_file=}, {file_start_position=}, {file_data=}")

    async def do_write_stream(
        self,
        address: Address,
        object_identifier: ObjectIdentifier,
        file_start_position: Integer,
        file_data: str,
    ) -> None:
        """
        usage: write_stream address object_identifier file_start_record file_data
        """
        if _debug:
            SampleCmd._debug(
                "do_write_stream %r %r %r %r",
                address,
                object_identifier,
                file_start_position,
                file_data,
            )

        try:
            file_start_position = await app.write_stream(
                address,
                object_identifier,
                file_start_position,
                OctetString(file_data.encode()),
            )
        except ErrorRejectAbortNack as err:
            if _debug:
                SampleCmd._debug("    - exception: %r", err)
            return

        await self.response(f"{file_start_position=}")


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
        app = CustomApplication.from_args(args)
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
