"""
Application Module
"""

from __future__ import annotations

import inspect
from typing import Any as _Any
from typing import Callable, Optional, Tuple, Union

from ..apdu import (
    ErrorRejectAbortNack,
    ReadPropertyACK,
    ReadPropertyMultipleACK,
    ReadPropertyMultipleRequest,
    ReadPropertyRequest,
    ReadRangeACK,
    ReadRangeRequest,
    SimpleAckPDU,
    WritePropertyRequest,
)
from ..basetypes import (
    DateTime,
    ErrorType,
    PropertyIdentifier,
    PropertyReference,
    Range,
    RangeByPosition,
    RangeBySequenceNumber,
    RangeByTime,
    ReadAccessResult,
    ReadAccessResultElement,
    ReadAccessResultElementChoice,
    ReadAccessSpecification,
)
from ..constructeddata import Any, Array, List, SequenceOf
from ..debugging import ModuleLogger, bacpypes_debugging
from ..errors import (
    ExecutionError,
    ObjectError,
    PropertyError,
    UnrecognizedService,
)
from ..object import DeviceObject
from ..pdu import Address
from ..primitivedata import Date, Null, ObjectIdentifier, Time, Unsigned
from ..vendor import VendorInfo, get_vendor_info

# some debugging
_debug = 0
_log = ModuleLogger(globals())

#
#   ReadProperty and WriteProperty Services
#


@bacpypes_debugging
class ReadWritePropertyServices:
    _debug: Callable[..., None]

    device_object: Optional[DeviceObject]
    device_info_cache: "DeviceInfoCache"  # noqa: F821

    async def read_property(
        self,
        address: Union[Address, str],
        objid: Union[ObjectIdentifier, str],
        prop: Union[PropertyIdentifier, str],
        array_index: Optional[int] = None,
    ) -> _Any:
        """
        Send a Read Property Request to an address and decode the response,
        returning just the value, or the error, reject, or abort if that
        was received.
        """
        if _debug:
            ReadWritePropertyServices._debug(
                "read_property %r %r %r %r", address, objid, prop, array_index
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

        # parse the property reference if needed
        if isinstance(prop, str):
            property_reference = await self.parse_property_reference(
                prop, vendor_info=vendor_info
            )
            prop = property_reference.propertyIdentifier
            if property_reference.propertyArrayIndex is not None:
                if array_index is not None:
                    raise ValueError("array index conflict")
                array_index = property_reference.propertyArrayIndex
        elif not isinstance(prop, PropertyIdentifier):
            raise TypeError("prop")

        # create a request
        read_property_request = ReadPropertyRequest(
            objectIdentifier=objid,
            propertyIdentifier=prop,
            destination=address,
        )
        if array_index is not None:
            read_property_request.propertyArrayIndex = array_index
        if _debug:
            ReadWritePropertyServices._debug(
                "    - read_property_request: %r", read_property_request
            )

        # send the request, wait for the response
        response = await self.request(read_property_request)
        if _debug:
            ReadWritePropertyServices._debug("    - response: %r", response)
        if isinstance(response, ErrorRejectAbortNack):
            if _debug:
                ReadWritePropertyServices._debug(
                    "    - error/reject/abort: %r", response
                )
            return response
        if not isinstance(response, ReadPropertyACK):
            if _debug:
                ReadWritePropertyServices._debug("    - invalid response: %r", response)
            return None

        # using the vendor information, look up the class
        object_class = vendor_info.get_object_class(objid[0])
        if not object_class:
            return "-no object class-"

        # now get the property type from the class
        property_type = object_class.get_property_type(prop)
        if _debug:
            ReadWritePropertyServices._debug("    - property_type: %r", property_type)
        if not property_type:
            return "-no property type-"

        # filter the array index reference
        if issubclass(property_type, Array):
            if array_index is None:
                pass
            elif array_index == 0:
                property_type = Unsigned
            else:
                property_type = property_type._subtype
            if _debug:
                ReadWritePropertyServices._debug(
                    "    - other property_type: %r", property_type
                )

        # cast it out of the Any
        property_value = response.propertyValue.cast_out(property_type)
        if _debug:
            ReadWritePropertyServices._debug(
                "    - property_value: %r %r", property_value, property_type.__class__
            )

        return property_value

    async def write_property(
        self,
        address: Union[Address, str],
        objid: Union[ObjectIdentifier, str],
        prop: Union[PropertyIdentifier, str],
        value: _Any,
        array_index: Optional[int] = None,
        priority: Optional[int] = None,
    ) -> _Any:
        """
        Send a Write Property Request to an address and expect a simple
        acknowledgement.  Return the error, reject, or abort if that
        was received.
        """
        if _debug:
            ReadWritePropertyServices._debug(
                "write_property %r %r %r %r %r %r",
                address,
                objid,
                prop,
                value,
                array_index,
                priority,
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

        # parse the property reference if needed
        if isinstance(prop, str):
            property_reference = await self.parse_property_reference(
                prop, vendor_info=vendor_info
            )
            prop = property_reference.propertyIdentifier
            if property_reference.propertyArrayIndex is not None:
                if array_index is not None:
                    raise ValueError("array index conflict")
                array_index = property_reference.propertyArrayIndex
        elif not isinstance(prop, PropertyIdentifier):
            raise TypeError("prop")

        # using the vendor information, look up the class
        object_class = vendor_info.get_object_class(objid[0])
        if not object_class:
            return "-no object class-"

        # now get the property type from the class
        property_type = object_class.get_property_type(prop)
        if not property_type:
            return "-no property type-"

        if issubclass(property_type, Array):
            if array_index is None:
                pass
            elif array_index == 0:
                property_type = Unsigned
            else:
                property_type = property_type._subtype
            if _debug:
                ReadWritePropertyServices._debug(
                    "    - other property_type: %r", property_type
                )
        if _debug:
            ReadWritePropertyServices._debug("    - property_type: %r", property_type)

        # cast it as the appropriate type if necessary
        if (priority is not None) and isinstance(value, Null):
            pass
        elif not isinstance(value, property_type):
            if _debug:
                ReadWritePropertyServices._debug("    - cast: %r", value)
            value = property_type(value)

        # build a request
        write_property_request = WritePropertyRequest(
            objectIdentifier=objid,
            propertyIdentifier=prop,
            propertyValue=value,
            destination=address,
        )
        if array_index is not None:
            write_property_request.propertyArrayIndex = array_index
        if priority is not None:
            write_property_request.priority = priority
        if _debug:
            ReadWritePropertyServices._debug(
                "    - write_property_request: %r", write_property_request
            )

        # send the request and wait for the response
        response = await self.request(write_property_request)
        if _debug:
            ReadWritePropertyServices._debug("    - response: %r", response)
        if isinstance(response, ErrorRejectAbortNack):
            if _debug:
                ReadWritePropertyServices._debug(
                    "    - error/reject/abort: %r", response
                )
            return response
        if not isinstance(response, SimpleAckPDU):
            if _debug:
                ReadWritePropertyServices._debug("    - invalid response: %r", response)
            return None

        return None

    async def do_ReadPropertyRequest(self, apdu: ReadPropertyRequest) -> None:
        """Return the value of some property of one of our objects."""
        if _debug:
            ReadWritePropertyServices._debug("do_ReadPropertyRequest %r", apdu)

        # extract the object identifier
        objId = apdu.objectIdentifier

        # check for wildcard
        if (objId == ("device", 4194303)) and self.device_object is not None:
            if _debug:
                ReadWritePropertyServices._debug("    - wildcard device identifier")
            objId = self.device_object.objectIdentifier

        # get the object
        obj = self.get_object_id(objId)
        if not obj:
            raise ExecutionError(errorClass="object", errorCode="unknownObject")
        if _debug:
            ReadWritePropertyServices._debug("    - object: %r", obj)

        # get the value
        try:
            value = await obj.read_property(
                apdu.propertyIdentifier, apdu.propertyArrayIndex
            )
            if _debug:
                ReadWritePropertyServices._debug("    - value: %r", value)

            # if it is None then the property is defined but isn't there
            if value is None:
                raise PropertyError(errorCode="unknownProperty")
        except AttributeError:
            # exception if this is not a defined property
            raise PropertyError(errorCode="unknownProperty")

        # build a response
        resp = ReadPropertyACK(
            objectIdentifier=objId,
            propertyIdentifier=apdu.propertyIdentifier,
            propertyArrayIndex=apdu.propertyArrayIndex,
            propertyValue=value,
            context=apdu,
        )

        # return the result
        await self.response(resp)

    async def do_WritePropertyRequest(self, apdu: WritePropertyRequest) -> None:
        """Change the value of some property of one of our objects."""
        if _debug:
            ReadWritePropertyServices._debug("do_WritePropertyRequest %r", apdu)

        # get the object
        obj = self.get_object_id(apdu.objectIdentifier)
        if not obj:
            raise ExecutionError(errorClass="object", errorCode="unknownObject")
        if _debug:
            ReadWritePropertyServices._debug("    - object: %r", obj)

        # get the property type
        property_type = obj.get_property_type(apdu.propertyIdentifier)
        if _debug:
            ReadWritePropertyServices._debug("    - property_type: %r", property_type)

        array_index = apdu.propertyArrayIndex
        priority = apdu.priority

        if issubclass(property_type, Array):
            if array_index is None:
                pass
            elif array_index == 0:
                property_type = Unsigned
            else:
                property_type = property_type._subtype
            if _debug:
                ReadWritePropertyServices._debug(
                    "    - other property_type: %r", property_type
                )

        # decode the property value, and null is acceptable when commanding a
        # a point
        property_value = apdu.propertyValue.cast_out(
            property_type, null=(priority is not None)
        )
        if _debug:
            ReadWritePropertyServices._debug(
                "    - property_value: %r %r", property_value, property_value.__class__
            )

        # change the value
        await obj.write_property(
            apdu.propertyIdentifier, property_value, array_index, priority
        )
        if _debug:
            ReadWritePropertyServices._debug("    - success")

        # success
        resp = SimpleAckPDU(context=apdu)
        if _debug:
            ReadWritePropertyServices._debug("    - resp: %r", resp)

        # return the result
        await self.response(resp)


#
#   ReadWritePropertyMultipleServices
#


@bacpypes_debugging
async def read_property_to_any(obj, propertyIdentifier, propertyArrayIndex=None):
    """Read the specified property of the object, with the optional array index,
    and cast the result into an Any object."""
    if _debug:
        read_property_to_any._debug(
            "read_property_to_any %s %r %r", obj, propertyIdentifier, propertyArrayIndex
        )

    try:
        # get the value
        value = await obj.read_property(propertyIdentifier, propertyArrayIndex)
        if _debug:
            read_property_to_any._debug("    - value: %r", value)

        # property could be there, but it's not
        if value is None:
            raise PropertyError(errorCode="unknownProperty")
    except AttributeError:
        raise PropertyError(errorCode="unknownProperty")

    # get the datatype
    datatype = obj.get_property_type(propertyIdentifier)
    if _debug:
        read_property_to_any._debug("    - datatype: %r", datatype)
    if datatype is None:
        raise PropertyError(errorCode="datatypeNotSupported")

    # encode the value
    result = Any(value)
    if _debug:
        read_property_to_any._debug("    - result: %r", result)

    # return the object
    return result


@bacpypes_debugging
async def read_property_to_result_element(
    obj, propertyIdentifier, propertyArrayIndex=None
):
    """Read the specified property of the object, with the optional array index,
    and cast the result into an Any object."""
    if _debug:
        read_property_to_result_element._debug(
            "read_property_to_result_element %s %r %r",
            obj,
            propertyIdentifier,
            propertyArrayIndex,
        )

    # save the result in the property value
    read_result = ReadAccessResultElementChoice()

    if not obj:
        read_result.propertyAccessError = ErrorType(
            errorClass="object", errorCode="unknownObject"
        )
    else:
        try:
            read_result.propertyValue = await read_property_to_any(
                obj, propertyIdentifier, propertyArrayIndex
            )
            if _debug:
                read_property_to_result_element._debug("    - success")
        except ExecutionError as error:
            if _debug:
                read_property_to_result_element._debug("    - error: %r", error)
            read_result.propertyAccessError = ErrorType(
                errorClass=error.errorClass, errorCode=error.errorCode
            )

    # make an element for this value
    read_access_result_element = ReadAccessResultElement(
        propertyIdentifier=propertyIdentifier,
        propertyArrayIndex=propertyArrayIndex,
        readResult=read_result,
    )
    if _debug:
        read_property_to_result_element._debug(
            "    - read_access_result_element: %r", read_access_result_element
        )

    # fini
    return read_access_result_element


@bacpypes_debugging
class ReadWritePropertyMultipleServices:
    _debug: Callable[..., None]

    device_object: Optional[DeviceObject]
    device_info_cache: "DeviceInfoCache"  # noqa: F821

    async def read_property_multiple(
        self,
        address: Address,
        parameter_list: List[
            Tuple[
                Union[ObjectIdentifier, str],
                List[Union[PropertyReference, PropertyIdentifier, str]],
            ],
        ],
        vendor_info: Optional[VendorInfo] = None,
    ) -> List[Tuple[ObjectIdentifier, PropertyIdentifier, Union[int, None], _Any]]:
        if _debug:
            ReadWritePropertyMultipleServices._debug(
                "read_property_multiple %r %r", address, parameter_list
            )

        # parse the address if needed
        if isinstance(address, str):
            address = Address(address)
        elif not isinstance(address, Address):
            raise TypeError("address")

        # if the vendor information was provided, use it, otherwise get the
        # device information based on its address and look up the vendor
        # information from that
        if not vendor_info:
            vendor_info = await self.get_vendor_info(device_address=address)
            if _debug:
                ReadWritePropertyMultipleServices._debug(
                    "    - vendor_info: %r", vendor_info
                )

        list_of_read_access_specs = []
        while parameter_list:
            read_access_spec = ReadAccessSpecification()
            list_of_read_access_specs.append(read_access_spec)

            object_identifier, property_reference_list, *parameter_list = parameter_list

            # parse the object identifier if needed
            if isinstance(object_identifier, str):
                object_identifier = await self.parse_object_identifier(
                    object_identifier, vendor_info=vendor_info
                )
            elif not isinstance(object_identifier, ObjectIdentifier):
                raise TypeError("objid")
            if _debug:
                ReadWritePropertyMultipleServices._debug(
                    "    - object_identifier: %r", object_identifier
                )
            read_access_spec.objectIdentifier = object_identifier

            list_of_property_references = []
            for property_reference in property_reference_list:
                if _debug:
                    ReadWritePropertyMultipleServices._debug(
                        "    - property_reference: %r", property_reference
                    )

                # parse the property reference if needed
                if isinstance(property_reference, PropertyReference):
                    property_reference = property_reference
                elif isinstance(property_reference, PropertyIdentifier):
                    property_reference = PropertyReference(
                        propertyIdentifier=property_reference
                    )
                elif isinstance(property_reference, str):
                    property_reference = await self.parse_property_reference(
                        property_reference, vendor_info=vendor_info
                    )
                else:
                    raise TypeError("property_reference")
                if _debug:
                    ReadWritePropertyMultipleServices._debug(
                        "    - property_reference: %r", property_reference
                    )
                list_of_property_references.append(property_reference)

            read_access_spec.listOfPropertyReferences = list_of_property_references

        if len(list_of_read_access_specs) == 0:
            raise TypeError("read access specification expected")

        read_property_multiple_request = ReadPropertyMultipleRequest(
            listOfReadAccessSpecs=SequenceOf(ReadAccessSpecification)(
                list_of_read_access_specs
            ),
            destination=address,
        )
        if _debug:
            ReadWritePropertyMultipleServices._debug(
                "    - read_property_multiple_request: %r",
                read_property_multiple_request,
            )

        # send the request, wait for the response
        response = await self.request(read_property_multiple_request)
        if _debug:
            ReadWritePropertyServices._debug("    - response: %r", response)
        if isinstance(response, ErrorRejectAbortNack):
            if _debug:
                ReadWritePropertyMultipleServices._debug(
                    "    - error/reject/abort: %r", response
                )
            return response
        if not isinstance(response, ReadPropertyMultipleACK):
            if _debug:
                ReadWritePropertyMultipleServices._debug(
                    "    - invalid response: %r", response
                )
            return None

        # build up a list of results
        result_list = []
        for read_access_result in response.listOfReadAccessResults:
            if _debug:
                ReadWritePropertyMultipleServices._debug(
                    "    - read_access_result: %r", read_access_result
                )

            # get the object class
            object_identifier = read_access_result.objectIdentifier
            object_class = vendor_info.get_object_class(object_identifier[0])

            for read_access_result_element in read_access_result.listOfResults:
                if _debug:
                    ReadWritePropertyMultipleServices._debug(
                        "    - read_access_result_element: %r",
                        read_access_result_element,
                    )

                property_identifier = read_access_result_element.propertyIdentifier
                property_array_index = read_access_result_element.propertyArrayIndex
                read_result = read_access_result_element.readResult

                if read_result.propertyAccessError:
                    result_list.append(
                        (
                            object_identifier,
                            property_identifier,
                            property_array_index,
                            read_result.propertyAccessError,
                        )
                    )
                    continue

                # get the datatype
                property_type = object_class.get_property_type(property_identifier)
                if _debug:
                    ReadWritePropertyMultipleServices._debug(
                        "    - property_type: %r", property_type
                    )
                if property_type is None:
                    ReadWritePropertyMultipleServices._warning(
                        "%r not supported", property_identifier
                    )
                    result_list.append(
                        (
                            object_identifier,
                            property_identifier,
                            property_array_index,
                            None,
                        )
                    )
                    continue

                if issubclass(property_type, Array):
                    if property_array_index is None:
                        pass
                    elif property_array_index == 0:
                        property_type = Unsigned
                    else:
                        property_type = property_type._subtype
                    if _debug:
                        ReadWritePropertyMultipleServices._debug(
                            "    - other property_type: %r", property_type
                        )

                property_value = read_result.propertyValue.cast_out(property_type)
                if _debug:
                    ReadWritePropertyMultipleServices._debug(
                        "    - property_value: %r %r",
                        property_value,
                        property_value.__class__,
                    )

                result_list.append(
                    (
                        object_identifier,
                        property_identifier,
                        property_array_index,
                        property_value,
                    )
                )

        # return the list of results
        return result_list

    async def do_ReadPropertyMultipleRequest(
        self, apdu: ReadPropertyMultipleRequest
    ) -> None:
        """Respond to a ReadPropertyMultiple Request."""
        if _debug:
            ReadWritePropertyMultipleServices._debug(
                "do_ReadPropertyMultipleRequest %r", apdu
            )

        # first pass - make sure all of the objects exist
        object_reference_exists = False
        for read_access_spec in apdu.listOfReadAccessSpecs:
            # get the object identifier
            object_identifier = read_access_spec.objectIdentifier
            if _debug:
                ReadWritePropertyMultipleServices._debug(
                    "    - object_identifier: %r", object_identifier
                )

            # check for wildcard
            if (
                object_identifier == ("device", 4194303)
            ) and self.device_object is not None:
                if _debug:
                    ReadWritePropertyMultipleServices._debug(
                        "    - wildcard device identifier"
                    )
                object_identifier = self.device_object.objectIdentifier

            # get the object
            obj = self.get_object_id(object_identifier)
            if _debug:
                ReadWritePropertyMultipleServices._debug("    - object: %r", obj)

            if obj:
                object_reference_exists = True

        if not object_reference_exists:
            raise ObjectError("unknown-object")
        if _debug:
            ReadWritePropertyMultipleServices._debug("    - all objects exist")

        # response is a list of read access results (or an error)
        resp = None
        read_access_result_list = []

        # loop through the request
        for read_access_spec in apdu.listOfReadAccessSpecs:
            # get the object identifier
            object_identifier = read_access_spec.objectIdentifier
            if _debug:
                ReadWritePropertyMultipleServices._debug(
                    "    - object_identifier: %r", object_identifier
                )

            # check for wildcard
            if (
                object_identifier == ("device", 4194303)
            ) and self.device_object is not None:
                if _debug:
                    ReadWritePropertyMultipleServices._debug(
                        "    - wildcard device identifier"
                    )
                object_identifier = self.device_object.objectIdentifier

            # get the object
            obj = self.get_object_id(object_identifier)
            if _debug:
                ReadWritePropertyMultipleServices._debug("    - object: %r", obj)

            # build a list of result elements
            read_access_result_element_list = []

            # loop through the property references
            for prop_reference in read_access_spec.listOfPropertyReferences:
                # get the property identifier
                propertyIdentifier = prop_reference.propertyIdentifier
                if _debug:
                    ReadWritePropertyMultipleServices._debug(
                        "    - propertyIdentifier: %r", propertyIdentifier
                    )

                # get the array index (optional)
                propertyArrayIndex = prop_reference.propertyArrayIndex
                if _debug:
                    ReadWritePropertyMultipleServices._debug(
                        "    - propertyArrayIndex: %r", propertyArrayIndex
                    )

                # make a set of the required properties
                required_properties = set()
                for cls in reversed(obj.__class__.__mro__):
                    if hasattr(cls, "_required"):
                        required_properties = required_properties.union(
                            set(cls._required)
                        )
                if _debug:
                    ReadWritePropertyMultipleServices._debug(
                        "    - required_properties: %r", required_properties
                    )

                if propertyIdentifier == PropertyIdentifier.all:
                    property_set = set(obj._elements.keys())
                    propertyArrayIndex = None
                    if "propertyList" in property_set:
                        property_set.remove("propertyList")

                elif propertyIdentifier == PropertyIdentifier.required:
                    property_set = set(obj._elements.keys()).intersection(
                        required_properties
                    )
                    propertyArrayIndex = None
                    if "propertyList" in property_set:
                        property_set.remove("propertyList")

                elif propertyIdentifier == PropertyIdentifier.optional:
                    property_set = set(obj._elements.keys()).difference(
                        required_properties
                    )
                    propertyArrayIndex = None
                else:
                    property_set = set([propertyIdentifier.attr])
                if _debug:
                    ReadWritePropertyMultipleServices._debug(
                        "    - property_set: %r", property_set
                    )

                if len(property_set) == 1:
                    # read the specific property
                    read_access_result_element = await read_property_to_result_element(
                        obj, propertyIdentifier, propertyArrayIndex
                    )
                    if _debug:
                        ReadWritePropertyMultipleServices._debug(
                            "    - read_access_result_element: %r",
                            read_access_result_element,
                        )

                    # add it to the list
                    read_access_result_element_list.append(read_access_result_element)
                else:
                    for propId in property_set:
                        # get the value without triggering functions
                        value = inspect.getattr_static(obj, propId, None)
                        if value is None:
                            continue

                        # read the specific property
                        read_access_result_element = (
                            await read_property_to_result_element(
                                obj, propId, propertyArrayIndex
                            )
                        )
                        if _debug:
                            ReadWritePropertyMultipleServices._debug(
                                "    - read_access_result_element: %r",
                                read_access_result_element,
                            )
                        if read_access_result_element.readResult.propertyAccessError:
                            if _debug:
                                ReadWritePropertyMultipleServices._debug(
                                    "    - propertyAccessError: %r",
                                    read_access_result_element.readResult.propertyAccessError,
                                )
                            continue

                        # add it to the list
                        read_access_result_element_list.append(
                            read_access_result_element
                        )

            # build a read access result
            read_access_result = ReadAccessResult(
                objectIdentifier=object_identifier,
                listOfResults=read_access_result_element_list,
            )
            if _debug:
                ReadWritePropertyMultipleServices._debug(
                    "    - read_access_result: %r", read_access_result
                )

            # add it to the list
            read_access_result_list.append(read_access_result)

        # this is a ReadPropertyMultiple ack
        if not resp:
            resp = ReadPropertyMultipleACK(
                listOfReadAccessResults=read_access_result_list,
                context=apdu,
            )
            if _debug:
                ReadWritePropertyMultipleServices._debug("    - resp: %r", resp)

        # return the result
        await self.response(resp)

    def do_WritePropertyMultipleRequest(self, apdu):
        """Respond to a WritePropertyMultiple Request."""
        if _debug:
            ReadWritePropertyMultipleServices._debug(
                "do_WritePropertyMultipleRequest %r", apdu
            )

        raise UnrecognizedService()


@bacpypes_debugging
class ReadRangeServices:
    _debug: Callable[..., None]

    device_object: Optional[DeviceObject]
    device_info_cache: "DeviceInfoCache"  # noqa: F821

    async def read_range(
        self,
        address: Address,
        objid: ObjectIdentifier,
        prop: PropertyIdentifier,
        arr_index: Optional[int] = None,
        range_params: tuple = None,
    ) -> _Any:
        """
        Send a Read Range Request to an address and decode the response,
        returning the sequence, or the error, reject, or abort if that
        was received.

        :param args: String with <addr> <type> <inst> <prop> [ <indx> ]
        :param range_params: parameters defining how to query the range, a list of five elements
        :returns: data read from device (list of LogRecords)

        range_params: a list of five elements: (range_type: str, first: int, date: str, time: str, count: int)
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
            ReadRangeServices._debug(
                "read_range %r %r %r %r", address, objid, prop, range
            )

        # create a request
        read_range_request = ReadRangeRequest(
            objectIdentifier=objid,
            propertyIdentifier=prop,
            destination=address,
        )

        read_range_request.pduDestination = address
        if read_range_request is not None:
            range_type, first, date, time, count = range_params
            if range_type == "p":
                rbp = RangeByPosition(referenceIndex=int(first), count=int(count))
                read_range_request.range = Range(byPosition=rbp)
            elif range_type == "s":
                rbs = RangeBySequenceNumber(
                    referenceSequenceNumber=int(first), count=int(count)
                )
                read_range_request.range = Range(bySequenceNumber=rbs)
            elif range_type == "t":
                rbt = RangeByTime(
                    referenceTime=DateTime(date=Date(date), time=Time(time)),
                    count=int(count),
                )
                read_range_request.range = Range(byTime=rbt)
            elif range_type == "x":
                # should be missing required parameter
                read_range_request.range = Range()
            else:
                raise ValueError(f"unknown range type: {range_type!r}")

        if arr_index is not None:
            read_range_request.propertyArrayIndex = arr_index

        if _debug:
            ReadRangeServices._debug("    - read_range_request: %r", read_range_request)

        # send the request, wait for the response
        response = await self.request(read_range_request)
        if _debug:
            ReadRangeServices._debug("    - response: %r", response)
        if isinstance(response, ErrorRejectAbortNack):
            if _debug:
                ReadRangeServices._debug("    - error/reject/abort: %r", response)
            return response
        if not isinstance(response, ReadRangeACK):
            if _debug:
                ReadRangeServices._debug("    - invalid response: %r", response)
            return None

        # get information about the device from the cache
        device_info = await self.device_info_cache.get_device_info(address)
        if _debug:
            ReadWritePropertyServices._debug("    - device_info: %r", device_info)

        # using the device info, look up the vendor information
        if device_info:
            vendor_info = get_vendor_info(device_info.vendor_identifier)
        else:
            vendor_info = get_vendor_info(0)

        if _debug:
            ReadWritePropertyServices._debug(
                "    - vendor_info (%d): %r", vendor_info.vendor_identifier, vendor_info
            )

        # using the vendor information, look up the class
        object_class = vendor_info.get_object_class(response.objectIdentifier[0])
        if not object_class:
            return "-no object class-"

        # now get the property type from the class
        property_type = object_class.get_property_type(response.propertyIdentifier)
        if _debug:
            ReadRangeServices._debug("    - property_type: %r", property_type)
        if not property_type:
            return "-no property type-"

        # cast it out of the Any
        property_value = response.itemData.cast_out(property_type)
        if _debug:
            ReadRangeServices._debug(
                "    - property_value: %r %r", property_value, property_type.__class__
            )

        return property_value

    async def do_ReadRangeRequest(self, apdu: ReadRangeRequest) -> None:
        """Return the value of some property of one of our objects."""
        if _debug:
            ReadRangeServices._debug("do_ReadRangeRequest %r", apdu)

        raise NotImplementedError()

    """
    TODO : Make that better
        # extract the object identifier
        objId = apdu.objectIdentifier

        # get the object
        obj = self.get_object_id(objId)
        if not obj:
            raise ExecutionError(errorClass="object", errorCode="unknownObject")

        if _debug:
            ReadRangeServices._debug("    - object: %r", obj)

        # get the datatype
        datatype = obj.get_property_type(apdu.propertyIdentifier)
        if _debug:
            ReadRangeServices._debug("    - datatype: %r", datatype)

        # must be a list, or an array of lists
        if issubclass(datatype, List):
            pass
        elif (
            (apdu.propertyArrayIndex is not None)
            and issubclass(datatype, Array)
            and issubclass(datatype.subtype, List)
        ):
            pass
        else:
            raise ExecutionError(errorClass="property", errorCode="propertyIsNotAList")

        # get the value
        if _debug:
            ReadRangeServices._debug(apdu.__dict__)
        try:
            value = await obj.read_property(
                apdu.propertyIdentifier, apdu.propertyArrayIndex
            )

            if _debug:
                ReadRangeServices._debug(
                    f"    - value: {value.__repr__()} | of type {type(value)}"
                )
            if value is None:
                raise PropertyError(errorCode="unknownProperty")
            if isinstance(value, List):
                ReadRangeServices._debug(
                    "    - value is a list of: %r", datatype.subtype
                )
                # datatype = datatype.subtype

            if apdu.range.byPosition:
                range_by_position = apdu.range.byPosition
                if _debug:
                    ReadRangeServices._debug(
                        "    - range_by_position: %r", range_by_position
                    )

            elif apdu.range.bySequenceNumber:
                range_by_sequence_number = apdu.range.bySequenceNumber
                if _debug:
                    ReadRangeServices._debug(
                        "    - range_by_sequence_number: %r", range_by_sequence_number
                    )

            elif apdu.range.byTime:
                range_by_time = apdu.range.byTime
                if _debug:
                    ReadRangeServices._debug("    - range_by_time: %r", range_by_time)

            else:
                raise RejectException("missingRequiredParameter")
        except AttributeError:
            # exception if this is not a defined property
            raise PropertyError(errorCode="unknownProperty")
        # this is an ack
        resp = ReadRangeACK(context=apdu)
        resp.objectIdentifier = objId
        resp.propertyIdentifier = apdu.propertyIdentifier
        resp.propertyArrayIndex = apdu.propertyArrayIndex

        resp.resultFlags = [1, 1, 0]
        resp.itemCount = len(value)

        # save the result in the item data
        item_data = SequenceOf(Any)()
        item_data.cast_in(value)
        resp.itemData = item_data
        if _debug:
            ReadRangeServices._debug("    - itemData : %r", resp.itemData)
            ReadRangeServices._debug("    - resp: %r", resp)
        self.response(resp)

        # return the result
        await self.response(resp)
"""
