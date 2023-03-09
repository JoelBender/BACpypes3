#
#   Local Objects
#

from ..basetypes import PropertyIdentifier
from ..object import VendorInfo


class LocalPropertyIdentifier(PropertyIdentifier):
    settings = 512


local_vendor_info = VendorInfo(999, property_identifier=LocalPropertyIdentifier)

from . import object
from . import cmd
from . import cov
from . import device
from . import networkport
from . import schedule
