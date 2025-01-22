"""
Vendor
"""

# mypy: ignore-errors

from __future__ import annotations

import warnings

from typing import (
    Callable,
    Dict,
    Optional,
    Tuple,
)

from .debugging import ModuleLogger, DebugContents, bacpypes_debugging
from .primitivedata import ObjectIdentifier, ObjectType, PropertyIdentifier

# some debugging
_debug = 0
_log = ModuleLogger(globals())


#
#   VendorInfo
#


ASHRAE_vendor_info: VendorInfo
_vendor_info: Dict[int, VendorInfo] = {}


def get_vendor_info(vendor_identifier: int) -> VendorInfo:
    global _vendor_info, ASHRAE_vendor_info

    return _vendor_info.get(vendor_identifier, ASHRAE_vendor_info)


@bacpypes_debugging
class VendorInfo(DebugContents):
    _debug: Callable[..., None]
    _debug_contents: Tuple[str, ...] = (
        "vendor_identifier",
        "object_type",
        "object_identifier",
        "property_identifier",
    )

    vendor_identifier: int
    registered_object_classes: Dict[int, type] = {}

    object_type: type
    object_identifier: type
    property_identifier: type

    def __init__(
        self,
        vendor_identifier: int,
        object_type: Optional[type] = None,
        property_identifier: Optional[type] = None,
    ) -> None:
        if _debug:
            VendorInfo._debug("__init__ %r ...", vendor_identifier)
        global _vendor_info

        # put this in the global map
        if vendor_identifier in _vendor_info:
            raise RuntimeError(
                f"vendor identifier already registered: {vendor_identifier!r}"
            )
        _vendor_info[vendor_identifier] = self

        self.vendor_identifier = vendor_identifier
        self.registered_object_classes = {}

        # reference the object type class
        if object_type:
            self.object_type = object_type

            # build an object identifier class with the specialized object type
            self.object_identifier = type(
                "ObjectIdentifier!",
                (ObjectIdentifier,),
                {
                    "_vendor_id": vendor_identifier,
                    "object_type_class": object_type,
                },
            )
        else:
            self.object_type = ObjectType
            self.object_identifier = ObjectIdentifier

        # there might be special property identifiers
        self.property_identifier = property_identifier or PropertyIdentifier

    def register_object_class(self, object_type: int, object_class: type) -> None:
        if _debug:
            VendorInfo._debug(
                "register_object_class(%d) %r %r",
                self.vendor_identifier,
                object_type,
                object_class,
            )
        if object_type in self.registered_object_classes:
            # built-in classes have multiple classes with different features
            if self.vendor_identifier != 999:
                warnings.warn(
                    f"object type {object_type!r}"
                    f" for vendor identifier {self.vendor_identifier}"
                    f" already registered: {self.registered_object_classes[object_type]}"
                )
            return

        self.registered_object_classes[object_type] = object_class

    def get_object_class(self, object_type: int) -> Optional[type]:
        if _debug:
            VendorInfo._debug(
                "get_object_class(%d) %r",
                self.vendor_identifier,
                object_type,
            )
        return self.registered_object_classes.get(
            object_type, None
        ) or ASHRAE_vendor_info.registered_object_classes.get(
            object_type, None
        )  # type: ignore[attr-defined]


# ASHRAE is Vendor ID 0
ASHRAE_vendor_info = VendorInfo(0)
