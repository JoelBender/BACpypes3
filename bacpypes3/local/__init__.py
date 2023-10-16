#
#   Local Objects
#

from ..basetypes import PropertyIdentifier
from ..vendor import VendorInfo


class LocalPropertyIdentifier(PropertyIdentifier):
    settings = 512


local_vendor_info = VendorInfo(999, property_identifier=LocalPropertyIdentifier)

from . import object
from . import cmd
from . import cov
from . import device
from . import analog
from . import binary
from . import event
from . import fault
from . import networkport
from . import schedule
