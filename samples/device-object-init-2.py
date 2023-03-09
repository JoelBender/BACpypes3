"""
Define a new device object for vendor identifier 888, create an instance of it,
dump the contents as JSON, then round-trip the JSON back into a device object.
"""
from pprint import pprint

from bacpypes3.debugging import ModuleLogger

# from bacpypes3.argparse import create_log_handler

from bacpypes3.object import VendorInfo
from bacpypes3.local.device import DeviceObject as _DeviceObject
from bacpypes3.json import sequence_to_json, json_to_sequence

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# this vendor identifier reference is used when registering custom classes
_vendor_id = 888

# create a VendorInfo object for this custom application before registering
# specialize object classes
custom_vendor_info = VendorInfo(_vendor_id)

# create_log_handler("__main__")
# create_log_handler("bacpypes3.constructeddata", color=4)
# create_log_handler("bacpypes3.object", color=5)
# create_log_handler("bacpypes3.local.object", color=6)
# create_log_handler("bacpypes3.local.device", color=6)


class DeviceObject(_DeviceObject):
    """
    When running as an instance of this custom device, the DeviceObject is
    an extension of the one defined in bacpypes3.local.device (in this case
    doesn't add any proprietary properties).

    The vendor-identifier property isn't set from the module for device
    objects, it is simpler to provide the value here in the class definition.
    """

    vendorIdentifier = _vendor_id


do1 = DeviceObject(objectIdentifier="device,1", objectName="Excelsior")
print("do1")
do1.debug_contents()
print("")

json_content = sequence_to_json(do1)
pprint(json_content)
print("")

do2 = json_to_sequence(json_content, DeviceObject)
print("do2")
do2.debug_contents()
print("")
