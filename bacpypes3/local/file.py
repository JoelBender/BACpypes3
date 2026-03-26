from itertools import chain
from typing import List, Tuple

from ..debugging import bacpypes_debugging, ModuleLogger

from ..errors import ExecutionError
from ..primitivedata import Unsigned, OctetString
from ..basetypes import DateTime
from ..object import FileObject

# some debugging
_debug = 0
_log = ModuleLogger(globals())

#
#   Local Record Access File Object Type
#


@bacpypes_debugging
class LocalRecordAccessFileObject(FileObject):
    record_data: List[str]

    def __init__(self, **kwargs):
        """Initialize a record accessed file object."""
        if _debug:
            LocalRecordAccessFileObject._debug(
                "__init__ %r",
                kwargs,
            )

        # verify the file access method or provide it
        if "fileAccessMethod" in kwargs:
            if kwargs["fileAccessMethod"] != "recordAccess":
                raise ValueError("inconsistent file access method")
        else:
            kwargs["fileAccessMethod"] = "recordAccess"

        # continue with initialization
        FileObject.__init__(self, **kwargs)

        # no records
        self.file_data = ""

    @property
    def fileSize(self) -> Unsigned:
        """Return the private value of the file size."""
        if _debug:
            LocalRecordAccessFileObject._debug("fileSize(getter)")

        return Unsigned(len(self.file_data))

    @fileSize.setter
    def fileSize(self, value: Unsigned) -> None:
        """
        Change the object name, and if it is associated with an application,
        update the application reference to this object.
        """
        if _debug:
            LocalRecordAccessFileObject._debug("fileSize(setter) %r", value)
        if (value is None) or (value < 0):
            raise ValueError("fileSize")
        if value == 0:
            self.file_data = ""
        elif value < len(self.file_data):
            self.file_data = self.file_data[:value]
        else:
            self.file_data += "\0" * (value - len(self.file_data))

        self.modificationDate = DateTime.now()

    @property
    def recordCount(self) -> Unsigned:
        """Return the number of records."""
        if _debug:
            LocalRecordAccessFileObject._debug("recordCount(getter)")

        # unpack the data as line feed terminated records
        record_data = self.file_data.splitlines(keepends=True)

        return Unsigned(len(record_data))

    @recordCount.setter
    def recordCount(self, value: Unsigned) -> None:
        """
        Change the number of records.
        """
        if _debug:
            LocalRecordAccessFileObject._debug("recordCount(setter) %r", value)
        if (value is None) or (value < 0):
            raise ValueError("recordCount")
        if value == 0:
            self.file_data = ""
        else:
            # unpack the data as line feed terminated records
            record_data = self.file_data.splitlines(keepends=True)

            if value < len(self.file_data):
                record_data = record_data[:value]
            else:
                record_data.extend(["\n"] * (value - len(record_data)))

            self.file_data = "".join(record_data)
        self.modificationDate = DateTime.now()

    async def read_record(
        self, file_start_record: int, requested_record_count: int
    ) -> Tuple[bool, int, List[OctetString]]:
        """Read a number of records starting at a specific record."""
        if _debug:
            LocalRecordAccessFileObject._debug(
                "read_record %r %r",
                file_start_record,
                requested_record_count,
            )

        # unpack the data as line feed terminated records
        record_data = self.file_data.splitlines(keepends=True)
        if _debug:
            LocalRecordAccessFileObject._debug("    - record_data: %r", record_data)

        if file_start_record < 0 or file_start_record >= len(record_data):
            raise ExecutionError("services", "invalidFileStartPosition")

        # true if the response contains the last record of the file
        end_of_file = (file_start_record + requested_record_count) >= len(record_data)

        return (
            end_of_file,
            file_start_record,
            record_data[file_start_record : file_start_record + requested_record_count],
        )

    async def write_record(
        self, file_start_record, record_count, file_record_data
    ) -> int:
        """Write a number of records, starting at a specific record."""
        if _debug:
            LocalRecordAccessFileObject._debug(
                "write_record %r %r %r",
                file_start_record,
                record_count,
                file_record_data,
            )

        # unpack the data as line feed terminated records
        record_data = self.file_data.splitlines(keepends=True)

        if file_start_record == -1:
            file_start_record = len(record_data)
            preceeding_records = record_data
            following_records = []
        else:
            if file_start_record < 0 or file_start_record > len(record_data):
                raise ExecutionError("services", "invalidFileStartPosition")

            preceeding_records = record_data[:file_start_record]

            file_end_record = file_start_record + record_count
            if file_end_record < len(record_data):
                following_records = record_data[file_end_record:]
            else:
                following_records = []

        if _debug:
            LocalRecordAccessFileObject._debug(
                "    - preceeding_records: %r", preceeding_records
            )
            LocalRecordAccessFileObject._debug(
                "    - file_record_data: %r", file_record_data
            )
            LocalRecordAccessFileObject._debug(
                "    - following_records: %r", following_records
            )

        self.file_data = b"".join(
            chain(preceeding_records, file_record_data, following_records)
        )
        self.modificationDate = DateTime.now()

        return file_start_record


#
#   Local Stream Access File Object Type
#


@bacpypes_debugging
class LocalStreamAccessFileObject(FileObject):
    stream_data: bytearray

    def __init__(self, **kwargs):
        """Initialize a stream accessed file object."""
        if _debug:
            LocalStreamAccessFileObject._debug(
                "__init__ %r",
                kwargs,
            )

        # verify the file access method or provide it
        if "fileAccessMethod" in kwargs:
            if kwargs["fileAccessMethod"] != "streamAccess":
                raise ValueError("inconsistent file access method")
        else:
            kwargs["fileAccessMethod"] = "streamAccess"

        # continue with initialization
        FileObject.__init__(self, **kwargs)

        # blob of stuff
        self.file_data = b""

    @property
    def fileSize(self) -> Unsigned:
        """Return the private value of the file size."""
        if _debug:
            LocalRecordAccessFileObject._debug("fileSize(getter)")

        return Unsigned(len(self.file_data))

    @fileSize.setter
    def fileSize(self, value: Unsigned) -> None:
        """
        Change the object name, and if it is associated with an application,
        update the application reference to this object.
        """
        if _debug:
            LocalRecordAccessFileObject._debug("fileSize(setter) %r", value)
        if (value is None) or (value < 0):
            raise ValueError("fileSize")
        if value == 0:
            self.file_data = b""
        elif value < len(self.file_data):
            self.file_data = self.file_data[:value]
        else:
            self.file_data += b"0" * (value - len(self.file_data))

        self.modificationDate = DateTime.now()

    async def read_stream(
        self, file_start_position: int, requested_octet_count: int
    ) -> Tuple[bool, int, List[OctetString]]:
        """Read a number of records starting at a specific record."""
        if _debug:
            LocalStreamAccessFileObject._debug(
                "read_stream %r %r",
                file_start_position,
                requested_octet_count,
            )
        if file_start_position < 0 or file_start_position >= len(self.file_data):
            raise ExecutionError("services", "invalidFileStartPosition")

        # true if the response contains the last octet of the file
        end_of_file = file_start_position + requested_octet_count >= len(self.file_data)

        return (
            end_of_file,
            file_start_position,
            self.file_data[
                file_start_position : file_start_position + requested_octet_count
            ],
        )

    async def write_stream(
        self, file_start_position: int, file_data: OctetString
    ) -> None:
        """Write a number of octets, starting at a specific offset."""
        if _debug:
            LocalStreamAccessFileObject._debug(
                "write_stream %r %r",
                file_start_position,
                file_data,
            )
        if file_start_position == -1:
            file_start_position = len(self.file_data)
            self.file_data += file_data
        else:
            if (file_start_position < 0) or (file_start_position > len(self.file_data)):
                raise ExecutionError("services", "invalidFileStartPosition")
            preceeding_octets = self.file_data[:file_start_position]

            file_end_position = file_start_position + len(file_data)
            if file_end_position < len(self.file_data):
                following_octets = self.file_data[file_end_position:]
            else:
                following_octets = b""

        self.file_data = preceeding_octets + file_data + following_octets
        self.modificationDate = DateTime.now()

        return file_start_position
