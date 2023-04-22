"""
BACnet Python Package
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
#   Project Metadata
#

__version__ = "0.0.71"
__author__ = "Joel Bender"
__email__ = "joel@carrickbender.com"

#
#   Settings and Debugging
#

from . import settings
from . import debugging
from . import errors

#
#   Communications Core Modules
#

from . import pdu
from . import comm

#
#   Shell
#

from . import argparse
from . import console

# from . import singleton
# from . import capability

#
#   Link Layer Modules
#

from . import ipv4
from . import ipv6
from . import vlan

try:
    import websockets
    from . import sc
except ImportError:
    pass

#
#   Network Layer Modules
#

from . import npdu
from . import netservice

#
#   Application Layer Modules
#

from . import primitivedata
from . import constructeddata
from . import basetypes
from . import object
from . import apdu

from . import app
from . import appservice

from . import local
from . import service

#
#   Library of useful functions
#

from . import lib
from . import json

try:
    import rdflib  # type: ignore[import]
    from . import rdf
except ImportError:
    pass

#
#   Analysis
#

# from . import analysis
