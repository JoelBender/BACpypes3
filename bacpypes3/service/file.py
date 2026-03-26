from typing import List, Tuple, Union

from ..debugging import bacpypes_debugging, ModuleLogger

from ..object import FileObject

from ..pdu import Address
from ..primitivedata import Integer, Unsigned, OctetString, ObjectIdentifier
from ..basetypes import AtomicReadFileACKAccessMethodRecordAccess, \
    AtomicReadFileACKAccessMethodStreamAccess
from ..apdu import AtomicReadFileACK, AtomicReadFileACKAccessMethodChoice, \
    AtomicReadFileACKAccessMethodStreamAccess, \
    AtomicWriteFileACK
from ..errors import ExecutionError, MissingRequiredParameter

# some debugging
_debug = 0
_log = ModuleLogger(globals())

#
#   File Services
#

@bacpypes_debugging
class FileServices:

    def do_AtomicReadFileRequest(self, apdu):
        """Return one of our records."""
        if _debug: FileServices._debug("do_AtomicReadFileRequest %r", apdu)

        if (apdu.fileIdentifier[0] != 'file'):
            raise ExecutionError('services', 'inconsistentObjectType')

        # get the object
        obj = self.get_object_id(apdu.fileIdentifier)
        if _debug: FileServices._debug("    - object: %r", obj)

        if not obj:
            raise ExecutionError('object', 'unknownObject')

        if apdu.accessMethod.recordAccess:
            # check against the object
            if obj.fileAccessMethod != 'recordAccess':
                raise ExecutionError('services', 'invalidFileAccessMethod')

            # simplify
            record_access = apdu.accessMethod.recordAccess

            # check for required parameters
            if record_access.fileStartRecord is None:
                raise MissingRequiredParameter("fileStartRecord required")
            if record_access.requestedRecordCount is None:
                raise MissingRequiredParameter("requestedRecordCount required")

            ### verify start is valid - double check this (empty files?)
            if (record_access.fileStartRecord < 0) or \
                    (record_access.fileStartRecord >= len(obj)):
                raise ExecutionError('services', 'invalidFileStartPosition')

            # pass along to the object
            end_of_file, record_data = obj.read_record(
                record_access.fileStartRecord,
                record_access.requestedRecordCount,
                )
            if _debug: FileServices._debug("    - record_data: %r", record_data)

            # this is an ack
            resp = AtomicReadFileACK(context=apdu,
                endOfFile=end_of_file,
                accessMethod=AtomicReadFileACKAccessMethodChoice(
                    recordAccess=AtomicReadFileACKAccessMethodRecordAccess(
                        fileStartRecord=record_access.fileStartRecord,
                        returnedRecordCount=len(record_data),
                        fileRecordData=record_data,
                        ),
                    ),
                )

        elif apdu.accessMethod.streamAccess:
            # check against the object
            if obj.fileAccessMethod != 'streamAccess':
                raise ExecutionError('services', 'invalidFileAccessMethod')

            # simplify
            stream_access = apdu.accessMethod.streamAccess

            # check for required parameters
            if stream_access.fileStartPosition is None:
                raise MissingRequiredParameter("fileStartPosition required")
            if stream_access.requestedOctetCount is None:
                raise MissingRequiredParameter("requestedOctetCount required")

            ### verify start is valid - double check this (empty files?)
            if (stream_access.fileStartPosition < 0) or \
                    (stream_access.fileStartPosition >= len(obj)):
                raise ExecutionError('services', 'invalidFileStartPosition')

            # pass along to the object
            end_of_file, record_data = obj.read_stream(
                stream_access.fileStartPosition,
                stream_access.requestedOctetCount,
                )
            if _debug: FileServices._debug("    - record_data: %r", record_data)

            # this is an ack
            resp = AtomicReadFileACK(context=apdu,
                endOfFile=end_of_file,
                accessMethod=AtomicReadFileACKAccessMethodChoice(
                    streamAccess=AtomicReadFileACKAccessMethodStreamAccess(
                        fileStartPosition=stream_access.fileStartPosition,
                        fileData=record_data,
                        ),
                    ),
                )

        if _debug: FileServices._debug("    - resp: %r", resp)

        # return the result
        self.response(resp)

    def do_AtomicWriteFileRequest(self, apdu):
        """Return one of our records."""
        if _debug: FileServices._debug("do_AtomicWriteFileRequest %r", apdu)

        if (apdu.fileIdentifier[0] != 'file'):
            raise ExecutionError('services', 'inconsistentObjectType')

        # get the object
        obj = self.get_object_id(apdu.fileIdentifier)
        if _debug: FileServices._debug("    - object: %r", obj)

        if not obj:
            raise ExecutionError('object', 'unknownObject')

        if apdu.accessMethod.recordAccess:
            # check against the object
            if obj.fileAccessMethod != 'recordAccess':
                raise ExecutionError('services', 'invalidFileAccessMethod')

            # simplify
            record_access = apdu.accessMethod.recordAccess

            # check for required parameters
            if record_access.fileStartRecord is None:
                raise MissingRequiredParameter("fileStartRecord required")
            if record_access.recordCount is None:
                raise MissingRequiredParameter("recordCount required")
            if record_access.fileRecordData is None:
                raise MissingRequiredParameter("fileRecordData required")

            # check for read-only
            if obj.readOnly:
                raise ExecutionError('services', 'fileAccessDenied')

            # pass along to the object
            start_record = obj.write_record(
                record_access.fileStartRecord,
                record_access.recordCount,
                record_access.fileRecordData,
                )
            if _debug: FileServices._debug("    - start_record: %r", start_record)

            # this is an ack
            resp = AtomicWriteFileACK(context=apdu,
                fileStartRecord=start_record,
                )

        elif apdu.accessMethod.streamAccess:
            # check against the object
            if obj.fileAccessMethod != 'streamAccess':
                raise ExecutionError('services', 'invalidFileAccessMethod')

            # simplify
            stream_access = apdu.accessMethod.streamAccess

            # check for required parameters
            if stream_access.fileStartPosition is None:
                raise MissingRequiredParameter("fileStartPosition required")
            if stream_access.fileData is None:
                raise MissingRequiredParameter("fileData required")

            # check for read-only
            if obj.readOnly:
                raise ExecutionError('services', 'fileAccessDenied')

            # pass along to the object
            start_position = obj.write_stream(
                stream_access.fileStartPosition,
                stream_access.fileData,
                )
            if _debug: FileServices._debug("    - start_position: %r", start_position)

            # this is an ack
            resp = AtomicWriteFileACK(context=apdu,
                fileStartPosition=start_position,
                )

        if _debug: FileServices._debug("    - resp: %r", resp)

        # return the result
        self.response(resp)

    async def read_record(
        self,
        address: Union[Address, str],
        objid: Union[ObjectIdentifier, str],
        file_start_record: Integer,
        requested_record_count: Unsigned,
    ) -> Tuple[bool, int, List[OctetString]]:
        """
        Send a record access Atomic Read File Request to an address and
        decode the response, returning the end-of-file, starting record,
        and a list of the records.
        """
        pass

    async def write_record(
        self,
        address: Union[Address, str],
        objid: Union[ObjectIdentifier, str],
        file_start_record: Integer,
        file_record_data: List[OctetString],
    ) -> int:
        """
        Send a record access Atomic Read File Request to an address and
        decode the response, returning the starting record.
        """
        pass

    async def read_stream(
        self,
        address: Union[Address, str],
        objid: Union[ObjectIdentifier, str],
        file_start_position: Integer,
        requested_octet_count: Unsigned,
    ) -> Tuple[bool, int, OctetString]:
        """
        Send a record access Atomic Read File Request to an address and
        decode the response, returning the end-of-file, starting position,
        and a the data.
        """
        pass

    async def write_stream(
        self,
        address: Union[Address, str],
        objid: Union[ObjectIdentifier, str],
        file_start_position: Integer,
        file_data: OctetString,
    ) -> int:
        """
        Send a record access Atomic Read File Request to an address and
        decode the response, returning the starting position.
        """
        pass