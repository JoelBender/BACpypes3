"""
BACnet/RDF Python Package
"""

#
#   Platform Check
#

import sys as _sys
import warnings as _warnings

_supported_platforms = ("linux", "win32", "darwin")

if _sys.platform not in _supported_platforms:
    _warnings.warn("unsupported platform", RuntimeWarning)

#
#
#

from .core import BACnetNS, BACnetGraph

from . import core
from . import util
