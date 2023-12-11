"""
Custom Objects and Properties
"""

from bacpypes3.debugging import ModuleLogger
from bacpypes3.primitivedata import Integer, ObjectType
from bacpypes3.basetypes import PropertyIdentifier
from bacpypes3.vendor import VendorInfo

from bacpypes3.local.object import _Object
from bacpypes3.local.device import DeviceObject as _DeviceObject
from bacpypes3.local.networkport import NetworkPortObject as _NetworkPortObject


# some debugging
_debug = 0
_log = ModuleLogger(globals())


# this vendor identifier reference is used when registering custom classes
_vendor_id = 888


class ProprietaryObjectType(ObjectType):
    """
    This is a list of the object type enumerations for proprietary object types,
    see Clause 23.4.1.
    """

    custom_object = 128


class ProprietaryPropertyIdentifier(PropertyIdentifier):
    """
    This is a list of the property identifiers that are used in custom object
    types or are used in custom properties of standard types.
    """

    custom_property = 512


# create a VendorInfo object for this custom application before registering
# specialize object classes
custom_vendor_info = VendorInfo(
    _vendor_id, ProprietaryObjectType, ProprietaryPropertyIdentifier
)


class DeviceObject(_DeviceObject):
    """
    When running as an instance of this custom device, the DeviceObject is
    an extension of the one defined in bacpypes3.local.device (in this case
    doesn't add any proprietary properties).
    """

    pass


class NetworkPortObject(_NetworkPortObject):
    """
    When running as an instance of this custom device, the NetworkPortObject is
    an extension of the one defined in bacpypes3.local.networkport (in this
    case doesn't add any proprietary properties).
    """

    pass


class ProprietaryObject(_Object):
    """
    This is a proprietary object type.
    """

    # object identifiers are interpreted from this customized subclass of the
    # standard ObjectIdentifier that leverages the ProprietaryObjectType
    # enumeration in the vendor information
    objectIdentifier: custom_vendor_info.object_identifier

    # all objects get the object-type property to be this value
    objectType = ProprietaryObjectType("custom_object")

    # all objects have an object-name property, provided by the parent class
    # with special hooks if an instance of this class is bound to an application
    # objectName: CharacterString

    # the property-list property of this object is provided by the getter
    # method defined in the parent class and computed dynamically
    # propertyList: ArrayOf(PropertyIdentifier)

    # this is a custom property using a standard datatype
    custom_property: Integer
