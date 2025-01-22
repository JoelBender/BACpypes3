#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Parsing References
-----------------------
"""

import unittest
import pytest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger

from bacpypes3.primitivedata import ObjectType, ObjectIdentifier, PropertyIdentifier
from bacpypes3.basetypes import PropertyReference
from bacpypes3.app import Application
from bacpypes3.vendor import get_vendor_info, VendorInfo

# some debugging
_debug = 0
_log = ModuleLogger(globals())


# this vendor identifier reference is used when registering proprietary classes
proprietary_vendor_id = 888


class ProprietaryObjectType(ObjectType):
    """
    This is a list of the object type enumerations for proprietary object types,
    see Clause 23.4.1.
    """

    proprietary_object = 128


class ProprietaryPropertyIdentifier(PropertyIdentifier):
    """
    This is a list of the property identifiers that are used in proprietary object
    types or are used in proprietary properties of standard types.
    """

    proprietary_property = 512


# create a VendorInfo object for this proprietary application before registering
# specialize object classes
proprietary_vendor_info = VendorInfo(
    proprietary_vendor_id, ProprietaryObjectType, ProprietaryPropertyIdentifier
)


@bacpypes_debugging
class TestStandardReferences:
    @pytest.mark.asyncio
    async def test_parse_object_identifier(self):
        if _debug:
            TestStandardReferences._debug("test_parse_object_identifier")

        # create an application
        app = Application()

        # test with a name
        object_identifier = await app.parse_object_identifier("device,1")
        assert object_identifier == (ObjectType("device"), 1)

        # test with a numeric object type reference
        object_identifier = await app.parse_object_identifier("8,2")
        assert object_identifier == (ObjectType("device"), 2)

        # test with a numeric object type reference in the vendor range
        object_identifier = await app.parse_object_identifier("128,3")
        assert object_identifier == (128, 3)

        if _debug:
            TestStandardReferences._debug("    - passed")

    @pytest.mark.asyncio
    async def test_parse_property_reference(self):
        if _debug:
            TestStandardReferences._debug("test_parse_property_reference")

        # create an application
        app = Application()

        # test without an array index
        property_reference = await app.parse_property_reference("present-value")
        assert property_reference == PropertyReference(
            propertyIdentifier=PropertyIdentifier("present-value"),
            propertyArrayIndex=None,
        )

        # test a numeric reference
        property_reference = await app.parse_property_reference("512")
        assert property_reference == PropertyReference(
            propertyIdentifier=512,
            propertyArrayIndex=None,
        )

        # test with an array index
        property_reference = await app.parse_property_reference("priority-array[1]")
        assert property_reference == PropertyReference(
            propertyIdentifier=PropertyIdentifier("priority-array"),
            propertyArrayIndex=1,
        )

        # test a numeric reference and an array index
        property_reference = await app.parse_property_reference("512[2]")
        assert property_reference == PropertyReference(
            propertyIdentifier=512,
            propertyArrayIndex=2,
        )

        if _debug:
            TestStandardReferences._debug("    - passed")


@bacpypes_debugging
class TestProprietaryReferences:
    @pytest.mark.asyncio
    async def test_parse_object_identifier(self):
        if _debug:
            TestProprietaryReferences._debug("test_parse_object_identifier")

        # create an application
        app = Application()

        # test without vendor reference
        with pytest.raises(ValueError):
            object_identifier = await app.parse_object_identifier(
                "proprietary_object,1"
            )

        # test with a name
        object_identifier = await app.parse_object_identifier(
            "proprietary_object,1", vendor_info=proprietary_vendor_info
        )
        assert object_identifier == (ProprietaryObjectType("proprietary_object"), 1)

        if _debug:
            TestProprietaryReferences._debug("    - passed")

    @pytest.mark.asyncio
    async def test_parse_property_reference(self):
        if _debug:
            TestProprietaryReferences._debug("test_parse_property_reference")

        # create an application
        app = Application()

        # test without vendor reference
        with pytest.raises(ValueError):
            property_reference = await app.parse_property_reference(
                "proprietary_property"
            )

        # test with vendor reference, without an array index
        property_reference = await app.parse_property_reference(
            "proprietary_property", vendor_info=proprietary_vendor_info
        )
        assert property_reference == PropertyReference(
            propertyIdentifier=ProprietaryPropertyIdentifier("proprietary_property"),
            propertyArrayIndex=None,
        )

        # test with vendor identifier reference, without an array index
        property_reference = await app.parse_property_reference(
            "proprietary_property", vendor_identifier=proprietary_vendor_id
        )
        assert property_reference == PropertyReference(
            propertyIdentifier=ProprietaryPropertyIdentifier("proprietary_property"),
            propertyArrayIndex=None,
        )

        if _debug:
            TestProprietaryReferences._debug("    - passed")
