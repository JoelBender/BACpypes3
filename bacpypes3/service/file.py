from typing import List, Tuple, Union

from ..debugging import bacpypes_debugging, ModuleLogger


from ..pdu import Address
from ..primitivedata import Integer, Unsigned, OctetString, ObjectIdentifier, ObjectType
from ..basetypes import (
    FileAccessMethod,
    AtomicReadFileRequestAccessMethodChoice,
    AtomicReadFileRequestAccessMethodChoiceRecordAccess,
    AtomicReadFileRequestAccessMethodChoiceStreamAccess,
    AtomicReadFileACKAccessMethodChoice,
    AtomicReadFileACKAccessMethodRecordAccess,
    AtomicReadFileACKAccessMethodStreamAccess,
    AtomicWriteFileRequestAccessMethodChoice,
    AtomicWriteFileRequestAccessMethodChoiceRecordAccess,
    AtomicWriteFileRequestAccessMethodChoiceStreamAccess,
)
from ..apdu import (
    ErrorRejectAbortNack,
    AtomicReadFileRequest,
    AtomicReadFileACK,
    AtomicWriteFileRequest,
    AtomicWriteFileACK,
)
from ..errors import ExecutionError, MissingRequiredParameter

# some debugging
_debug = 0
_log = ModuleLogger(globals())

#
#   File Services
#


@bacpypes_debugging
class FileServices:
    async def do_AtomicReadFileRequest(self, apdu):
        """Return one of our records."""
        if _debug:
            FileServices._debug("do_AtomicReadFileRequest %r", apdu)

        if apdu.fileIdentifier[0] != ObjectType.file:
            raise ExecutionError("services", "inconsistentObjectType")

        # get the object
        obj = self.get_object_id(apdu.fileIdentifier)
        if _debug:
            FileServices._debug("    - object: %r", obj)

        if not obj:
            raise ExecutionError("object", "unknownObject")

        if apdu.accessMethod.recordAccess:
            # check against the object
            if obj.fileAccessMethod != FileAccessMethod.recordAccess:
                raise ExecutionError("services", "invalidFileAccessMethod")

            # simplify
            record_access = apdu.accessMethod.recordAccess
            if _debug:
                FileServices._debug("    - record_access: %r", record_access)

            # check for required parameters
            if record_access.fileStartRecord is None:
                raise MissingRequiredParameter("fileStartRecord required")
            if record_access.requestedRecordCount is None:
                raise MissingRequiredParameter("requestedRecordCount required")

            # pass along to the object
            end_of_file, file_start_record, file_record_data = await obj.read_record(
                record_access.fileStartRecord,
                record_access.requestedRecordCount,
            )
            if _debug:
                FileServices._debug("    - end_of_file: %r", end_of_file)
                FileServices._debug("    - file_start_record: %r", file_start_record)
                FileServices._debug("    - record_data: %r", file_record_data)

            # this is an ack
            resp = AtomicReadFileACK(
                context=apdu,
                endOfFile=end_of_file,
                accessMethod=AtomicReadFileACKAccessMethodChoice(
                    recordAccess=AtomicReadFileACKAccessMethodRecordAccess(
                        fileStartRecord=file_start_record,
                        returnedRecordCount=len(file_record_data),
                        fileRecordData=file_record_data,
                    ),
                ),
            )

        elif apdu.accessMethod.streamAccess:
            # check against the object
            if obj.fileAccessMethod != FileAccessMethod.streamAccess:
                raise ExecutionError("services", "invalidFileAccessMethod")

            # simplify
            stream_access = apdu.accessMethod.streamAccess
            if _debug:
                FileServices._debug("    - stream_access: %r", stream_access)

            # check for required parameters
            if stream_access.fileStartPosition is None:
                raise MissingRequiredParameter("fileStartPosition required")
            if stream_access.requestedOctetCount is None:
                raise MissingRequiredParameter("requestedOctetCount required")

            # pass along to the object
            end_of_file, file_start_position, file_data = await obj.read_stream(
                stream_access.fileStartPosition,
                stream_access.requestedOctetCount,
            )
            if _debug:
                FileServices._debug("    - record_data: %r", file_data)

            # this is an ack
            resp = AtomicReadFileACK(
                context=apdu,
                endOfFile=end_of_file,
                accessMethod=AtomicReadFileACKAccessMethodChoice(
                    streamAccess=AtomicReadFileACKAccessMethodStreamAccess(
                        fileStartPosition=file_start_position,
                        fileData=file_data,
                    ),
                ),
            )

        if _debug:
            FileServices._debug("    - resp: %r", resp)

        # return the result
        await self.response(resp)

    async def do_AtomicWriteFileRequest(self, apdu):
        """Return one of our records."""
        if _debug:
            FileServices._debug("do_AtomicWriteFileRequest %r", apdu)

        if apdu.fileIdentifier[0] != ObjectType.file:
            raise ExecutionError("services", "inconsistentObjectType")

        # get the object
        obj = self.get_object_id(apdu.fileIdentifier)
        if _debug:
            FileServices._debug("    - object: %r", obj)

        if not obj:
            raise ExecutionError("object", "unknownObject")

        if apdu.accessMethod.recordAccess:
            # check against the object
            if obj.fileAccessMethod != FileAccessMethod.recordAccess:
                raise ExecutionError("services", "invalidFileAccessMethod")

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
                raise ExecutionError("services", "fileAccessDenied")

            # pass along to the object
            file_start_record = await obj.write_record(
                record_access.fileStartRecord,
                record_access.recordCount,
                record_access.fileRecordData,
            )
            if _debug:
                FileServices._debug("    - file_start_record: %r", file_start_record)

            # this is an ack
            resp = AtomicWriteFileACK(
                context=apdu,
                fileStartRecord=file_start_record,
            )

        elif apdu.accessMethod.streamAccess:
            # check against the object
            if obj.fileAccessMethod != FileAccessMethod.streamAccess:
                raise ExecutionError("services", "invalidFileAccessMethod")

            # simplify
            stream_access = apdu.accessMethod.streamAccess

            # check for required parameters
            if stream_access.fileStartPosition is None:
                raise MissingRequiredParameter("fileStartPosition required")
            if stream_access.fileData is None:
                raise MissingRequiredParameter("fileData required")

            # check for read-only
            if obj.readOnly:
                raise ExecutionError("services", "fileAccessDenied")

            # pass along to the object
            start_position = await obj.write_stream(
                stream_access.fileStartPosition,
                stream_access.fileData,
            )
            if _debug:
                FileServices._debug("    - start_position: %r", start_position)

            # this is an ack
            resp = AtomicWriteFileACK(
                context=apdu,
                fileStartPosition=start_position,
            )

        if _debug:
            FileServices._debug("    - resp: %r", resp)

        # return the result
        await self.response(resp)

    async def read_record(
        self,
        address: Union[Address, str],
        objid: Union[ObjectIdentifier, str],
        file_start_record: Integer,
        requested_record_count: Unsigned,
    ) -> Tuple[bool, int, int, List[OctetString]]:
        """
        Send a record access Atomic Read File Request to an address and
        decode the response, returning the end-of-file, starting record,
        and a list of the records.
        """

        # parse the address if needed
        if isinstance(address, str):
            address = Address(address)
        elif not isinstance(address, Address):
            raise TypeError("address")

        # get the vendor information to have a context for parsing the
        # object identifier and property reference
        vendor_info = await self.get_vendor_info(device_address=address)

        # parse the object identifier if needed
        if isinstance(objid, str):
            objid = await self.parse_object_identifier(objid, vendor_info=vendor_info)
        elif not isinstance(objid, ObjectIdentifier):
            raise TypeError("objid")

        # create a request
        read_file_request = AtomicReadFileRequest(
            fileIdentifier=objid,
            accessMethod=AtomicReadFileRequestAccessMethodChoice(
                recordAccess=AtomicReadFileRequestAccessMethodChoiceRecordAccess(
                    fileStartRecord=file_start_record,
                    requestedRecordCount=requested_record_count,
                ),
            ),
            destination=address,
        )
        if _debug:
            FileServices._debug("    - read_file_request: %r", read_file_request)

        # send the request, wait for the response
        read_file_response = await self.request(read_file_request)
        if _debug:
            FileServices._debug("    - read_file_response: %r", read_file_response)
        if isinstance(read_file_response, ErrorRejectAbortNack):
            if _debug:
                FileServices._debug("    - error/reject/abort: %r", read_file_response)
            return read_file_response
        if not isinstance(read_file_response, AtomicReadFileACK):
            if _debug:
                FileServices._debug("    - invalid response: %r", read_file_response)
            return None

        access_method = read_file_response.accessMethod
        assert isinstance(access_method, AtomicReadFileACKAccessMethodChoice)
        record_access = access_method.recordAccess
        assert isinstance(record_access, AtomicReadFileACKAccessMethodRecordAccess)

        return (
            read_file_response.endOfFile,
            record_access.fileStartRecord,
            record_access.returnedRecordCount,
            record_access.fileRecordData,
        )

    async def write_record(
        self,
        address: Union[Address, str],
        objid: Union[ObjectIdentifier, str],
        file_start_record: Integer,
        file_record_data: List[OctetString],
    ) -> int:
        """
        Send a record access Atomic Write File Request to an address and
        decode the response, returning the starting record.
        """
        if _debug:
            FileServices._debug(
                "write_record %r %r %r %r",
                address,
                objid,
                file_start_record,
                file_record_data,
            )

        # parse the address if needed
        if isinstance(address, str):
            address = Address(address)
        elif not isinstance(address, Address):
            raise TypeError("address")

        # get the vendor information to have a context for parsing the
        # object identifier and property reference
        vendor_info = await self.get_vendor_info(device_address=address)

        # parse the object identifier if needed
        if isinstance(objid, str):
            objid = await self.parse_object_identifier(objid, vendor_info=vendor_info)
        elif not isinstance(objid, ObjectIdentifier):
            raise TypeError("objid")

        # create a request
        write_file_request = AtomicWriteFileRequest(
            fileIdentifier=objid,
            accessMethod=AtomicWriteFileRequestAccessMethodChoice(
                recordAccess=AtomicWriteFileRequestAccessMethodChoiceRecordAccess(
                    fileStartRecord=file_start_record,
                    recordCount=len(file_record_data),
                    fileRecordData=file_record_data,
                ),
            ),
            destination=address,
        )
        if _debug:
            FileServices._debug("    - write_file_request: %r", write_file_request)

        # send the request, wait for the response
        write_file_response = await self.request(write_file_request)
        if _debug:
            FileServices._debug("    - write_file_response: %r", write_file_response)
        if isinstance(write_file_response, ErrorRejectAbortNack):
            if _debug:
                FileServices._debug("    - error/reject/abort: %r", write_file_response)
            return write_file_response
        if not isinstance(write_file_response, AtomicWriteFileACK):
            if _debug:
                FileServices._debug("    - invalid response: %r", write_file_response)
            return None

        return write_file_response.fileStartRecord

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

        # parse the address if needed
        if isinstance(address, str):
            address = Address(address)
        elif not isinstance(address, Address):
            raise TypeError("address")

        # get the vendor information to have a context for parsing the
        # object identifier and property reference
        vendor_info = await self.get_vendor_info(device_address=address)

        # parse the object identifier if needed
        if isinstance(objid, str):
            objid = await self.parse_object_identifier(objid, vendor_info=vendor_info)
        elif not isinstance(objid, ObjectIdentifier):
            raise TypeError("objid")

        # create a request
        read_file_request = AtomicReadFileRequest(
            fileIdentifier=objid,
            accessMethod=AtomicReadFileRequestAccessMethodChoice(
                streamAccess=AtomicReadFileRequestAccessMethodChoiceStreamAccess(
                    fileStartPosition=file_start_position,
                    requestedOctetCount=requested_octet_count,
                ),
            ),
            destination=address,
        )
        if _debug:
            FileServices._debug("    - read_file_request: %r", read_file_request)

        # send the request, wait for the response
        read_file_response = await self.request(read_file_request)
        if _debug:
            FileServices._debug("    - read_file_response: %r", read_file_response)
        if isinstance(read_file_response, ErrorRejectAbortNack):
            if _debug:
                FileServices._debug("    - error/reject/abort: %r", read_file_response)
            return read_file_response
        if not isinstance(read_file_response, AtomicReadFileACK):
            if _debug:
                FileServices._debug("    - invalid response: %r", read_file_response)
            return None

        access_method = read_file_response.accessMethod
        assert isinstance(access_method, AtomicReadFileACKAccessMethodChoice)
        stream_access = access_method.streamAccess
        assert isinstance(stream_access, AtomicReadFileACKAccessMethodStreamAccess)

        return (
            read_file_response.endOfFile,
            stream_access.fileStartPosition,
            stream_access.fileData,
        )

    async def write_stream(
        self,
        address: Union[Address, str],
        objid: Union[ObjectIdentifier, str],
        file_start_position: Integer,
        file_data: OctetString,
    ) -> int:
        """
        Send a stream access Atomic Write File Request to an address and
        decode the response, returning the starting position.
        """

        # parse the address if needed
        if isinstance(address, str):
            address = Address(address)
        elif not isinstance(address, Address):
            raise TypeError("address")

        # get the vendor information to have a context for parsing the
        # object identifier and property reference
        vendor_info = await self.get_vendor_info(device_address=address)

        # parse the object identifier if needed
        if isinstance(objid, str):
            objid = await self.parse_object_identifier(objid, vendor_info=vendor_info)
        elif not isinstance(objid, ObjectIdentifier):
            raise TypeError("objid")

        # create a request
        write_file_request = AtomicWriteFileRequest(
            fileIdentifier=objid,
            accessMethod=AtomicWriteFileRequestAccessMethodChoice(
                streamAccess=AtomicWriteFileRequestAccessMethodChoiceStreamAccess(
                    fileStartPosition=file_start_position,
                    fileData=file_data,
                ),
            ),
            destination=address,
        )
        if _debug:
            FileServices._debug("    - write_file_request: %r", write_file_request)

        # send the request, wait for the response
        write_file_response = await self.request(write_file_request)
        if _debug:
            FileServices._debug("    - write_file_response: %r", write_file_response)
        if isinstance(write_file_response, ErrorRejectAbortNack):
            if _debug:
                FileServices._debug("    - error/reject/abort: %r", write_file_response)
            return write_file_response
        if not isinstance(write_file_response, AtomicWriteFileACK):
            if _debug:
                FileServices._debug("    - invalid response: %r", write_file_response)
            return None

        return write_file_response.fileStartPosition
