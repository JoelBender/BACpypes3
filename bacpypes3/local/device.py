"""
Device Object
"""

from __future__ import annotations

from typing import Any, Callable, List

from ..debugging import bacpypes_debugging, ModuleLogger
from ..primitivedata import Date, Time, ObjectIdentifier, ObjectType
from ..basetypes import (
    AddressBinding,
    DeviceStatus,
    Segmentation,
    ServicesSupported,
    ObjectTypesSupported,
    ListOfCOVSubscription,
)
from ..constructeddata import ArrayOf, ListOf

# object module provides basic DeviceObject
from ..object import DeviceObject as _DeviceObject

# local object provides dynamically generated propertyList property
from .object import Object

# some debugging
_debug = 0
_log = ModuleLogger(globals())


# this is for sample applications
_vendor_id = 999

ArrayOfObjectIdentifier = ArrayOf(ObjectIdentifier)
ListOfAddressBinding = ListOf(AddressBinding)


@bacpypes_debugging
class DeviceObject(Object, _DeviceObject):
    """
    A local device object has a dynamically generated localDate, localTime, and
    objectList property.
    """

    _debug: Callable[..., None]

    objectType = ObjectType("device")

    systemStatus = DeviceStatus.operational
    vendorName = "BACpypes"
    vendorIdentifier = _vendor_id
    modelName = "N/A"
    firmwareRevision = "N/A"
    applicationSoftwareVersion = "1.0"
    protocolVersion = 1
    protocolRevision = 22
    databaseRevision = 1

    maxApduLengthAccepted = 1024
    segmentationSupported = Segmentation.segmentedBoth
    maxSegmentsAccepted = 16
    apduSegmentTimeout = 1000
    apduTimeout = 3000
    numberOfApduRetries = 3

    @property
    def localDate(self) -> Date:  # type: ignore[override]
        """Return the local date."""
        return Date.now()

    @localDate.setter
    def localDate(self, value: Any) -> None:
        """Change the local date, ignored."""
        if _debug:
            DeviceObject._debug("DeviceObject.localDate(setter) %r", value)

    @property
    def localTime(self) -> Time:  # type: ignore[override]
        """Return the local time."""
        return Time.now()

    @localTime.setter
    def localTime(self, value: Any) -> None:
        """Change the local time, ignored."""
        if _debug:
            DeviceObject._debug("DeviceObject.localTime(setter) %r", value)

    @property
    def objectList(self) -> ArrayOfObjectIdentifier:  # type: ignore[valid-type]
        """
        Return the list of identifiers for the objects in the application.  If
        this object isn't bound to an application, return a list of just itself.
        """
        object_identifier_list: List[ObjectIdentifier]
        if not self._app:
            object_identifier_list = [self.objectIdentifier]
        else:
            object_identifier_list = list(self._app.objectIdentifier.keys())

        return ArrayOfObjectIdentifier(object_identifier_list)

    @objectList.setter
    def objectList(self, value: Any) -> None:
        """Change the list of objects in the application, ignored."""
        if _debug:
            DeviceObject._debug("DeviceObject.objectList(setter) %r", value)

    @property
    def protocolServicesSupported(self) -> ServicesSupported:  # type: ignore[override]
        """Return the protocol services supported."""
        if _debug:
            DeviceObject._debug("DeviceObject.protocolServicesSupported(getter)")

        if not self._app:
            if _debug:
                DeviceObject._debug("    - no application")
            return ServicesSupported([])
        else:
            return self._app.get_services_supported()

    @protocolServicesSupported.setter
    def protocolServicesSupported(self, value: Any) -> None:
        """Change the protocol services supported, ignored."""
        if _debug:
            DeviceObject._debug(
                "DeviceObject.protocolServicesSupported(setter) %r", value
            )

    @property
    def protocolObjectTypesSupported(self) -> ObjectTypesSupported:  # type: ignore[override]
        """Return the protocol object types supported."""
        if _debug:
            DeviceObject._debug("DeviceObject.protocolObjectTypesSupported(getter)")

        return ObjectTypesSupported([])

    @protocolObjectTypesSupported.setter
    def protocolObjectTypesSupported(self, value: Any) -> None:
        """Change the protocol object types supported, ignored."""
        if _debug:
            DeviceObject._debug(
                "DeviceObject.protocolObjectTypesSupported(setter) %r", value
            )

    @property
    def deviceAddressBinding(self) -> ListOfAddressBinding:
        """Return the device address binding list."""
        if _debug:
            DeviceObject._debug("DeviceObject.deviceAddressBinding(getter)")

        return ListOfAddressBinding()

    @deviceAddressBinding.setter
    def deviceAddressBinding(self, value: Any) -> None:
        """Change the device address binding list, ignored."""
        if _debug:
            DeviceObject._debug("DeviceObject.deviceAddressBinding(setter) %r", value)

    @property
    def activeCovSubscriptions(self) -> ListOfCOVSubscription:
        """Return the list of active subscriptions."""
        if _debug:
            DeviceObject._debug("DeviceObject.activeCovSubscriptions(getter)")

        if not self._app or (not hasattr(self._app, "get_active_cov_subscriptions")):
            if _debug:
                DeviceObject._debug("    - no application")
            return ListOfCOVSubscription()
        else:
            return self._app.get_active_cov_subscriptions()

    @activeCovSubscriptions.setter
    def activeCovSubscriptions(self, value: Any) -> None:
        """Change the active subscriptions."""
        if _debug:
            DeviceObject._debug("DeviceObject.activeCovSubscriptions(setter) %r", value)
